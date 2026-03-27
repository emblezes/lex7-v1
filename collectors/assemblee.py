"""Collecteur Assemblée nationale — polling CSV publication_j + fetch XML.

Adapté depuis LegisAPI pour async (httpx + SQLAlchemy async).
"""

import tempfile
from collections import defaultdict
from datetime import datetime
from io import StringIO
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.collectors.base import BaseCollector
from legix.core.config import settings
from legix.core.models import (
    Acteur,
    Amendement,
    CompteRendu,
    Reunion,
    SeenPublication,
    Texte,
)
from legix.parsers.amendement import parse_amendement
from legix.parsers.compte_rendu import parse_compte_rendu
from legix.parsers.reunion import parse_reunion
from legix.parsers.texte import parse_texte

# Mapping préfixes → (parser_key, parser_fn, model_class, type_label)
DOCUMENT_TYPES = {
    "AMANR": ("amendement", parse_amendement, Amendement, "Amendement"),
    "RUANR": ("reunion", parse_reunion, Reunion, "Réunion"),
    "PIONANR": ("texte", parse_texte, Texte, "Texte législatif"),
    "PNREANR": ("texte", parse_texte, Texte, "Proposition de résolution"),
    "CRSANR": ("compte_rendu", parse_compte_rendu, CompteRendu, "Compte rendu"),
    "RAPPANR": ("texte", parse_texte, Texte, "Rapport"),
}

SKIP_TYPES = {"EDOCANR", "CRSAJOANR", "RIONANR"}


class AssembleeCollector(BaseCollector):
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)

    def get_source_name(self) -> str:
        return "assemblee"

    async def fetch_publication_list(self, date: str = "j") -> list[tuple[str, str]]:
        """Fetch the daily publication CSV."""
        url = f"{settings.an_publication_url}/publication_{date}"
        response = await self.client.get(url)

        if response.status_code == 404:
            return []
        response.raise_for_status()

        publications = []
        for line in StringIO(response.text):
            line = line.strip()
            if not line or ";" not in line:
                continue
            parts = line.split(";", 1)
            if len(parts) == 2:
                publications.append((parts[0], parts[1]))
        return publications

    async def get_new_publications(
        self, session: AsyncSession, publications: list[tuple[str, str]]
    ) -> list[tuple[str, str]]:
        """Filtre les publications non encore traitées."""
        by_url: dict[str, str] = {}
        for timestamp, url in publications:
            if not url.endswith(".xml"):
                continue
            by_url[url] = timestamp

        new = []
        for url, timestamp in by_url.items():
            result = await session.get(SeenPublication, url)
            if result is None:
                new.append((timestamp, url))
        return new

    def detect_type(self, url: str) -> str | None:
        """Détecte le type de document depuis le préfixe du nom de fichier."""
        filename = url.rsplit("/", 1)[-1]
        for prefix in DOCUMENT_TYPES:
            if filename.startswith(prefix):
                return prefix
        for prefix in SKIP_TYPES:
            if filename.startswith(prefix):
                return None
        return None

    async def download_xml(self, url: str) -> str | None:
        """Télécharge un fichier XML dans un fichier temporaire."""
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            tmp = tempfile.NamedTemporaryFile(suffix=".xml", delete=False)
            tmp.write(response.content)
            tmp.close()
            return tmp.name
        except httpx.HTTPError:
            return None

    async def store_amendement(self, session: AsyncSession, data: dict) -> str:
        existing = await session.get(Amendement, data["uid"])
        if existing:
            # Detecter si le sort a change → invalider le score
            old_sort = existing.sort or ""
            new_sort = data.get("sort", "") or ""
            sort_changed = old_sort != new_sort and new_sort

            for key in ["etat", "sort", "date_sort", "date_publication",
                        "dispositif", "expose_sommaire"]:
                if data.get(key):
                    setattr(existing, key, data[key])
            existing.updated_at = datetime.utcnow()

            if sort_changed:
                # Forcer le re-scoring au prochain batch
                existing.score_impact = None

            return "updated"

        amdt = Amendement(
            uid=data["uid"], legislature=data["legislature"],
            numero=data["numero"], numero_ordre_depot=data["numero_ordre_depot"],
            texte_ref=data["texte_ref"], examen_ref=data["examen_ref"],
            organe_examen=data["organe_examen"],
            auteur_ref=data["auteur_ref"], auteur_type=data["auteur_type"],
            groupe_ref=data["groupe_ref"],
            article_vise=data["article_vise"], article_type=data["article_type"],
            alinea=data["alinea"],
            dispositif=data["dispositif"], expose_sommaire=data["expose_sommaire"],
            date_depot=data["date_depot"], date_publication=data["date_publication"],
            date_sort=data["date_sort"],
            etat=data["etat"], sort=data["sort"],
            source="assemblee",
        )
        session.add(amdt)
        return "new"

    async def store_reunion(self, session: AsyncSession, data: dict) -> str:
        existing = await session.get(Reunion, data["uid"])
        if existing:
            for key in ["etat", "odj", "lieu", "date_debut"]:
                if data.get(key):
                    setattr(existing, key, data[key])
            existing.updated_at = datetime.utcnow()
            return "updated"

        reunion = Reunion(
            uid=data["uid"], date_debut=data["date_debut"],
            lieu=data["lieu"], organe_ref=data["organe_ref"],
            etat=data["etat"], ouverture_presse=data["ouverture_presse"],
            captation_video=data["captation_video"],
            visioconference=data["visioconference"],
            odj=data["odj"], format_reunion=data["format_reunion"],
            source="assemblee",
        )
        session.add(reunion)
        return "new"

    async def store_texte(self, session: AsyncSession, data: dict) -> str:
        existing = await session.get(Texte, data["uid"])
        if existing:
            for key in ["titre", "titre_court", "date_publication"]:
                if data.get(key):
                    setattr(existing, key, data[key])
            existing.updated_at = datetime.utcnow()
            return "updated"

        texte = Texte(
            uid=data["uid"], legislature=data["legislature"],
            denomination=data["denomination"],
            titre=data["titre"], titre_court=data["titre_court"],
            type_code=data["type_code"], type_libelle=data["type_libelle"],
            date_depot=data["date_depot"], date_publication=data["date_publication"],
            dossier_ref=data["dossier_ref"], organe_ref=data["organe_ref"],
            source="assemblee",
        )
        session.add(texte)
        return "new"

    async def store_compte_rendu(self, session: AsyncSession, data: dict) -> str:
        existing = await session.get(CompteRendu, data["uid"])
        if existing:
            for key in ["sommaire", "etat"]:
                if data.get(key):
                    setattr(existing, key, data[key])
            existing.updated_at = datetime.utcnow()
            return "updated"

        cr = CompteRendu(
            uid=data["uid"], seance_ref=data["seance_ref"],
            session_ref=data["session_ref"],
            date_seance=data["date_seance"], date_seance_jour=data["date_seance_jour"],
            num_seance=data["num_seance"], etat=data["etat"],
            sommaire=data["sommaire"], source="assemblee",
        )
        session.add(cr)
        return "new"

    async def collect(self, session: AsyncSession, date: str = "j") -> dict:
        """Collecte les nouvelles publications de l'Assemblée nationale."""
        stats = {
            "new": 0, "updated": 0, "skipped": 0, "errors": 0,
            "by_type": defaultdict(int),
            "new_uids": {"texte": [], "amendement": [], "reunion": [], "compte_rendu": []},
            "updated_uids": {"texte": [], "amendement": [], "reunion": [], "compte_rendu": []},
        }

        publications = await self.fetch_publication_list(date)
        if not publications:
            return stats

        new_pubs = await self.get_new_publications(session, publications)

        store_methods = {
            "amendement": self.store_amendement,
            "reunion": self.store_reunion,
            "texte": self.store_texte,
            "compte_rendu": self.store_compte_rendu,
        }

        for timestamp, url in new_pubs:
            doc_type = self.detect_type(url)
            if doc_type is None:
                stats["skipped"] += 1
                await session.merge(SeenPublication(
                    url=url, timestamp=timestamp,
                    document_type="unknown", document_uid="",
                ))
                await session.commit()
                continue

            parser_key, parser_fn, model_class, type_label = DOCUMENT_TYPES[doc_type]

            filepath = await self.download_xml(url)
            if filepath is None:
                stats["errors"] += 1
                continue

            try:
                data = parser_fn(filepath)
                result = await store_methods[parser_key](session, data)

                if result == "new":
                    stats["new"] += 1
                    stats["new_uids"][parser_key].append(data["uid"])
                else:
                    stats["updated"] += 1
                    stats["updated_uids"][parser_key].append(data["uid"])

                stats["by_type"][type_label] += 1

                await session.merge(SeenPublication(
                    url=url, timestamp=timestamp,
                    document_type=doc_type, document_uid=data.get("uid", ""),
                ))
                await session.commit()

            except Exception as e:
                await session.rollback()
                stats["errors"] += 1
                print(f"  Error processing {url}: {e}")

            finally:
                Path(filepath).unlink(missing_ok=True)

        return stats

    async def backfill(self, session: AsyncSession, days: int = 30) -> dict:
        """Rattrapage historique : collecte les publications des N derniers jours.

        L'AN expose publication_j, publication_j-1, ..., publication_j-N.
        Cette methode itere sur chaque jour pour ingerer les textes,
        amendements et reunions manquants.
        """
        import logging
        logger = logging.getLogger(__name__)

        total_stats = {
            "new": 0, "updated": 0, "skipped": 0, "errors": 0,
            "by_type": defaultdict(int),
            "new_uids": {"texte": [], "amendement": [], "reunion": [], "compte_rendu": []},
            "updated_uids": {"texte": [], "amendement": [], "reunion": [], "compte_rendu": []},
        }

        for offset in range(days + 1):
            date_key = "j" if offset == 0 else f"j-{offset}"
            logger.info("[assemblee] Backfill jour %s...", date_key)

            try:
                day_stats = await self.collect(session, date=date_key)
            except Exception as e:
                logger.warning("[assemblee] Backfill %s echoue: %s", date_key, e)
                total_stats["errors"] += 1
                continue

            total_stats["new"] += day_stats["new"]
            total_stats["updated"] += day_stats["updated"]
            total_stats["skipped"] += day_stats["skipped"]
            total_stats["errors"] += day_stats["errors"]
            for k, v in day_stats["by_type"].items():
                total_stats["by_type"][k] += v
            for k in total_stats["new_uids"]:
                total_stats["new_uids"][k].extend(day_stats["new_uids"].get(k, []))
            for k in total_stats["updated_uids"]:
                total_stats["updated_uids"][k].extend(day_stats["updated_uids"].get(k, []))

        logger.info(
            "[assemblee] Backfill %d jours termine: %d nouveaux, %d maj, %d erreurs",
            days, total_stats["new"], total_stats["updated"], total_stats["errors"],
        )
        return total_stats

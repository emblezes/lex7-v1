"""Collecteur Scrutins — votes nominatifs de l'Assemblée nationale.

Source : Open data AN — archive ZIP de fichiers JSON individuels par scrutin.
Chaque scrutin contient le vote nominatif de chaque député.

URL : https://data.assemblee-nationale.fr/static/openData/repository/17/loi/scrutins/Scrutins.json.zip
"""

import io
import json
import logging
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from legix.collectors.base import BaseCollector
from legix.core.models import ScrutinVote

logger = logging.getLogger(__name__)

# Archive ZIP des scrutins (fichiers JSON individuels)
SCRUTINS_ZIP_URL = (
    "https://data.assemblee-nationale.fr/static/openData/repository"
    "/17/loi/scrutins/Scrutins.json.zip"
)


class ScrutinsCollector(BaseCollector):
    """Collecteur des scrutins publics de l'Assemblée nationale."""

    def get_source_name(self) -> str:
        return "scrutins"

    async def collect(self, db: AsyncSession) -> dict:
        stats = self._empty_stats()

        # Determiner les scrutins deja en base pour ne pas tout re-traiter
        result = await db.execute(
            select(func.count(func.distinct(ScrutinVote.scrutin_numero)))
        )
        known_count = result.scalar() or 0

        try:
            zip_bytes = await self._download_zip()
            if not zip_bytes:
                logger.warning("[scrutins] Impossible de telecharger le ZIP")
                stats["errors"] += 1
                return stats

            scrutins = self._extract_scrutins(zip_bytes)
            logger.info(
                "[scrutins] %d scrutins dans le ZIP, %d deja en base",
                len(scrutins), known_count,
            )

            # Traiter tous les scrutins (le check de doublon est dans _process_scrutin)
            batch_size = 0
            for scrutin_data in scrutins:
                created = await self._process_scrutin(db, stats, scrutin_data)
                if created:
                    batch_size += 1
                # Commit par batch de 50 scrutins pour eviter les transactions trop longues
                if batch_size >= 50:
                    await db.commit()
                    batch_size = 0

            await db.commit()

        except Exception as e:
            logger.error("[scrutins] Collecte echouee: %s", e, exc_info=True)
            stats["errors"] += 1

        if stats["new"] > 0:
            logger.info("[scrutins] %d nouveaux votes collectes", stats["new"])
        return stats

    async def _download_zip(self) -> bytes | None:
        """Telecharge le ZIP des scrutins (timeout etendu car ~19 MB)."""
        client = await self._get_client()
        try:
            resp = await client.get(SCRUTINS_ZIP_URL, timeout=120.0)
            resp.raise_for_status()
            logger.info(
                "[scrutins] ZIP telecharge: %.1f MB",
                len(resp.content) / 1_000_000,
            )
            return resp.content
        except Exception as e:
            logger.warning("[scrutins] Erreur telechargement ZIP: %s", e)
            return None

    def _extract_scrutins(self, zip_bytes: bytes) -> list[dict]:
        """Extrait les scrutins du ZIP en memoire."""
        scrutins = []
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                if not name.endswith(".json"):
                    continue
                try:
                    with zf.open(name) as f:
                        data = json.load(f)
                    # Le JSON contient {"scrutin": {...}}
                    scrutin = data.get("scrutin", data)
                    scrutins.append(scrutin)
                except (json.JSONDecodeError, KeyError) as e:
                    logger.debug("[scrutins] Erreur parsing %s: %s", name, e)
                    continue
        return scrutins

    async def _process_scrutin(
        self, db: AsyncSession, stats: dict, scrutin: dict
    ) -> bool:
        """Traite un scrutin et extrait les votes nominatifs.

        Returns True si de nouveaux votes ont ete crees.
        """
        numero = scrutin.get("numero")
        if not numero:
            return False

        numero_int = int(numero) if isinstance(numero, str) else numero

        # Verifier si deja traite
        existing = await db.execute(
            select(ScrutinVote).where(
                ScrutinVote.scrutin_numero == numero_int
            ).limit(1)
        )
        if existing.scalar_one_or_none():
            return False

        titre = scrutin.get("titre", "")
        if not titre:
            titre = scrutin.get("objet", {}).get("libelle", "")
        date_str = scrutin.get("dateScrutin", "")
        scrutin_date = None
        if date_str:
            try:
                scrutin_date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                pass

        scrutin_type = scrutin.get("typeVote", {}).get(
            "libelleTypeVote", "ordinaire"
        )

        # Resultats globaux
        synthese = scrutin.get("syntheseVote", {})
        nombre_votants = _to_int(synthese.get("nombreVotants"))
        decompte = synthese.get("decompte", {})
        pour_total = _to_int(decompte.get("pour"))
        contre_total = _to_int(decompte.get("contre"))
        abstentions_total = _to_int(decompte.get("abstentions"))

        # Resultat
        sort_code = scrutin.get("sort", {}).get("code", "")
        resultat = (
            "adopte"
            if sort_code in ("adopté", "adopte")
            else "rejete"
        )

        # Extraire les votes par groupe
        ventilation = (
            scrutin.get("ventilationVotes", {})
            .get("organe", {})
            .get("groupes", {})
            .get("groupe", [])
        )
        if isinstance(ventilation, dict):
            ventilation = [ventilation]

        created_any = False
        for groupe_data in ventilation:
            groupe_ref = groupe_data.get("organeRef", "")
            vote_data = groupe_data.get("vote", {})
            decompte_nom = vote_data.get("decompteNominatif", {})

            for position_key, position_label in [
                ("pours", "pour"),
                ("contres", "contre"),
                ("abstentions", "abstention"),
                ("nonVotants", "non_votant"),
            ]:
                votants = decompte_nom.get(position_key, {})
                if not votants or not isinstance(votants, dict):
                    continue
                votant_list = votants.get("votant", [])
                if isinstance(votant_list, dict):
                    votant_list = [votant_list]

                for votant in votant_list:
                    acteur_uid = votant.get("acteurRef", "")
                    if not acteur_uid:
                        continue

                    vote = ScrutinVote(
                        scrutin_numero=numero_int,
                        scrutin_titre=titre[:500] if titre else "",
                        scrutin_date=scrutin_date,
                        scrutin_type=scrutin_type,
                        acteur_uid=acteur_uid,
                        position=position_label,
                        groupe_ref=groupe_ref or None,
                        nombre_votants=nombre_votants,
                        pour_total=pour_total,
                        contre_total=contre_total,
                        abstentions_total=abstentions_total,
                        resultat=resultat,
                        source="assemblee",
                    )
                    db.add(vote)
                    stats["new"] += 1
                    stats["new_uids"]["scrutin_vote"].append(
                        f"{numero_int}-{acteur_uid}"
                    )
                    created_any = True

        if created_any:
            stats["by_type"]["scrutin"] += 1
        return created_any


def _to_int(val) -> int | None:
    """Conversion sure en int."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None

"""Collecteur HATVP — Haute Autorite pour la Transparence de la Vie Publique.

Source : API open data HATVP (representants d'interets).
Utile pour savoir qui d'autre lobbye sur les memes sujets que le client.
"""

import hashlib
import json
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from legix.collectors.base import BaseCollector
from legix.core.models import StakeholderProfile

logger = logging.getLogger(__name__)

# API open data HATVP
HATVP_API_BASE = "https://www.hatvp.fr/api/v1"
HATVP_SEARCH_URL = f"{HATVP_API_BASE}/representants"
HATVP_FICHES_URL = f"{HATVP_API_BASE}/fiches"


class HATVPCollector(BaseCollector):
    """Collecte les representants d'interets depuis le registre HATVP."""

    def get_source_name(self) -> str:
        return "hatvp"

    async def collect(self, db: AsyncSession) -> dict:
        stats = self._empty_stats()

        # Recuperer la liste des representants
        try:
            data = await self._fetch_json(HATVP_SEARCH_URL)
        except Exception as e:
            logger.error("HATVP: erreur API: %s", e)
            # Fallback : scraper les CSV open data
            data = await self._fetch_opendata_csv()

        if not data:
            logger.warning("HATVP: aucune donnee recuperee")
            return stats

        representants = data if isinstance(data, list) else data.get("results", [])

        for rep in representants:
            try:
                await self._process_representant(db, rep, stats)
            except Exception as e:
                stats["errors"] += 1
                logger.error("HATVP: erreur traitement: %s", e)

        await db.commit()
        logger.info(
            "HATVP: %d nouveaux, %d mis a jour, %d ignores, %d erreurs",
            stats["new"], stats["updated"], stats["skipped"], stats["errors"],
        )
        return stats

    async def _process_representant(
        self, db: AsyncSession, rep: dict, stats: dict,
    ):
        """Traite un representant d'interets."""
        # Construire l'identifiant unique
        nom = rep.get("denomination", rep.get("nom", ""))
        if not nom:
            stats["skipped"] += 1
            return

        uid = f"HATVP_{hashlib.md5(nom.encode()).hexdigest()[:12]}"

        # Verifier si deja vu
        url = rep.get("url", f"https://www.hatvp.fr/fiche-organisation/?id={uid}")
        if await self._is_seen(db, url):
            stats["skipped"] += 1
            return

        # Extraire les infos
        activites = rep.get("activites", [])
        themes = self._extract_themes(activites)
        chiffre_affaires = rep.get("chiffre_affaires", rep.get("ca", None))

        # Creer ou mettre a jour le StakeholderProfile
        stakeholder = StakeholderProfile(
            acteur_uid=uid,
            nom=nom,
            stakeholder_type="lobbyiste",
            organisation=nom,
            email=rep.get("email"),
            phone=rep.get("telephone"),
            key_themes=json.dumps(themes, ensure_ascii=False),
            bio_summary=self._build_summary(rep, activites),
            influence_score=self._estimate_influence(rep),
            data_source="hatvp",
            metadata_=json.dumps({
                "chiffre_affaires": chiffre_affaires,
                "nombre_activites": len(activites),
                "type_organisation": rep.get("type", ""),
                "adresse": rep.get("adresse", ""),
            }, ensure_ascii=False),
        )
        db.add(stakeholder)
        await self._mark_seen(db, url, "stakeholder", uid)
        stats["new"] += 1
        stats["new_uids"].append(uid)

    def _extract_themes(self, activites: list) -> list[str]:
        """Extrait les themes des activites de lobbying."""
        themes = set()
        theme_keywords = {
            "sante": ["sante", "medicament", "hopital", "pharma"],
            "environnement/climat": ["environnement", "climat", "ecologie", "carbone"],
            "energie": ["energie", "nucleaire", "renouvelable", "petrole", "gaz"],
            "numerique/tech": ["numerique", "tech", "donnees", "ia", "cyber"],
            "finance": ["banque", "finance", "assurance", "investissement"],
            "transport": ["transport", "mobilite", "automobile", "ferroviaire"],
            "agriculture": ["agriculture", "agroalimentaire", "pesticide"],
            "industrie": ["industrie", "manufacture", "production"],
        }
        for activite in activites:
            desc = str(activite).lower()
            for theme, keywords in theme_keywords.items():
                if any(kw in desc for kw in keywords):
                    themes.add(theme)
        return list(themes)

    def _build_summary(self, rep: dict, activites: list) -> str:
        """Construit un resume du representant."""
        parts = [f"Representant d'interets: {rep.get('denomination', '')}"]
        if rep.get("type"):
            parts.append(f"Type: {rep['type']}")
        if activites:
            parts.append(f"{len(activites)} activite(s) de lobbying declaree(s)")
        return ". ".join(parts)

    def _estimate_influence(self, rep: dict) -> int:
        """Estime un score d'influence (0-100)."""
        score = 30  # Base
        ca = rep.get("chiffre_affaires", 0)
        if ca and isinstance(ca, (int, float)):
            if ca > 1_000_000_000:
                score += 40
            elif ca > 100_000_000:
                score += 30
            elif ca > 10_000_000:
                score += 20
            elif ca > 1_000_000:
                score += 10
        nb_activites = len(rep.get("activites", []))
        score += min(nb_activites * 5, 30)
        return min(score, 100)

    async def _fetch_opendata_csv(self) -> list:
        """Fallback : recupere les donnees HATVP depuis le CSV open data."""
        csv_url = "https://www.hatvp.fr/wordpress/wp-content/uploads/2024/opendata/export_representants.csv"
        try:
            text = await self._fetch_text(csv_url)
            if not text:
                return []
            import csv
            import io
            reader = csv.DictReader(io.StringIO(text), delimiter=";")
            return list(reader)
        except Exception as e:
            logger.error("HATVP CSV fallback echoue: %s", e)
            return []

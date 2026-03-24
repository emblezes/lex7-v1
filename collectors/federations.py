"""Collecteur federations professionnelles — MEDEF, CPME, AFEP, FBF, FNSEA, etc.

Surveille les prises de position des federations sectorielles.
Utile pour : detecter les alliances possibles, reperer les positions concurrentes,
anticiper les campagnes de lobbying.
"""

import json
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from legix.collectors.base import BaseCollector
from legix.collectors.rss_utils import parse_rss_entries
from legix.core.models import PressArticle

logger = logging.getLogger(__name__)

# Sources RSS des federations professionnelles
FEDERATION_FEEDS = [
    # Patronat general
    {"name": "MEDEF", "url": "https://www.medef.com/fr/feed", "themes": ["travail/emploi", "fiscalite", "industrie"], "sector": "general"},
    {"name": "CPME", "url": "https://www.cpme.fr/feed", "themes": ["travail/emploi", "commerce"], "sector": "general"},
    {"name": "AFEP", "url": "https://afep.com/feed/", "themes": ["fiscalite", "finance", "industrie"], "sector": "general"},
    {"name": "U2P", "url": "https://u2p-france.fr/feed", "themes": ["travail/emploi", "commerce"], "sector": "general"},
    # Finance / banque
    {"name": "FBF (Fed. Bancaire)", "url": "https://www.fbf.fr/feed/", "themes": ["finance"], "sector": "finance"},
    {"name": "France Assureurs", "url": "https://www.franceassureurs.fr/feed/", "themes": ["finance"], "sector": "assurance"},
    # Industrie / construction
    {"name": "France Industrie", "url": "https://www.franceindustrie.org/feed/", "themes": ["industrie"], "sector": "industrie"},
    {"name": "FFB (Fed. Batiment)", "url": "https://www.ffbatiment.fr/feed", "themes": ["logement", "industrie"], "sector": "construction"},
    {"name": "FIEEC (Electrique)", "url": "https://www.fieec.fr/feed/", "themes": ["industrie", "numerique/tech", "energie"], "sector": "electronique"},
    # Energie
    {"name": "UFE (Electricite)", "url": "https://ufe-electricite.fr/feed/", "themes": ["energie"], "sector": "energie"},
    {"name": "SER (Renouvelables)", "url": "https://www.syndicat-energies-renouvelables.fr/feed/", "themes": ["energie", "environnement/climat"], "sector": "energie"},
    # Agriculture
    {"name": "FNSEA", "url": "https://www.fnsea.fr/feed/", "themes": ["agriculture"], "sector": "agriculture"},
    {"name": "ANIA (Agroalimentaire)", "url": "https://www.ania.net/feed/", "themes": ["agriculture", "sante"], "sector": "agroalimentaire"},
    # Numerique
    {"name": "Syntec Numerique", "url": "https://numeum.fr/feed", "themes": ["numerique/tech"], "sector": "numerique"},
    {"name": "TECH IN France", "url": "https://www.techinfrance.fr/feed/", "themes": ["numerique/tech"], "sector": "numerique"},
    # Sante
    {"name": "LEEM (Pharma)", "url": "https://www.leem.org/feed", "themes": ["sante"], "sector": "pharma"},
    {"name": "FHP (Hospitalisation)", "url": "https://www.fhp.fr/feed", "themes": ["sante"], "sector": "sante"},
    # Transport
    {"name": "FNTR (Transport routier)", "url": "https://www.fntr.fr/feed", "themes": ["transport"], "sector": "transport"},
    {"name": "UTP (Transport public)", "url": "https://www.utp.fr/feed", "themes": ["transport"], "sector": "transport"},
    # Commerce
    {"name": "FCD (Commerce)", "url": "https://www.fcd.fr/feed/", "themes": ["commerce"], "sector": "commerce"},
]


class FederationsCollector(BaseCollector):
    """Collecte les publications des federations professionnelles."""

    def get_source_name(self) -> str:
        return "federations"

    async def collect(
        self,
        db: AsyncSession,
        feeds: list[dict] | None = None,
        sectors: list[str] | None = None,
    ) -> dict:
        """Collecte les flux RSS des federations.

        Args:
            db: Session DB
            feeds: Liste custom de feeds (sinon FEDERATION_FEEDS)
            sectors: Filtrer par secteur (ex: ["finance", "energie"])
        """
        stats = self._empty_stats()

        target_feeds = feeds or FEDERATION_FEEDS
        if sectors:
            target_feeds = [f for f in target_feeds if f.get("sector") in sectors]

        for feed_config in target_feeds:
            try:
                await self._process_feed(db, feed_config, stats)
            except Exception as e:
                stats["errors"] += 1
                logger.error("Federation %s: erreur: %s", feed_config["name"], e)

        await db.commit()
        logger.info(
            "Federations: %d nouveaux, %d ignores, %d erreurs (sur %d sources)",
            stats["new"], stats["skipped"], stats["errors"], len(target_feeds),
        )
        return stats

    async def _process_feed(
        self, db: AsyncSession, config: dict, stats: dict,
    ):
        """Traite un flux RSS de federation."""
        name = config["name"]

        try:
            xml_bytes = await self._fetch_xml(config["url"])
        except Exception:
            logger.warning("Federation %s: flux inaccessible", name)
            stats["errors"] += 1
            return

        if not xml_bytes:
            return

        entries = parse_rss_entries(xml_bytes)

        for entry in entries[:15]:
            entry_url = entry.get("link", "")
            if not entry_url:
                continue

            if await self._is_seen(db, entry_url):
                stats["skipped"] += 1
                continue

            article = PressArticle(
                source_name=name,
                title=entry.get("title", ""),
                url=entry_url,
                publication_date=entry.get("published"),
                excerpt=entry.get("summary", "")[:1000],
                themes=json.dumps(config["themes"], ensure_ascii=False),
                author="federation",
            )
            db.add(article)
            await self._mark_seen(db, entry_url, "press_article", f"fed_{name}")
            stats["new"] += 1

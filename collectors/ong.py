"""Collecteur ONG — Organisations Non Gouvernementales et societe civile.

Sources RSS : FNE, Greenpeace, Oxfam, Amnesty, Les Amis de la Terre,
WWF, Fondation Abbe Pierre, Secours Catholique, UFC-Que Choisir, etc.

Utile pour : veille parties prenantes, anticipation campagnes,
detection de pressions sur les decideurs.
"""

import json
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from legix.collectors.base import BaseCollector
from legix.collectors.rss_utils import parse_rss_entries
from legix.core.models import PressArticle

logger = logging.getLogger(__name__)

# Sources RSS des principales ONG francaises
ONG_FEEDS = [
    # Environnement
    {"name": "France Nature Environnement", "url": "https://fne.asso.fr/feed", "themes": ["environnement/climat"], "type": "ong_env"},
    {"name": "Greenpeace France", "url": "https://www.greenpeace.fr/feed/", "themes": ["environnement/climat", "energie"], "type": "ong_env"},
    {"name": "Les Amis de la Terre", "url": "https://www.amisdelaterre.org/feed/", "themes": ["environnement/climat", "finance"], "type": "ong_env"},
    {"name": "WWF France", "url": "https://www.wwf.fr/feed", "themes": ["environnement/climat"], "type": "ong_env"},
    {"name": "Reseau Action Climat", "url": "https://reseauactionclimat.org/feed/", "themes": ["environnement/climat", "energie", "transport"], "type": "ong_env"},
    {"name": "Notre Affaire a Tous", "url": "https://notreaffaireatous.org/feed/", "themes": ["environnement/climat", "justice"], "type": "ong_env"},
    # Social / droits humains
    {"name": "Oxfam France", "url": "https://www.oxfamfrance.org/feed/", "themes": ["fiscalite", "international"], "type": "ong_social"},
    {"name": "Amnesty International FR", "url": "https://www.amnesty.fr/feed", "themes": ["justice", "international"], "type": "ong_droits"},
    {"name": "Fondation Abbe Pierre", "url": "https://www.fondation-abbe-pierre.fr/feed", "themes": ["logement"], "type": "ong_social"},
    {"name": "Secours Catholique", "url": "https://www.secours-catholique.org/feed", "themes": ["travail/emploi", "logement"], "type": "ong_social"},
    {"name": "ATD Quart Monde", "url": "https://www.atd-quartmonde.fr/feed/", "themes": ["travail/emploi", "logement"], "type": "ong_social"},
    # Consommateurs / sante
    {"name": "UFC-Que Choisir", "url": "https://www.quechoisir.org/rss/", "themes": ["sante", "numerique/tech", "commerce"], "type": "ong_conso"},
    {"name": "Foodwatch France", "url": "https://www.foodwatch.org/fr/feed/", "themes": ["sante", "agriculture"], "type": "ong_conso"},
    # Numerique
    {"name": "La Quadrature du Net", "url": "https://www.laquadrature.net/feed/", "themes": ["numerique/tech", "justice"], "type": "ong_num"},
    {"name": "Framasoft", "url": "https://framablog.org/feed/", "themes": ["numerique/tech"], "type": "ong_num"},
    # Industrie / federations
    {"name": "Transparency International FR", "url": "https://transparency-france.org/feed/", "themes": ["finance", "justice"], "type": "ong_gouvernance"},
]


class ONGCollector(BaseCollector):
    """Collecte les publications des ONG et organisations de la societe civile."""

    def get_source_name(self) -> str:
        return "ong"

    async def collect(
        self, db: AsyncSession, feeds: list[dict] | None = None,
    ) -> dict:
        stats = self._empty_stats()

        target_feeds = feeds or ONG_FEEDS

        for feed_config in target_feeds:
            try:
                await self._process_feed(db, feed_config, stats)
            except Exception as e:
                stats["errors"] += 1
                logger.error("ONG %s: erreur: %s", feed_config["name"], e)

        await db.commit()
        logger.info(
            "ONG: %d nouveaux, %d ignores, %d erreurs (sur %d sources)",
            stats["new"], stats["skipped"], stats["errors"], len(target_feeds),
        )
        return stats

    async def _process_feed(
        self, db: AsyncSession, config: dict, stats: dict,
    ):
        """Traite un flux RSS d'ONG."""
        name = config["name"]
        url = config["url"]

        try:
            xml_bytes = await self._fetch_xml(url)
        except Exception as e:
            logger.warning("ONG %s: flux inaccessible: %s", name, e)
            stats["errors"] += 1
            return

        if not xml_bytes:
            return

        entries = parse_rss_entries(xml_bytes)

        for entry in entries[:20]:  # Max 20 par source
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
                author=config["type"],
            )
            db.add(article)
            await self._mark_seen(db, entry_url, "press_article", f"ong_{name}")
            stats["new"] += 1

        logger.debug("ONG %s: %d entries traitees", name, len(entries))

"""Collecteur Think Tanks — veille anticipation pré-législative.

Surveille les publications des principaux think tanks et organismes
de réflexion qui influencent la fabrique de la loi en France :
- Institut Montaigne
- Fondapol (Fondation pour l'innovation politique)
- IFRAP (Fondation IFRAP)
- Terra Nova (déjà dans presse.py, dédié ici pour anticipation)
- Fondation Jean Jaurès
- Institut de l'entreprise
- France Stratégie (déjà en presse, dédié ici)
- IRES (Institut de recherches économiques et sociales)

Les rapports sont stockés comme AnticipationReport (pas comme Texte).
"""

import hashlib
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.collectors.base import BaseCollector
from legix.collectors.rss_utils import fetch_rss
from legix.core.models import AnticipationReport

logger = logging.getLogger(__name__)


# --- Configuration des think tanks ---

THINK_TANK_FEEDS: list[dict] = [
    {
        "id": "terra_nova",
        "nom": "Terra Nova",
        "source_type": "think_tank",
        "feeds": ["https://tnova.fr/feed/"],
    },
    {
        "id": "france_strategie",
        "nom": "France Stratégie",
        "source_type": "think_tank",
        "feeds": ["https://www.strategie.gouv.fr/rss.xml"],
    },
    {
        "id": "fondapol",
        "nom": "Fondapol",
        "source_type": "think_tank",
        "feeds": ["https://www.fondapol.org/feed/"],
    },
    {
        "id": "jean_jaures",
        "nom": "Fondation Jean Jaurès",
        "source_type": "think_tank",
        "feeds": ["https://www.jean-jaures.org/feed/"],
    },
    {
        "id": "ifrap",
        "nom": "IFRAP",
        "source_type": "think_tank",
        "feeds": ["https://www.ifrap.org/feed"],
    },
    {
        "id": "institut_montaigne",
        "nom": "Institut Montaigne",
        "source_type": "think_tank",
        "feeds": ["https://www.institutmontaigne.org/feed"],
    },
    {
        "id": "ires",
        "nom": "IRES",
        "source_type": "think_tank",
        "feeds": ["https://www.ires.fr/feed"],
    },
    {
        "id": "institut_entreprise",
        "nom": "Institut de l'entreprise",
        "source_type": "think_tank",
        "feeds": ["https://www.institut-entreprise.fr/feed"],
    },
]


def _report_uid(source_id: str, url: str) -> str:
    """UID stable pour un rapport d'anticipation."""
    h = hashlib.md5(url.encode()).hexdigest()[:12]
    return f"ANTIC-{source_id.upper()}-{h}"


class ThinkTankCollector(BaseCollector):
    """Collecteur des publications de think tanks pour l'anticipation."""

    def get_source_name(self) -> str:
        return "think_tanks"

    async def collect(self, db: AsyncSession) -> dict:
        """Collecte les publications de tous les think tanks configurés."""
        stats = self._empty_stats()

        for source in THINK_TANK_FEEDS:
            source_id = source["id"]
            source_nom = source["nom"]
            source_type = source["source_type"]

            for feed_url in source["feeds"]:
                try:
                    items = await fetch_rss(feed_url)
                except Exception as e:
                    logger.debug("[think_tanks:%s] RSS échoué: %s", source_id, e)
                    stats["errors"] += 1
                    continue

                new_count = 0
                for item in items:
                    if not item.link:
                        continue

                    if await self._is_seen(db, item.link):
                        continue

                    # Vérifier si déjà en base via URL
                    existing = await db.execute(
                        select(AnticipationReport).where(
                            AnticipationReport.url == item.link
                        )
                    )
                    if existing.scalar_one_or_none():
                        await self._mark_seen(db, item.link, "anticipation", "")
                        continue

                    report = AnticipationReport(
                        source_type=source_type,
                        source_name=source_nom,
                        title=item.title or "",
                        url=item.link,
                        publication_date=item.pub_date,
                        author=item.description[:500] if item.description else "",
                        pipeline_stage="report",
                    )
                    db.add(report)
                    await self._mark_seen(db, item.link, "anticipation", "")

                    stats["new"] += 1
                    stats["new_uids"]["anticipation"].append(item.link)
                    stats["by_type"][source_id] += 1
                    new_count += 1

                if new_count > 0:
                    logger.info(
                        "[think_tanks:%s] %d nouvelles publications", source_id, new_count
                    )

            await db.commit()

        total = stats["new"]
        if total > 0:
            logger.info(
                "[think_tanks] Collecte terminée: %d nouvelles publications, par source: %s",
                total,
                dict(stats["by_type"]),
            )
        return stats

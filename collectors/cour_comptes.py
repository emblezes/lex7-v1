"""Collecteur Cour des Comptes — rapports et recommandations.

La Cour des Comptes publie des rapports qui influencent fortement
la législation (rapports annuels, référés, notes, rapports thématiques).

Source : RSS + scraping de ccomptes.fr
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

# Flux RSS de la Cour des comptes
COUR_COMPTES_FEEDS = [
    "https://www.ccomptes.fr/fr/rss.xml",
]

# Flux RSS des chambres régionales (optionnel)
CRC_FEEDS = [
    "https://www.ccomptes.fr/fr/chambre-regionale-des-comptes/rss.xml",
]


class CourComptesCollector(BaseCollector):
    """Collecteur des rapports de la Cour des Comptes."""

    def get_source_name(self) -> str:
        return "cour_comptes"

    async def collect(self, db: AsyncSession) -> dict:
        stats = self._empty_stats()

        for feed_url in COUR_COMPTES_FEEDS:
            try:
                items = await fetch_rss(feed_url)
            except Exception as e:
                logger.debug("[cour_comptes] RSS échoué: %s", e)
                stats["errors"] += 1
                # Fallback : scraping de la page de publications
                try:
                    await self._collect_from_html(db, stats)
                except Exception as e2:
                    logger.warning("[cour_comptes] Scraping aussi échoué: %s", e2)
                continue

            for item in items:
                if not item.link:
                    continue
                if await self._is_seen(db, item.link):
                    continue

                existing = await db.execute(
                    select(AnticipationReport).where(
                        AnticipationReport.url == item.link
                    )
                )
                if existing.scalar_one_or_none():
                    await self._mark_seen(db, item.link, "anticipation", "")
                    continue

                report = AnticipationReport(
                    source_type="rapport_inspection",
                    source_name="Cour des Comptes",
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
                stats["by_type"]["cour_comptes"] += 1

        await db.commit()

        if stats["new"] > 0:
            logger.info(
                "[cour_comptes] %d nouveaux rapports collectés", stats["new"]
            )
        return stats

    async def _collect_from_html(self, db: AsyncSession, stats: dict):
        """Fallback : scraping de la page publications si RSS échoue."""
        url = "https://www.ccomptes.fr/fr/publications"
        html = await self._fetch_text(url)
        if not html:
            return

        # Parse simple des liens vers les rapports
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        articles = soup.select("article a[href]") or soup.select(".views-row a[href]")

        for link in articles[:30]:  # Limiter aux 30 plus récents
            href = link.get("href", "")
            if not href:
                continue
            if not href.startswith("http"):
                href = f"https://www.ccomptes.fr{href}"

            if await self._is_seen(db, href):
                continue

            title = link.get_text(strip=True) or ""
            if not title or len(title) < 10:
                continue

            existing = await db.execute(
                select(AnticipationReport).where(AnticipationReport.url == href)
            )
            if existing.scalar_one_or_none():
                await self._mark_seen(db, href, "anticipation", "")
                continue

            report = AnticipationReport(
                source_type="rapport_inspection",
                source_name="Cour des Comptes",
                title=title,
                url=href,
                publication_date=datetime.utcnow(),
                pipeline_stage="report",
            )
            db.add(report)
            await self._mark_seen(db, href, "anticipation", "")

            stats["new"] += 1
            stats["new_uids"]["anticipation"].append(href)
            stats["by_type"]["cour_comptes_html"] += 1

        await db.commit()

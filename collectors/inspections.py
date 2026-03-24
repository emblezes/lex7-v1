"""Collecteur corps d'inspection — IGF, IGAS, IGA.

Les rapports des inspections générales sont souvent précurseurs
de réformes législatives. Ils identifient les dysfonctionnements
et formulent des recommandations reprises par le législateur.

Sources :
- IGF (Inspection Générale des Finances) : igf.finances.gouv.fr
- IGAS (Inspection Générale des Affaires Sociales) : igas.gouv.fr
- IGA (Inspection Générale de l'Administration) : interieur.gouv.fr/IGA
"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.collectors.base import BaseCollector
from legix.core.models import AnticipationReport

logger = logging.getLogger(__name__)

# Sources d'inspection avec leurs pages de publications
INSPECTION_SOURCES = [
    {
        "id": "igf",
        "nom": "IGF",
        "source_type": "rapport_inspection",
        "url": "https://www.igf.finances.gouv.fr/rapports-publics",
        "rss": None,  # Pas de RSS, scraping nécessaire
    },
    {
        "id": "igas",
        "nom": "IGAS",
        "source_type": "rapport_inspection",
        "url": "https://www.igas.gouv.fr/rapports-publics",
        "rss": "https://www.igas.gouv.fr/spip.php?page=backend",
    },
    {
        "id": "iga",
        "nom": "IGA",
        "source_type": "rapport_inspection",
        "url": "https://www.interieur.gouv.fr/Publications/Rapports-de-l-IGA",
        "rss": None,
    },
]


class InspectionsCollector(BaseCollector):
    """Collecteur des rapports des corps d'inspection."""

    def get_source_name(self) -> str:
        return "inspections"

    async def collect(self, db: AsyncSession) -> dict:
        stats = self._empty_stats()

        for source in INSPECTION_SOURCES:
            source_id = source["id"]
            source_nom = source["nom"]

            # Essayer RSS d'abord si disponible
            if source.get("rss"):
                try:
                    from legix.collectors.rss_utils import fetch_rss
                    items = await fetch_rss(source["rss"])
                    for item in items:
                        if not item.link:
                            continue
                        await self._process_report(
                            db, stats, source_id, source_nom,
                            item.title, item.link, item.pub_date,
                            item.description,
                        )
                    await db.commit()
                    continue
                except Exception as e:
                    logger.debug("[inspections:%s] RSS échoué: %s", source_id, e)

            # Fallback : scraping de la page publications
            try:
                await self._scrape_publications(db, stats, source)
            except Exception as e:
                logger.warning("[inspections:%s] Scraping échoué: %s", source_id, e)
                stats["errors"] += 1

        total = stats["new"]
        if total > 0:
            logger.info(
                "[inspections] %d nouveaux rapports, par source: %s",
                total, dict(stats["by_type"]),
            )
        return stats

    async def _process_report(
        self, db: AsyncSession, stats: dict,
        source_id: str, source_nom: str,
        title: str, url: str, pub_date: datetime | None,
        description: str = "",
    ):
        """Traite un rapport individuel."""
        if not url or await self._is_seen(db, url):
            return

        existing = await db.execute(
            select(AnticipationReport).where(AnticipationReport.url == url)
        )
        if existing.scalar_one_or_none():
            await self._mark_seen(db, url, "anticipation", "")
            return

        report = AnticipationReport(
            source_type="rapport_inspection",
            source_name=source_nom,
            title=title or "",
            url=url,
            publication_date=pub_date or datetime.utcnow(),
            author=description[:500] if description else "",
            pipeline_stage="report",
        )
        db.add(report)
        await self._mark_seen(db, url, "anticipation", "")

        stats["new"] += 1
        stats["new_uids"]["anticipation"].append(url)
        stats["by_type"][source_id] += 1

    async def _scrape_publications(self, db: AsyncSession, stats: dict, source: dict):
        """Scraping de la page de publications d'un corps d'inspection."""
        html = await self._fetch_text(source["url"])
        if not html:
            return

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        # Chercher des liens vers des rapports (sélecteurs génériques)
        links = (
            soup.select("article a[href]")
            or soup.select(".views-row a[href]")
            or soup.select(".node a[href]")
            or soup.select("h2 a[href], h3 a[href]")
        )

        source_id = source["id"]
        source_nom = source["nom"]
        base_url = source["url"].rsplit("/", 1)[0]

        for link in links[:25]:
            href = link.get("href", "")
            if not href:
                continue
            if not href.startswith("http"):
                href = f"{base_url}/{href.lstrip('/')}"

            title = link.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            await self._process_report(
                db, stats, source_id, source_nom, title, href, None
            )

        await db.commit()

"""Collecteur consultations publiques — CNIL, AMF, ARCEP, Commission EU, etc.

Surveille les consultations ouvertes auxquelles le client peut contribuer.
"""

import hashlib
import json
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from legix.collectors.base import BaseCollector
from legix.collectors.rss_utils import parse_rss_entries
from legix.core.models import AnticipationReport

logger = logging.getLogger(__name__)

# Sources de consultations publiques
CONSULTATION_SOURCES = [
    # Regulateurs francais
    {
        "name": "CNIL",
        "url": "https://www.cnil.fr/fr/rss.xml",
        "type": "regulateur",
        "themes": ["numerique/tech"],
        "filter_keywords": ["consultation", "appel", "contribution", "avis"],
    },
    {
        "name": "AMF",
        "url": "https://www.amf-france.org/fr/rss",
        "type": "regulateur",
        "themes": ["finance"],
        "filter_keywords": ["consultation", "appel", "contribution"],
    },
    {
        "name": "ARCEP",
        "url": "https://www.arcep.fr/actualites/les-consultations-publiques-de-larcep.rss",
        "type": "regulateur",
        "themes": ["numerique/tech"],
        "filter_keywords": [],  # Flux dedie aux consultations
    },
    {
        "name": "ADEME",
        "url": "https://www.ademe.fr/feed/",
        "type": "agence",
        "themes": ["environnement/climat", "energie"],
        "filter_keywords": ["consultation", "appel", "avis"],
    },
    {
        "name": "Autorite de la concurrence",
        "url": "https://www.autoritedelaconcurrence.fr/fr/rss.xml",
        "type": "regulateur",
        "themes": ["commerce", "industrie"],
        "filter_keywords": ["consultation", "avis", "enquete"],
    },
    # Commission europeenne — Have Your Say
    {
        "name": "Commission EU - Have Your Say",
        "url": "https://ec.europa.eu/info/law/better-regulation/brp/consultation/rss",
        "type": "commission_eu",
        "themes": [],  # Tous themes
        "filter_keywords": [],
    },
    # Vie Publique (service d'information du gouvernement)
    {
        "name": "Vie Publique",
        "url": "https://www.vie-publique.fr/rss/consultations.xml",
        "type": "gouvernement",
        "themes": [],
        "filter_keywords": [],
    },
]


class ConsultationsCollector(BaseCollector):
    """Collecte les consultations publiques ouvertes."""

    def get_source_name(self) -> str:
        return "consultations"

    async def collect(
        self, db: AsyncSession, sources: list[dict] | None = None,
    ) -> dict:
        stats = self._empty_stats()

        target_sources = sources or CONSULTATION_SOURCES

        for source in target_sources:
            try:
                await self._process_source(db, source, stats)
            except Exception as e:
                stats["errors"] += 1
                logger.error("Consultation %s: erreur: %s", source["name"], e)

        await db.commit()
        logger.info(
            "Consultations: %d nouvelles, %d ignorees, %d erreurs",
            stats["new"], stats["skipped"], stats["errors"],
        )
        return stats

    async def _process_source(
        self, db: AsyncSession, source: dict, stats: dict,
    ):
        """Traite une source de consultations."""
        name = source["name"]

        try:
            xml_bytes = await self._fetch_xml(source["url"])
        except Exception:
            logger.warning("Consultation %s: source inaccessible", name)
            stats["errors"] += 1
            return

        if not xml_bytes:
            return

        entries = parse_rss_entries(xml_bytes)
        keywords = source.get("filter_keywords", [])

        for entry in entries[:15]:
            entry_url = entry.get("link", "")
            if not entry_url:
                continue

            # Filtrer par mots-cles si necessaire
            title = entry.get("title", "").lower()
            summary = entry.get("summary", "").lower()
            if keywords:
                if not any(kw in title or kw in summary for kw in keywords):
                    continue

            if await self._is_seen(db, entry_url):
                stats["skipped"] += 1
                continue

            uid = f"CONSULT_{hashlib.md5(entry_url.encode()).hexdigest()[:12]}"

            # Stocker comme AnticipationReport (consultation = signal pre-legislatif)
            report = AnticipationReport(
                uid=uid,
                source_type="consultation",
                source_name=name,
                title=entry.get("title", ""),
                url=entry_url,
                published_at=entry.get("published"),
                content_snippet=entry.get("summary", "")[:2000],
                themes=json.dumps(source["themes"], ensure_ascii=False),
                policy_stage="consultation",
                legislative_probability=0.6,  # Les consultations deviennent souvent des reglements
            )
            db.add(report)
            await self._mark_seen(db, entry_url, "anticipation_report", uid)
            stats["new"] += 1
            stats["new_uids"].append(uid)

        logger.debug("Consultation %s: %d entries", name, len(entries))

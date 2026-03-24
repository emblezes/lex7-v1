"""Collecteur EUR-Lex — legislation europeenne via RSS.

EUR-Lex fournit des flux RSS predetermines pour chaque categorie :
- Legislation du Parlement europeen et du Conseil
- Propositions de la Commission
- Actes delegues et d'execution
- Journal officiel de l'UE (JOUE)

Les flux sont publics, pas d'authentification requise.
Format : RSS standard avec liens vers les textes complets sur eur-lex.europa.eu.
"""

import hashlib
import logging
import re
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from legix.collectors.base import BaseCollector
from legix.collectors.rss_utils import fetch_rss
from legix.core.models import Texte

logger = logging.getLogger(__name__)


# Flux RSS predetermines EUR-Lex
# Source : https://eur-lex.europa.eu/content/help/search/predefined-rss.html
EURLEX_FEEDS: list[dict] = [
    {
        "id": "legislation_pe_conseil",
        "label": "Legislation PE et Conseil",
        "type_code": "REGL_EU",
        "type_libelle": "Reglements et directives EU",
        "url": "https://eur-lex.europa.eu/EN/display-feed.rss?rssId=161",
    },
    {
        "id": "propositions_commission",
        "label": "Propositions de la Commission",
        "type_code": "PROP_EU",
        "type_libelle": "Proposition de la Commission",
        "url": "https://eur-lex.europa.eu/EN/display-feed.rss?rssId=162",
    },
    {
        "id": "actes_delegues",
        "label": "Actes delegues et d'execution",
        "type_code": "ADEL_EU",
        "type_libelle": "Acte delegue EU",
        "url": "https://eur-lex.europa.eu/EN/display-feed.rss?rssId=163",
    },
    {
        "id": "accords_internationaux",
        "label": "Accords internationaux",
        "type_code": "AINT_EU",
        "type_libelle": "Accord international EU",
        "url": "https://eur-lex.europa.eu/EN/display-feed.rss?rssId=164",
    },
    {
        "id": "joue_l",
        "label": "JOUE serie L (legislation)",
        "type_code": "JOUE_L",
        "type_libelle": "Journal officiel UE (L)",
        "url": "https://eur-lex.europa.eu/EN/display-feed.rss?rssId=221",
    },
    {
        "id": "joue_c",
        "label": "JOUE serie C (communications)",
        "type_code": "JOUE_C",
        "type_libelle": "Journal officiel UE (C)",
        "url": "https://eur-lex.europa.eu/EN/display-feed.rss?rssId=222",
    },
]


def _extract_celex(url: str) -> str | None:
    """Extrait le numero CELEX d'une URL EUR-Lex."""
    # Pattern : /legal-content/FR/TXT/?uri=CELEX:32024R1234
    match = re.search(r"CELEX[:%](\w+)", url)
    if match:
        return match.group(1)
    # Pattern : /eli/reg/2024/1234
    match = re.search(r"/eli/(\w+/\d{4}/\d+)", url)
    if match:
        return match.group(1)
    return None


def _uid_from_url(url: str) -> str:
    """Genere un UID stable."""
    celex = _extract_celex(url)
    if celex:
        return f"EURLEX-{celex}"
    h = hashlib.md5(url.encode()).hexdigest()[:12]
    return f"EURLEX-{h}"


class EurLexCollector(BaseCollector):
    """Collecteur EUR-Lex via flux RSS predetermines."""

    def get_source_name(self) -> str:
        return "eurlex"

    async def collect(self, db: AsyncSession) -> dict:
        """Collecte les textes EU depuis les flux RSS EUR-Lex."""
        stats = self._empty_stats()

        for feed_cfg in EURLEX_FEEDS:
            feed_id = feed_cfg["id"]
            feed_url = feed_cfg["url"]
            type_code = feed_cfg["type_code"]
            type_libelle = feed_cfg["type_libelle"]

            try:
                items = await fetch_rss(feed_url)
            except Exception as e:
                logger.debug("[eurlex:%s] RSS echoue: %s", feed_id, e)
                stats["errors"] += 1
                continue

            new_count = 0
            for item in items:
                if not item.link:
                    continue

                if await self._is_seen(db, item.link):
                    continue

                uid = _uid_from_url(item.link)

                existing = await db.get(Texte, uid)
                if existing:
                    await self._mark_seen(db, item.link, type_code, uid)
                    continue

                titre = item.title or ""
                texte = Texte(
                    uid=uid,
                    denomination=type_libelle,
                    titre=titre,
                    titre_court=titre[:120] if titre else "",
                    type_code=type_code,
                    type_libelle=type_libelle,
                    date_depot=item.pub_date,
                    date_publication=item.pub_date,
                    source="eurlex",
                    url_source=item.link,
                    auteur_texte=item.description[:2000] if item.description else "",
                )
                db.add(texte)
                await self._mark_seen(db, item.link, type_code, uid)

                stats["new"] += 1
                stats["new_uids"]["texte"].append(uid)
                stats["by_type"][type_code] += 1
                new_count += 1

            if new_count > 0:
                logger.info("[eurlex:%s] %d nouveaux textes", feed_id, new_count)

            await db.commit()

        total = stats["new"]
        if total > 0:
            logger.info(
                "[eurlex] Collecte terminee: %d nouveaux, par type: %s",
                total, dict(stats["by_type"]),
            )
        else:
            logger.info("[eurlex] Aucun nouveau texte EU")

        return stats

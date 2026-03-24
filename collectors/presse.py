"""Collecteur Presse specialisee — veille contextuelle via RSS.

Surveille les flux RSS des medias et think tanks specialises :
Contexte, Acteurs Publics, Euractiv, Les Echos, Le Monde, etc.

Les articles sont stockes comme Texte avec source="presse".
"""

import hashlib
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from legix.collectors.base import BaseCollector
from legix.collectors.rss_utils import fetch_rss
from legix.core.models import Texte

logger = logging.getLogger(__name__)


# --- Flux RSS presse specialisee ---

PRESSE_FEEDS: list[dict] = [
    # --- Fonctionnels (verifies) ---
    # Europe
    {
        "id": "touteleurope",
        "nom": "Toute l'Europe",
        "feeds": ["https://www.touteleurope.eu/feed/"],
    },
    # Politique
    {
        "id": "lemonde_politique",
        "nom": "Le Monde Politique",
        "feeds": ["https://www.lemonde.fr/politique/rss_full.xml"],
    },
    # Think tanks
    {
        "id": "terra_nova",
        "nom": "Terra Nova",
        "feeds": ["https://tnova.fr/feed/"],
    },
    {
        "id": "france_strategie",
        "nom": "France Strategie",
        "feeds": ["https://www.strategie.gouv.fr/rss.xml"],
    },
    # --- 403/404 (acces bloque ou URL changee) ---
    # Contexte : paywall + pas de RSS public
    # Euractiv FR : 403 (user-agent bloque)
    # Les Echos : 403 (user-agent bloque)
    # L'Usine Nouvelle : 403 (user-agent bloque)
    # Institut Montaigne : 404 (RSS supprime)
    # Acteurs Publics : RSS vide (0 items)
    # Vie publique : 502 intermittent
]


def _uid_from_url(source_id: str, url: str) -> str:
    """Genere un UID stable a partir de l'URL."""
    h = hashlib.md5(url.encode()).hexdigest()[:12]
    return f"PRESSE-{source_id.upper()}-{h}"


class PresseCollector(BaseCollector):
    """Collecteur presse specialisee via RSS."""

    def get_source_name(self) -> str:
        return "presse"

    async def collect(self, db: AsyncSession) -> dict:
        """Collecte les articles de tous les flux presse configures."""
        stats = self._empty_stats()

        for source in PRESSE_FEEDS:
            source_id = source["id"]
            source_nom = source["nom"]

            for feed_url in source["feeds"]:
                try:
                    items = await fetch_rss(feed_url)
                except Exception as e:
                    logger.debug("[presse:%s] RSS echoue: %s", source_id, e)
                    stats["errors"] += 1
                    continue

                new_count = 0
                for item in items:
                    if not item.link:
                        continue

                    if await self._is_seen(db, item.link):
                        continue

                    uid = _uid_from_url(source_id, item.link)

                    existing = await db.get(Texte, uid)
                    if existing:
                        await self._mark_seen(db, item.link, "article", uid)
                        continue

                    titre = item.title or ""
                    texte = Texte(
                        uid=uid,
                        denomination=f"Article {source_nom}",
                        titre=titre,
                        titre_court=titre[:120] if titre else "",
                        type_code="PRESSE",
                        type_libelle=source_nom,
                        date_depot=item.pub_date,
                        date_publication=item.pub_date,
                        source="presse",
                        url_source=item.link,
                        auteur_texte=item.description[:2000] if item.description else "",
                    )
                    db.add(texte)
                    await self._mark_seen(db, item.link, "article", uid)

                    stats["new"] += 1
                    stats["new_uids"]["texte"].append(uid)
                    stats["by_type"][source_id] += 1
                    new_count += 1

                if new_count > 0:
                    logger.info("[presse:%s] %d nouveaux articles", source_id, new_count)

            await db.commit()

        total = stats["new"]
        if total > 0:
            logger.info(
                "[presse] Collecte terminee: %d nouveaux articles, par source: %s",
                total, dict(stats["by_type"]),
            )
        return stats

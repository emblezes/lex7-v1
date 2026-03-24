"""Collecteur Regulateurs francais — veille via RSS.

Surveille les publications des autorites de regulation independantes :
CNIL, AMF, ARCEP, ADLC, HAS, ANSM, CRE, ARCOM, ACPR, ANSES, etc.

Chaque regulateur a 1-3 flux RSS. Les items sont stockes comme Texte
avec source="regulateur" et type_code specifique au regulateur.
"""

import hashlib
import json
import logging
import re
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from legix.collectors.base import BaseCollector
from legix.collectors.rss_utils import RSSItem, fetch_rss
from legix.core.models import Texte

logger = logging.getLogger(__name__)


# --- Configuration des flux RSS par regulateur ---

REGULATEUR_FEEDS: list[dict] = [
    # --- RSS verifies et fonctionnels ---
    {
        "id": "cnil",
        "nom": "CNIL",
        "type_code": "CNIL",
        "type_libelle": "Decision CNIL",
        "feeds": ["https://www.cnil.fr/fr/rss.xml"],
    },
    {
        "id": "amf",
        "nom": "AMF",
        "type_code": "AMF",
        "type_libelle": "Publication AMF",
        "feeds": ["https://www.amf-france.org/fr/flux-rss/display/21"],
    },
    {
        "id": "arcep",
        "nom": "ARCEP",
        "type_code": "ARCEP",
        "type_libelle": "Decision ARCEP",
        "feeds": [
            "https://www.arcep.fr/actualites/suivre-actualite-regulation-arcep/communiques-de-presse/rss.xml",
            "https://www.arcep.fr/actualites/suivre-actualite-regulation-arcep/avis-et-decisions/rss.xml",
        ],
    },
    {
        "id": "adlc",
        "nom": "Autorite de la concurrence",
        "type_code": "ADLC",
        "type_libelle": "Decision ADLC",
        "feeds": ["https://www.autoritedelaconcurrence.fr/rss.xml"],
    },
    {
        "id": "ansm",
        "nom": "ANSM",
        "type_code": "ANSM",
        "type_libelle": "Publication ANSM",
        "feeds": [
            "https://ansm.sante.fr/rss/actualites",
            "https://ansm.sante.fr/rss/informations_securite",
        ],
    },
    {
        "id": "arcom",
        "nom": "ARCOM",
        "type_code": "ARCOM",
        "type_libelle": "Decision ARCOM",
        "feeds": ["https://www.arcom.fr/rss.xml"],
    },
    {
        "id": "hcc",
        "nom": "Haut Conseil pour le Climat",
        "type_code": "HCC",
        "type_libelle": "Avis HCC",
        "feeds": ["https://www.hautconseilclimat.fr/feed/"],
    },
    {
        "id": "ce",
        "nom": "Conseil d'Etat",
        "type_code": "CE",
        "type_libelle": "Decision Conseil d'Etat",
        "feeds": [
            "https://www.conseil-etat.fr/rss/actualites-rss",
            "https://www.conseil-etat.fr/rss/avis-rss",
        ],
    },
    {
        "id": "cdc",
        "nom": "Cour des comptes",
        "type_code": "CDC",
        "type_libelle": "Rapport Cour des comptes",
        "feeds": ["https://www.ccomptes.fr/fr/rss/general"],
    },
    {
        "id": "ddd",
        "nom": "Defenseur des droits",
        "type_code": "DDD",
        "type_libelle": "Decision Defenseur des droits",
        "feeds": ["https://www.defenseurdesdroits.fr/rss.xml"],
    },
    # --- Sans RSS (scraping necessaire) ---
    # CRE : pas de RSS — scraper https://www.cre.fr/actualites
    # ACPR : pas de RSS — scraper https://acpr.banque-france.fr/fr/actualites
    # HAS : RSS JS-only — scraper https://www.has-sante.fr/
]


def _uid_from_url(regulateur_id: str, url: str) -> str:
    """Genere un UID stable a partir de l'URL."""
    h = hashlib.md5(url.encode()).hexdigest()[:12]
    return f"REG-{regulateur_id.upper()}-{h}"


class RegulateursCollector(BaseCollector):
    """Collecteur multi-regulateurs via RSS."""

    def get_source_name(self) -> str:
        return "regulateur"

    async def collect(self, db: AsyncSession) -> dict:
        """Collecte les publications de tous les regulateurs configures."""
        stats = self._empty_stats()

        for reg in REGULATEUR_FEEDS:
            reg_id = reg["id"]
            reg_nom = reg["nom"]
            type_code = reg["type_code"]
            type_libelle = reg["type_libelle"]

            for feed_url in reg["feeds"]:
                try:
                    items = await fetch_rss(feed_url)
                except Exception as e:
                    logger.debug("[regulateur:%s] RSS echoue %s: %s", reg_id, feed_url, e)
                    stats["errors"] += 1
                    continue

                new_count = 0
                for item in items:
                    if not item.link:
                        continue

                    # Deduplication
                    if await self._is_seen(db, item.link):
                        continue

                    uid = _uid_from_url(reg_id, item.link)

                    # Verifier si deja en base
                    existing = await db.get(Texte, uid)
                    if existing:
                        await self._mark_seen(db, item.link, type_code, uid)
                        continue

                    # Stocker comme Texte
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
                        source="regulateur",
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
                    logger.info(
                        "[regulateur:%s] %d nouvelles publications",
                        reg_id, new_count,
                    )

            await db.commit()

        total = stats["new"]
        if total > 0:
            logger.info(
                "[regulateurs] Collecte terminee: %d nouveaux, %d erreurs, par type: %s",
                total, stats["errors"], dict(stats["by_type"]),
            )
        else:
            logger.info("[regulateurs] Aucune nouvelle publication")

        return stats

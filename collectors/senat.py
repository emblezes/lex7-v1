"""Collecteur Senat — veille legislative via RSS + scraping HTML/JSON.

Adapte de LegisAPI en mode async pour LegiX.

Sources :
- 3 flux RSS (textes, rapports, presse)
- JSON amendements pour chaque texte suivi
- HTML parsing (BeautifulSoup) pour les pages textes, reunions, comptes rendus
"""

import json
import logging
import re
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.collectors.base import BaseCollector
from legix.collectors.rss_utils import RSSItem, fetch_rss
from legix.core.config import settings
from legix.core.models import (
    Amendement,
    CompteRendu,
    Reunion,
    SeenPublication,
    Texte,
)
from legix.parsers.senat_amendement import parse_senat_amendements_batch
from legix.parsers.senat_compte_rendu import parse_senat_cr
from legix.parsers.senat_reunion import parse_senat_reunion
from legix.parsers.senat_texte import parse_senat_texte

logger = logging.getLogger(__name__)

# Flux RSS du Senat
RSS_FEEDS = [
    ("textes", "https://www.senat.fr/rss/textes.rss"),
    ("rapports", "https://www.senat.fr/rss/rapports.rss"),
    ("presse", "https://www.senat.fr/rss/presse.rss"),
]

# Patterns URL → type de document
URL_TYPE_PATTERNS = [
    (re.compile(r"/leg/p[pj]l"), "texte"),
    (re.compile(r"/leg/tas"), "texte"),
    (re.compile(r"/rap/l"), "texte"),  # Rapports → stockes comme textes
    (re.compile(r"/cra/"), "compte_rendu"),
    (re.compile(r"/seances/"), "compte_rendu"),
    (re.compile(r"/amendements/"), "amendement"),
    (re.compile(r"/commission/"), "reunion"),
]

# Session parlementaire courante
CURRENT_SESSION = "2025-2026"


class SenatCollector(BaseCollector):
    """Collecteur Senat async — RSS + HTML scraping + JSON amendements."""

    def get_source_name(self) -> str:
        return "senat"

    def _detect_type(self, url: str) -> str | None:
        """Detecte le type de document depuis l'URL."""
        for pattern, doc_type in URL_TYPE_PATTERNS:
            if pattern.search(url):
                return doc_type
        return None

    async def _get_new_rss_items(self, db: AsyncSession) -> list[RSSItem]:
        """Poll tous les flux RSS et retourne les items non encore vus."""
        all_items: list[RSSItem] = []
        for label, feed_url in RSS_FEEDS:
            try:
                items = await fetch_rss(feed_url)
                all_items.extend(items)
                logger.debug("[senat] RSS %s: %d items", label, len(items))
            except Exception as e:
                logger.warning("[senat] RSS %s erreur: %s", label, e)
                continue

        # Dedupliquer par guid/link
        seen_guids: set[str] = set()
        unique: list[RSSItem] = []
        for item in all_items:
            key = item.guid or item.link
            if key in seen_guids:
                continue
            seen_guids.add(key)
            unique.append(item)

        # Filtrer les items deja vus en base
        new_items: list[RSSItem] = []
        for item in unique:
            if not item.link:
                continue
            if not await self._is_seen(db, item.link):
                new_items.append(item)

        logger.info("[senat] RSS: %d items dont %d nouveaux", len(unique), len(new_items))
        return new_items

    async def _store_texte(self, db: AsyncSession, data: dict) -> str:
        """Stocke un texte Senat en base."""
        existing = await db.get(Texte, data["uid"])
        if existing:
            for key in ["titre", "titre_court", "date_publication"]:
                if data.get(key):
                    setattr(existing, key, data[key])
            return "updated"

        texte = Texte(
            uid=data["uid"],
            legislature=data.get("legislature"),
            denomination=data["denomination"],
            titre=data["titre"],
            titre_court=data["titre_court"],
            type_code=data["type_code"],
            type_libelle=data["type_libelle"],
            date_depot=data.get("date_depot"),
            date_publication=data.get("date_publication"),
            dossier_ref=data.get("dossier_ref"),
            organe_ref=data.get("organe_ref"),
            source="senat",
            url_source=data.get("url_source"),
            auteur_texte=data.get("auteur_texte"),
        )
        db.add(texte)
        return "new"

    async def _store_amendement(self, db: AsyncSession, data: dict) -> str:
        """Stocke un amendement Senat en base."""
        existing = await db.get(Amendement, data["uid"])
        if existing:
            old_sort = existing.sort or ""
            new_sort = data.get("sort", "") or ""
            sort_changed = old_sort != new_sort and new_sort

            for key in ["etat", "sort", "date_sort", "dispositif", "expose_sommaire"]:
                if data.get(key):
                    setattr(existing, key, data[key])

            if sort_changed:
                existing.score_impact = None

            return "updated"

        amdt = Amendement(
            uid=data["uid"],
            legislature=data.get("legislature"),
            numero=data["numero"],
            texte_ref=data.get("texte_ref"),
            organe_examen=data.get("organe_examen", "Senat"),
            auteur_ref=data.get("auteur_ref"),
            auteur_type=data.get("auteur_type"),
            groupe_ref=data.get("groupe_ref"),
            article_vise=data.get("article_vise"),
            dispositif=data.get("dispositif"),
            expose_sommaire=data.get("expose_sommaire"),
            date_depot=data.get("date_depot"),
            etat=data.get("etat"),
            sort=data.get("sort"),
            source="senat",
            url_source=data.get("url_source"),
            auteur_nom=data.get("auteur_nom"),
            groupe_nom=data.get("groupe_nom"),
        )
        db.add(amdt)
        return "new"

    async def _store_reunion(self, db: AsyncSession, data: dict) -> str:
        """Stocke une reunion Senat en base."""
        existing = await db.get(Reunion, data["uid"])
        if existing:
            for key in ["etat", "odj", "lieu", "date_debut"]:
                if data.get(key):
                    setattr(existing, key, data[key])
            return "updated"

        reunion = Reunion(
            uid=data["uid"],
            date_debut=data.get("date_debut"),
            lieu=data.get("lieu"),
            organe_ref=data.get("organe_ref"),
            etat=data.get("etat"),
            odj=data.get("odj"),
            source="senat",
            url_source=data.get("url_source"),
            commission_nom=data.get("commission_nom"),
        )
        db.add(reunion)
        return "new"

    async def _store_compte_rendu(self, db: AsyncSession, data: dict) -> str:
        """Stocke un compte rendu Senat en base."""
        existing = await db.get(CompteRendu, data["uid"])
        if existing:
            for key in ["sommaire", "etat"]:
                if data.get(key):
                    setattr(existing, key, data[key])
            return "updated"

        cr = CompteRendu(
            uid=data["uid"],
            date_seance=data.get("date_seance"),
            num_seance=data.get("num_seance"),
            etat=data.get("etat"),
            sommaire=data.get("sommaire"),
            source="senat",
            url_source=data.get("url_source"),
        )
        db.add(cr)
        return "new"

    def _record_stat(self, stats: dict, result: str, doc_type: str, uid: str):
        """Enregistre une statistique de collecte."""
        if result == "new":
            stats["new"] += 1
            stats["new_uids"][doc_type].append(uid)
        else:
            stats["updated"] += 1
            stats["updated_uids"][doc_type].append(uid)
        stats["by_type"][doc_type] += 1

    async def _process_item(self, db: AsyncSession, item: RSSItem, stats: dict):
        """Traite un item RSS : detecte le type, telecharge, parse, stocke."""
        url = item.link
        doc_type = self._detect_type(url)

        if doc_type is None:
            stats["skipped"] += 1
            await self._mark_seen(db, url, "unknown", "")
            return

        try:
            if doc_type == "texte":
                html = await self._fetch_text(url)
                if not html:
                    stats["errors"] += 1
                    return
                data = parse_senat_texte(url, html)
                result = await self._store_texte(db, data)
                self._record_stat(stats, result, "texte", data["uid"])

            elif doc_type == "compte_rendu":
                html = await self._fetch_text(url)
                if not html:
                    stats["errors"] += 1
                    return
                data = parse_senat_cr(url, html)
                result = await self._store_compte_rendu(db, data)
                self._record_stat(stats, result, "compte_rendu", data["uid"])

            elif doc_type == "reunion":
                html = await self._fetch_text(url)
                if not html:
                    stats["errors"] += 1
                    return
                data = parse_senat_reunion(url, html)
                result = await self._store_reunion(db, data)
                self._record_stat(stats, result, "reunion", data["uid"])

            elif doc_type == "amendement":
                json_data = await self._fetch_json(url)
                if not json_data:
                    stats["errors"] += 1
                    return
                amendements = parse_senat_amendements_batch(json_data, CURRENT_SESSION)
                texte_ref = self._resolve_texte_ref(url)
                for amdt_data in amendements:
                    if texte_ref and not amdt_data.get("texte_ref"):
                        amdt_data["texte_ref"] = texte_ref
                    result = await self._store_amendement(db, amdt_data)
                    self._record_stat(stats, result, "amendement", amdt_data["uid"])

            await self._mark_seen(db, url, doc_type, "")

        except Exception as e:
            stats["errors"] += 1
            logger.warning("[senat] Erreur traitement %s: %s", url, e)

    async def _collect_amendements_for_textes(self, db: AsyncSession, stats: dict):
        """Cherche les amendements pour les textes Senat recents (30 derniers jours)."""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=30)
        result = await db.execute(
            select(Texte).where(
                Texte.source == "senat",
                Texte.created_at >= cutoff,
            )
        )
        textes = result.scalars().all()

        for texte in textes:
            # Extraire le numero du texte depuis l'UID (SENATTXT-2025-2026-25-440)
            match = re.search(r"SENATTXT-\d{4}-\d{4}-(\d{2}-\d+)$", texte.uid)
            if not match:
                continue

            numero = match.group(1)
            amdt_url = f"{settings.senat_base_url}/amendements/{numero}/jeu_complet.json"

            if await self._is_seen(db, amdt_url):
                continue

            json_data = await self._fetch_json(amdt_url)
            if not json_data:
                continue

            amendements = parse_senat_amendements_batch(json_data, CURRENT_SESSION)
            for amdt_data in amendements:
                amdt_data["texte_ref"] = texte.uid
                result = await self._store_amendement(db, amdt_data)
                self._record_stat(stats, result, "amendement", amdt_data["uid"])

            await self._mark_seen(db, amdt_url, "amendement_batch", texte.uid)
            logger.info(
                "[senat] %d amendements collectes pour %s",
                len(amendements), texte.uid,
            )

    def _resolve_texte_ref(self, url: str) -> str | None:
        """Tente de trouver le texte parent depuis l'URL d'amendement."""
        match = re.search(r"/amendements/(\d{4}-\d{4})/(\d{2}-\d+)", url)
        if match:
            session_str, numero = match.group(1), match.group(2)
            return f"SENATTXT-{session_str}-{numero}"
        return None

    async def collect(self, db: AsyncSession) -> dict:
        """Collecte complete : RSS + amendements pour textes connus."""
        stats = self._empty_stats()

        # 1. Poll RSS feeds → nouveaux items
        new_items = await self._get_new_rss_items(db)

        # 2. Traiter chaque item
        for item in new_items:
            await self._process_item(db, item, stats)

        await db.commit()

        # 3. Chercher les amendements pour les textes connus
        await self._collect_amendements_for_textes(db, stats)

        await db.commit()

        logger.info(
            "[senat] Collecte terminee: %d nouveaux, %d maj, %d erreurs",
            stats["new"], stats["updated"], stats["errors"],
        )
        return stats

"""Utilitaires RSS/Atom async — fetch et parse de flux."""

from dataclasses import dataclass
from datetime import datetime

import feedparser
import httpx


@dataclass
class RSSItem:
    """Item RSS/Atom normalise."""
    title: str
    link: str
    pub_date: datetime | None
    description: str
    guid: str


async def fetch_rss(url: str, timeout: float = 15.0) -> list[RSSItem]:
    """Telecharge et parse un flux RSS/Atom de maniere async.

    Returns:
        Liste de RSSItem triee par date decroissante.
    """
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()

    feed = feedparser.parse(response.text)
    items: list[RSSItem] = []

    for entry in feed.entries:
        pub_date = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                pub_date = datetime(*entry.published_parsed[:6])
            except (TypeError, ValueError):
                pass
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            try:
                pub_date = datetime(*entry.updated_parsed[:6])
            except (TypeError, ValueError):
                pass

        items.append(RSSItem(
            title=getattr(entry, "title", ""),
            link=getattr(entry, "link", ""),
            pub_date=pub_date,
            description=getattr(entry, "summary", getattr(entry, "description", "")),
            guid=getattr(entry, "id", getattr(entry, "link", "")),
        ))

    items.sort(key=lambda x: x.pub_date or datetime.min, reverse=True)
    return items


def parse_rss_entries(xml_bytes: bytes) -> list[dict]:
    """Parse du XML RSS/Atom brut en liste de dicts.

    Utilise par les collecteurs qui recoivent du XML via BaseCollector._fetch_xml().
    Retourne des dicts normalises {title, link, summary, published}.
    """
    feed = feedparser.parse(xml_bytes)
    entries = []

    for entry in feed.entries:
        pub_date = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                pub_date = datetime(*entry.published_parsed[:6])
            except (TypeError, ValueError):
                pass
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            try:
                pub_date = datetime(*entry.updated_parsed[:6])
            except (TypeError, ValueError):
                pass

        entries.append({
            "title": getattr(entry, "title", ""),
            "link": getattr(entry, "link", ""),
            "summary": getattr(entry, "summary", getattr(entry, "description", "")),
            "published": pub_date,
            "guid": getattr(entry, "id", getattr(entry, "link", "")),
        })

    return entries

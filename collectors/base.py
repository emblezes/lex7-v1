"""Classe de base pour les collecteurs de données parlementaires.

Fournit l'interface commune + utilitaires HTTP async pour tous les collecteurs.
"""

import logging
from abc import ABC, abstractmethod
from collections import defaultdict

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.models import SeenPublication

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    """Interface commune pour tous les collecteurs LegiX."""

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    @abstractmethod
    def get_source_name(self) -> str:
        """Identifiant de la source (ex: 'assemblee', 'senat', 'jorf')."""
        ...

    @abstractmethod
    async def collect(self, session: AsyncSession) -> dict:
        """Collecte les nouveaux documents et les stocke en base.

        Returns dict with stats:
            {"new": int, "updated": int, "skipped": int, "errors": int,
             "by_type": dict, "new_uids": dict}
        """
        ...

    def _empty_stats(self) -> dict:
        """Stats vides — point de depart pour chaque run."""
        return {
            "new": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
            "by_type": defaultdict(int),
            "new_uids": defaultdict(list),
            "updated_uids": defaultdict(list),
        }

    async def _get_client(self) -> httpx.AsyncClient:
        """Client HTTP reutilisable avec timeout."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={"User-Agent": "LegiX/1.0 (intelligence reglementaire)"},
            )
        return self._client

    async def _fetch_json(self, url: str, **kwargs) -> dict | list | None:
        """GET JSON avec gestion d'erreur."""
        client = await self._get_client()
        try:
            resp = await client.get(url, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning("[%s] HTTP %d sur %s", self.get_source_name(), e.response.status_code, url)
            return None
        except Exception as e:
            logger.warning("[%s] Erreur fetch %s: %s", self.get_source_name(), url, e)
            return None

    async def _fetch_text(self, url: str, **kwargs) -> str | None:
        """GET texte brut avec gestion d'erreur."""
        client = await self._get_client()
        try:
            resp = await client.get(url, **kwargs)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.warning("[%s] Erreur fetch %s: %s", self.get_source_name(), url, e)
            return None

    async def _fetch_xml(self, url: str, **kwargs) -> bytes | None:
        """GET XML brut (bytes) avec gestion d'erreur."""
        client = await self._get_client()
        try:
            resp = await client.get(url, **kwargs)
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            logger.warning("[%s] Erreur fetch %s: %s", self.get_source_name(), url, e)
            return None

    async def _is_seen(self, db: AsyncSession, url: str) -> bool:
        """Verifie si une URL a deja ete traitee."""
        result = await db.execute(
            select(SeenPublication).where(SeenPublication.url == url)
        )
        return result.scalar_one_or_none() is not None

    async def _mark_seen(
        self, db: AsyncSession, url: str, doc_type: str = "", doc_uid: str = ""
    ):
        """Marque une URL comme traitee."""
        from datetime import datetime
        pub = SeenPublication(
            url=url,
            document_type=doc_type,
            document_uid=doc_uid,
            first_seen=datetime.utcnow(),
        )
        db.add(pub)

    async def close(self):
        """Ferme le client HTTP."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

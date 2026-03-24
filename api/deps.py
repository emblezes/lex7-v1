"""Dépendances partagées pour les routes FastAPI."""

import jwt
from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.config import settings
from legix.core.database import get_db  # noqa: F401 — réexport pour les routes
from legix.core.models import ClientProfile


class PaginationParams:
    def __init__(
        self,
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=500),
    ):
        self.offset = offset
        self.limit = limit


async def verify_api_key(x_api_key: str = Header(default="")):
    """Vérifie la clé API si configurée."""
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Clé API invalide")


async def get_current_profile(
    authorization: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
) -> ClientProfile:
    """Décode le JWT et retourne le profil client authentifié.

    En mode dev (jwt_secret par défaut), si aucun token n'est fourni,
    retourne le premier profil actif pour faciliter le développement.
    """
    _is_dev = settings.jwt_secret == "legix-demo-secret-change-in-prod"

    if not authorization.startswith("Bearer "):
        if _is_dev:
            # Mode dev : retourner le premier profil actif
            result = await db.execute(
                select(ClientProfile).where(ClientProfile.is_active.is_(True)).limit(1)
            )
            profile = result.scalar_one_or_none()
            if profile:
                return profile
        raise HTTPException(status_code=401, detail="Token manquant")

    token = authorization[7:]
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        profile_id = payload.get("profile_id")
        if profile_id is None:
            raise HTTPException(status_code=401, detail="Token invalide")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expiré")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token invalide")

    result = await db.execute(
        select(ClientProfile).where(ClientProfile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=401, detail="Profil introuvable")
    return profile


async def get_optional_profile(
    authorization: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
) -> ClientProfile | None:
    """Retourne le profil si un token valide est fourni, None sinon."""
    if not authorization.startswith("Bearer "):
        return None
    try:
        return await get_current_profile(authorization=authorization, db=db)
    except HTTPException:
        return None

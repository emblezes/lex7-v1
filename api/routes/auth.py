"""Routes d'authentification et onboarding."""

import json
import logging
from datetime import datetime, timedelta

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.config import settings
from legix.core.database import get_db
from legix.core.models import ClientProfile, OnboardingJob
from legix.api.deps import get_current_profile
from legix.services.company_enrichment import enrich_and_build_profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


# --- Schemas ---

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    website: str | None = None
    sectors: list[str]

class LoginRequest(BaseModel):
    email: str
    password: str

class UpdateProfileRequest(BaseModel):
    description: str | None = None
    business_lines: list[str] | None = None
    products: list[str] | None = None
    regulatory_focus: list[str] | None = None
    context_note: str | None = None
    sectors: list[str] | None = None


# --- Helpers ---

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

def _create_token(profile_id: int) -> str:
    payload = {
        "profile_id": profile_id,
        "exp": datetime.utcnow() + timedelta(hours=settings.jwt_expiry_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

def _serialize_profile(p: ClientProfile) -> dict:
    """Sérialise un profil pour la réponse API."""
    def _parse_json(val):
        if not val:
            return []
        try:
            return json.loads(val) if isinstance(val, str) else val
        except (json.JSONDecodeError, TypeError):
            return []

    return {
        "id": p.id,
        "name": p.name,
        "email": p.email,
        "sectors": _parse_json(p.sectors),
        "business_lines": _parse_json(p.business_lines),
        "products": _parse_json(p.products),
        "regulatory_focus": _parse_json(p.regulatory_focus),
        "context_note": p.context_note,
        "description": p.description,
        "monitoring_explanation": p.monitoring_explanation,
        "site_web": p.site_web,
        "siren": p.siren,
        "chiffre_affaires": p.chiffre_affaires,
        "resultat_net": p.resultat_net,
        "effectifs": p.effectifs,
        "code_naf": p.code_naf,
        "siege_social": p.siege_social,
        "categorie_entreprise": p.categorie_entreprise,
        "dirigeants": _parse_json(p.dirigeants),
        "is_active": p.is_active,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


# --- Routes ---

@router.post("/register")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Inscription d'un nouveau prospect avec enrichissement automatique."""
    # Vérifier que l'email n'est pas déjà utilisé
    existing = await db.execute(
        select(ClientProfile).where(ClientProfile.email == req.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Cet email est déjà utilisé")

    # Enrichir le profil via API publique + Claude
    logger.info("Enrichissement du profil pour %s...", req.name)
    profile_data = await enrich_and_build_profile(
        company_name=req.name,
        email=req.email,
        sectors=req.sectors,
        website_url=req.website,
    )

    # Créer le profil
    profile = ClientProfile(
        password_hash=_hash_password(req.password),
        **profile_data,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    token = _create_token(profile.id)
    return {
        "token": token,
        "profile": _serialize_profile(profile),
    }


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Connexion avec email et mot de passe."""
    result = await db.execute(
        select(ClientProfile).where(ClientProfile.email == req.email)
    )
    profile = result.scalar_one_or_none()

    if not profile or not profile.password_hash:
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")

    if not _verify_password(req.password, profile.password_hash):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")

    token = _create_token(profile.id)
    return {
        "token": token,
        "profile": _serialize_profile(profile),
    }


@router.get("/me")
async def get_me(profile: ClientProfile = Depends(get_current_profile)):
    """Retourne le profil de l'utilisateur authentifié."""
    return _serialize_profile(profile)


@router.put("/profile")
async def update_profile(
    req: UpdateProfileRequest,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Met à jour la fiche entreprise (modification par le prospect)."""
    if req.description is not None:
        profile.description = req.description
    if req.business_lines is not None:
        profile.business_lines = json.dumps(req.business_lines, ensure_ascii=False)
    if req.products is not None:
        profile.products = json.dumps(req.products, ensure_ascii=False)
    if req.regulatory_focus is not None:
        profile.regulatory_focus = json.dumps(req.regulatory_focus, ensure_ascii=False)
    if req.context_note is not None:
        profile.context_note = req.context_note
    if req.sectors is not None:
        profile.sectors = json.dumps(req.sectors, ensure_ascii=False)

    profile.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(profile)
    return _serialize_profile(profile)


@router.post("/profile/start-analysis")
async def start_analysis(
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Lance la génération d'alertes en background après validation de la fiche."""
    import asyncio
    from legix.services.alert_generation import generate_alerts_for_profile

    # Créer le job de suivi
    job = OnboardingJob(
        profile_id=profile.id,
        status="pending",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Lancer en background
    asyncio.create_task(
        generate_alerts_for_profile(profile.id, job.id)
    )

    return {"job_id": job.id, "status": "started"}

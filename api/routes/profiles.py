"""Routes profils clients."""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.api.deps import get_db
from legix.core.config import settings
from legix.core.models import ClientProfile, ImpactAlert

_is_dev = settings.jwt_secret == "legix-demo-secret-change-in-prod"

router = APIRouter()


def _serialize_profile(p: ClientProfile) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "email": p.email,
        "sectors": json.loads(p.sectors) if p.sectors else [],
        "business_lines": json.loads(p.business_lines) if p.business_lines else [],
        "products": json.loads(p.products) if p.products else [],
        "regulatory_focus": json.loads(p.regulatory_focus) if p.regulatory_focus else [],
        "context_note": p.context_note,
        "is_active": p.is_active,
        "receive_briefing": p.receive_briefing,
        "briefing_frequency": p.briefing_frequency,
        "min_signal_severity": p.min_signal_severity,
    }


@router.get("/profiles")
async def list_profiles(
    db: AsyncSession = Depends(get_db),
):
    """Retourne tous les profils actifs avec stats alertes."""
    result = await db.execute(
        select(ClientProfile).where(ClientProfile.is_active.is_(True))
        .order_by(ClientProfile.name)
    )
    profiles = result.scalars().all()

    out = []
    for p in profiles:
        data = _serialize_profile(p)

        # Stats alertes
        total = (await db.execute(
            select(func.count()).where(ImpactAlert.profile_id == p.id)
        )).scalar() or 0

        unread = (await db.execute(
            select(func.count()).where(
                ImpactAlert.profile_id == p.id,
                ImpactAlert.is_read.is_(False),
            )
        )).scalar() or 0

        urgent = (await db.execute(
            select(func.count()).where(
                ImpactAlert.profile_id == p.id,
                ImpactAlert.impact_level.in_(["critical", "high"]),
            )
        )).scalar() or 0

        data["stats"] = {
            "total_alertes": total,
            "non_lues": unread,
            "urgentes": urgent,
        }
        out.append(data)

    return out


@router.get("/profiles/{profile_id}")
async def get_profile(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Detail d'un profil client."""
    result = await db.execute(
        select(ClientProfile).where(ClientProfile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Profil introuvable")

    data = _serialize_profile(profile)

    # Stats alertes detaillees
    total = (await db.execute(
        select(func.count()).where(ImpactAlert.profile_id == profile.id)
    )).scalar() or 0

    by_level = {}
    for level in ["critical", "high", "medium", "low"]:
        count = (await db.execute(
            select(func.count()).where(
                ImpactAlert.profile_id == profile.id,
                ImpactAlert.impact_level == level,
            )
        )).scalar() or 0
        by_level[level] = count

    threats = (await db.execute(
        select(func.count()).where(
            ImpactAlert.profile_id == profile.id,
            ImpactAlert.is_threat.is_(True),
        )
    )).scalar() or 0

    exposure = (await db.execute(
        select(func.sum(ImpactAlert.exposure_eur)).where(
            ImpactAlert.profile_id == profile.id,
        )
    )).scalar() or 0

    unread = (await db.execute(
        select(func.count()).where(
            ImpactAlert.profile_id == profile.id,
            ImpactAlert.is_read.is_(False),
        )
    )).scalar() or 0

    data["stats"] = {
        "total_alertes": total,
        "non_lues": unread,
        "urgentes": by_level.get("critical", 0) + by_level.get("high", 0),
        "par_niveau": by_level,
        "menaces": threats,
        "opportunites": total - threats,
        "exposure_eur": exposure,
    }

    return data


@router.get("/profiles/{profile_id}/alertes")
async def get_profile_alertes(
    profile_id: int,
    impact_level: str | None = None,
    is_threat: bool | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Alertes filtrees par profil."""

    stmt = select(ImpactAlert).where(ImpactAlert.profile_id == profile_id)

    if impact_level:
        stmt = stmt.where(ImpactAlert.impact_level == impact_level)
    if is_threat is not None:
        stmt = stmt.where(ImpactAlert.is_threat.is_(is_threat))

    stmt = stmt.order_by(ImpactAlert.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    alertes = result.scalars().all()

    return [
        {
            "id": a.id,
            "impact_level": a.impact_level,
            "impact_summary": a.impact_summary,
            "exposure_eur": a.exposure_eur,
            "matched_themes": json.loads(a.matched_themes) if a.matched_themes else [],
            "action_required": a.action_required,
            "is_threat": a.is_threat,
            "is_read": a.is_read,
            "texte_uid": a.texte_uid,
            "amendement_uid": a.amendement_uid,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alertes
    ]

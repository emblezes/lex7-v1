"""Routes briefings — consultation et export PDF."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.api.deps import get_current_profile, get_db
from legix.core.models import Briefing, ClientProfile

logger = logging.getLogger(__name__)
router = APIRouter()


class BriefingOut(BaseModel):
    id: int
    profile_id: int
    briefing_type: str | None = None
    content: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True}


@router.get("/briefings", response_model=list[BriefingOut])
async def list_briefings(
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Liste les briefings du profil authentifié."""
    result = await db.execute(
        select(Briefing)
        .where(Briefing.profile_id == profile.id)
        .order_by(Briefing.created_at.desc())
        .limit(30)
    )
    briefings = result.scalars().all()
    return [_briefing_to_out(b) for b in briefings]


@router.get("/briefings/{briefing_id}", response_model=BriefingOut)
async def get_briefing(
    briefing_id: int,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Contenu d'un briefing."""
    briefing = await db.get(Briefing, briefing_id)
    if not briefing or briefing.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Briefing introuvable")
    return _briefing_to_out(briefing)


@router.get("/briefings/{briefing_id}/pdf")
async def export_briefing_pdf(
    briefing_id: int,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Export PDF d'un briefing."""
    briefing = await db.get(Briefing, briefing_id)
    if not briefing or briefing.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Briefing introuvable")

    content = json.loads(briefing.content or "{}")

    from legix.export.pdf import export_briefing_pdf as gen_pdf
    pdf_bytes = gen_pdf(
        company_name=profile.name or "Client",
        date_str=str(briefing.created_at)[:10] if briefing.created_at else "N/A",
        content_sections=content,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="briefing_{briefing_id}.pdf"'
        },
    )


@router.post("/briefings/generate", response_model=BriefingOut)
async def generate_briefing(
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Déclencher manuellement la génération d'un briefing."""
    from legix.services.briefing_generation import generate_daily_briefing

    try:
        briefing = await generate_daily_briefing(db, profile)
        if not briefing:
            raise HTTPException(
                status_code=400,
                detail="Impossible de générer le briefing (pas de données récentes)",
            )
        return _briefing_to_out(briefing)
    except Exception as e:
        logger.error("Erreur génération briefing: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _briefing_to_out(b: Briefing) -> BriefingOut:
    return BriefingOut(
        id=b.id,
        profile_id=b.profile_id,
        briefing_type=b.briefing_type if hasattr(b, "briefing_type") else None,
        content=b.content,
        created_at=str(b.created_at) if b.created_at else None,
    )

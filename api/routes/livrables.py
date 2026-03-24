"""Routes livrables — CRUD + generation + export PDF."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.api.deps import get_current_profile, get_db
from legix.core.models import ActionTask, ClientProfile, Livrable

logger = logging.getLogger(__name__)
router = APIRouter()


class GenerateLivrableRequest(BaseModel):
    type: str  # note_comex / email / amendement / fiche_position


class UpdateLivrableRequest(BaseModel):
    status: str | None = None
    content: str | None = None
    title: str | None = None


def _livrable_to_dict(l: Livrable) -> dict:
    return {
        "id": l.id,
        "action_id": l.action_id,
        "profile_id": l.profile_id,
        "type": l.type,
        "title": l.title,
        "content": l.content,
        "format": l.format,
        "status": l.status,
        "metadata": l.metadata_,
        "created_at": l.created_at.isoformat() if l.created_at else None,
        "updated_at": l.updated_at.isoformat() if l.updated_at else None,
    }


@router.post("/actions/{action_id}/generate-livrable")
async def generate_livrable(
    action_id: int,
    body: GenerateLivrableRequest,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Genere un livrable pour une action."""
    task = await db.get(ActionTask, action_id)
    if not task or task.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Action introuvable")

    from legix.services.livrable_generator import generate_livrable as gen_livrable
    try:
        livrable = await gen_livrable(db, action_id, body.type)
        return _livrable_to_dict(livrable)
    except Exception as e:
        logger.error("Erreur generation livrable: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/livrables/{livrable_id}")
async def get_livrable(
    livrable_id: int,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Detail d'un livrable."""
    livrable = await db.get(Livrable, livrable_id)
    if not livrable or livrable.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Livrable introuvable")
    return _livrable_to_dict(livrable)


@router.put("/livrables/{livrable_id}")
async def update_livrable(
    livrable_id: int,
    body: UpdateLivrableRequest,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Modifier un livrable (status, content, title)."""
    livrable = await db.get(Livrable, livrable_id)
    if not livrable or livrable.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Livrable introuvable")

    if body.status is not None:
        livrable.status = body.status
    if body.content is not None:
        livrable.content = body.content
    if body.title is not None:
        livrable.title = body.title

    await db.commit()
    await db.refresh(livrable)
    return _livrable_to_dict(livrable)


@router.get("/livrables/{livrable_id}/pdf")
async def export_livrable_pdf(
    livrable_id: int,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Export PDF d'un livrable."""
    livrable = await db.get(Livrable, livrable_id)
    if not livrable or livrable.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Livrable introuvable")

    if not livrable.content:
        raise HTTPException(status_code=400, detail="Aucun contenu a exporter")

    from legix.export.pdf import export_impact_note_pdf
    pdf_bytes = export_impact_note_pdf(
        company_name=profile.name or "Client",
        alert_summary=livrable.title or "Livrable",
        impact_level="medium",
        content=livrable.content,
        metadata={"date": str(livrable.created_at), "type": livrable.type},
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="livrable_{livrable_id}.pdf"'
        },
    )

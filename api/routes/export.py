"""Routes export — PDF et DOCX pour les livrables."""

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.database import get_db
from legix.core.models import ClientProfile, Livrable

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/export", tags=["export"])


@router.get("/livrables/{livrable_id}/pdf")
async def export_livrable_pdf(
    livrable_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Exporte un livrable en PDF."""
    livrable = await db.get(Livrable, livrable_id)
    if not livrable:
        raise HTTPException(status_code=404, detail="Livrable non trouve")

    profile = await db.get(ClientProfile, livrable.profile_id)
    company_name = profile.name if profile else "Client"

    metadata = json.loads(livrable.metadata_) if livrable.metadata_ else {}

    from legix.export.pdf import export_impact_note_pdf
    pdf_bytes = export_impact_note_pdf(
        company_name=company_name,
        alert_summary=livrable.title,
        impact_level=metadata.get("impact_level", "medium"),
        content=livrable.content or "",
        metadata={
            "type": livrable.type,
            "date": str(livrable.created_at),
            "target_audience": metadata.get("target_audience", ""),
        },
    )

    filename = f"legix_{livrable.type}_{livrable_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/livrables/{livrable_id}/docx")
async def export_livrable_docx(
    livrable_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Exporte un livrable en DOCX (Word)."""
    livrable = await db.get(Livrable, livrable_id)
    if not livrable:
        raise HTTPException(status_code=404, detail="Livrable non trouve")

    profile = await db.get(ClientProfile, livrable.profile_id)
    company_name = profile.name if profile else "Client"

    metadata = json.loads(livrable.metadata_) if livrable.metadata_ else {}

    from legix.export.docx import export_livrable_docx as gen_docx
    docx_bytes = gen_docx(
        title=livrable.title,
        content_markdown=livrable.content or "",
        company_name=company_name,
        livrable_type=livrable.type,
        metadata={
            "date": str(livrable.created_at),
            "target_audience": metadata.get("target_audience", ""),
        },
    )

    filename = f"legix_{livrable.type}_{livrable_id}.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/briefing/{profile_id}/pdf")
async def export_briefing_pdf(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Exporte le dernier briefing d'un client en PDF."""
    from sqlalchemy import select
    from legix.core.models import Briefing

    profile = await db.get(ClientProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profil non trouve")

    result = await db.execute(
        select(Briefing)
        .where(Briefing.profile_id == profile_id)
        .order_by(Briefing.created_at.desc())
        .limit(1)
    )
    briefing = result.scalar_one_or_none()
    if not briefing:
        raise HTTPException(status_code=404, detail="Aucun briefing disponible")

    content = json.loads(briefing.content) if briefing.content else {}

    from legix.export.pdf import export_briefing_pdf as gen_pdf
    pdf_bytes = gen_pdf(
        company_name=profile.name,
        date_str=briefing.created_at.strftime("%d/%m/%Y") if briefing.created_at else "",
        content_sections=content,
    )

    filename = f"legix_briefing_{profile_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

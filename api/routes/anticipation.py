"""Routes API — Anticipation pré-législative.

CRUD pour les rapports d'anticipation + pipeline rapport→loi.
"""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.database import get_db
from legix.core.models import AnticipationReport

router = APIRouter(prefix="/anticipation", tags=["anticipation"])


@router.get("/reports")
async def list_reports(
    source_type: str | None = None,
    source_name: str | None = None,
    theme: str | None = None,
    pipeline_stage: str | None = None,
    limit: int = Query(default=20, le=100),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Liste les rapports d'anticipation avec filtres."""
    query = select(AnticipationReport).order_by(
        AnticipationReport.publication_date.desc()
    )

    if source_type:
        query = query.where(AnticipationReport.source_type == source_type)
    if source_name:
        query = query.where(AnticipationReport.source_name.ilike(f"%{source_name}%"))
    if theme:
        query = query.where(AnticipationReport.themes.ilike(f"%{theme}%"))
    if pipeline_stage:
        query = query.where(AnticipationReport.pipeline_stage == pipeline_stage)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    result = await db.execute(query.offset(offset).limit(limit))
    reports = result.scalars().all()

    return {
        "items": [
            {
                "id": r.id,
                "source_type": r.source_type,
                "source_name": r.source_name,
                "title": r.title,
                "url": r.url,
                "publication_date": r.publication_date.isoformat() if r.publication_date else None,
                "themes": json.loads(r.themes) if r.themes else [],
                "resume_ia": r.resume_ia,
                "policy_recommendations": json.loads(r.policy_recommendations) if r.policy_recommendations else [],
                "legislative_probability": r.legislative_probability,
                "estimated_timeline": r.estimated_timeline,
                "pipeline_stage": r.pipeline_stage,
                "linked_texte_uids": json.loads(r.linked_texte_uids) if r.linked_texte_uids else [],
                "is_read": r.is_read,
            }
            for r in reports
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/reports/{report_id}")
async def get_report(report_id: int, db: AsyncSession = Depends(get_db)):
    """Détail d'un rapport d'anticipation."""
    report = await db.get(AnticipationReport, report_id)
    if not report:
        from fastapi import HTTPException
        raise HTTPException(404, "Rapport non trouvé")

    return {
        "id": report.id,
        "source_type": report.source_type,
        "source_name": report.source_name,
        "title": report.title,
        "url": report.url,
        "author": report.author,
        "publication_date": report.publication_date.isoformat() if report.publication_date else None,
        "themes": json.loads(report.themes) if report.themes else [],
        "resume_ia": report.resume_ia,
        "policy_recommendations": json.loads(report.policy_recommendations) if report.policy_recommendations else [],
        "legislative_probability": report.legislative_probability,
        "estimated_timeline": report.estimated_timeline,
        "impact_assessment": report.impact_assessment,
        "pipeline_stage": report.pipeline_stage,
        "linked_texte_uids": json.loads(report.linked_texte_uids) if report.linked_texte_uids else [],
        "matched_sectors": json.loads(report.matched_sectors) if report.matched_sectors else [],
        "is_read": report.is_read,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


@router.get("/pipeline/{theme}")
async def get_pipeline(theme: str, db: AsyncSession = Depends(get_db)):
    """Visualisation du pipeline rapport→loi pour un thème."""
    from legix.agents.anticipateur import map_policy_pipeline
    return await map_policy_pipeline(db, theme=theme)


@router.get("/signals")
async def get_anticipation_signals(
    profile_id: int | None = None,
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """Signaux d'anticipation récents pour un client."""
    from legix.agents.anticipateur import detect_early_signals
    return await detect_early_signals(db, profile_id=profile_id, days=days)


@router.get("/stats")
async def anticipation_stats(db: AsyncSession = Depends(get_db)):
    """Statistiques globales d'anticipation."""
    # Par source
    source_query = select(
        AnticipationReport.source_name,
        func.count().label("nb"),
    ).group_by(AnticipationReport.source_name)
    result = await db.execute(source_query)
    by_source = {row.source_name: row.nb for row in result}

    # Par stade
    stage_query = select(
        AnticipationReport.pipeline_stage,
        func.count().label("nb"),
    ).group_by(AnticipationReport.pipeline_stage)
    result = await db.execute(stage_query)
    by_stage = {row.pipeline_stage: row.nb for row in result}

    # Total
    total = sum(by_source.values())

    return {
        "total": total,
        "by_source": by_source,
        "by_stage": by_stage,
    }

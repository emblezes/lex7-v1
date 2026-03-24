"""Routes pipeline — statut, déclenchement manuel, historique."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.api.deps import get_current_profile, get_db, verify_api_key
from legix.core.models import ClientProfile, PipelineRun

logger = logging.getLogger(__name__)
router = APIRouter()


class PipelineRunOut(BaseModel):
    id: int
    run_type: str
    status: str
    stats: str | None = None
    error_message: str | None = None
    started_at: str | None = None
    completed_at: str | None = None

    model_config = {"from_attributes": True}


@router.get("/pipeline/status")
async def pipeline_status(
    _: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Statut du dernier run pipeline."""
    result = await db.execute(
        select(PipelineRun)
        .order_by(PipelineRun.started_at.desc())
        .limit(1)
    )
    last_run = result.scalars().first()

    if not last_run:
        return {"status": "no_runs", "last_run": None}

    return {
        "status": last_run.status,
        "last_run": _run_to_out(last_run),
    }


@router.get("/pipeline/runs", response_model=list[PipelineRunOut])
async def list_pipeline_runs(
    run_type: str | None = None,
    limit: int = 20,
    _: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Historique des runs pipeline."""
    query = select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(limit)
    if run_type:
        query = query.where(PipelineRun.run_type == run_type)

    result = await db.execute(query)
    runs = result.scalars().all()

    return [_run_to_out(r) for r in runs]


@router.post("/pipeline/trigger", response_model=PipelineRunOut)
async def trigger_pipeline(
    _: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Déclencher manuellement le pipeline complet."""
    from legix.pipeline import collect_and_process

    try:
        await collect_and_process()
    except Exception as e:
        logger.error("Erreur pipeline manuel: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    # Retourner le dernier run créé
    result = await db.execute(
        select(PipelineRun)
        .order_by(PipelineRun.started_at.desc())
        .limit(1)
    )
    last_run = result.scalars().first()
    if not last_run:
        raise HTTPException(status_code=500, detail="Pipeline run non trouvé")

    return _run_to_out(last_run)


def _run_to_out(run: PipelineRun) -> PipelineRunOut:
    return PipelineRunOut(
        id=run.id,
        run_type=run.run_type,
        status=run.status,
        stats=run.stats,
        error_message=run.error_message,
        started_at=str(run.started_at) if run.started_at else None,
        completed_at=str(run.completed_at) if run.completed_at else None,
    )

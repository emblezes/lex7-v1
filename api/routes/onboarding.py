"""Routes de suivi de l'onboarding (progression de la génération d'alertes)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.database import get_db
from legix.core.models import ClientProfile, OnboardingJob
from legix.api.deps import get_current_profile

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: int,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Retourne le statut d'un job de génération d'alertes."""
    result = await db.execute(
        select(OnboardingJob).where(
            OnboardingJob.id == job_id,
            OnboardingJob.profile_id == profile.id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job introuvable")

    return {
        "id": job.id,
        "status": job.status,
        "progress_current": job.progress_current or 0,
        "progress_total": job.progress_total or 0,
        "alerts_count": job.alerts_count or 0,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }

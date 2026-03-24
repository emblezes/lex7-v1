"""Routes followups — suivi de textes dans le temps."""

import json
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.api.deps import get_current_profile, get_db
from legix.core.models import ClientProfile, TexteFollowUp

logger = logging.getLogger(__name__)
router = APIRouter()


class FollowUpCreate(BaseModel):
    texte_uid: str
    priority: str = "medium"
    notes: str | None = None


class FollowUpUpdate(BaseModel):
    status: str | None = None
    priority: str | None = None
    notes: str | None = None


class FollowUpOut(BaseModel):
    id: int
    profile_id: int
    texte_uid: str
    status: str
    priority: str
    last_analysis: str | None = None
    notes: str | None = None
    next_check_at: str | None = None
    commission_date: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True}


@router.get("/followups", response_model=list[FollowUpOut])
async def list_followups(
    status: str | None = None,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Liste les textes suivis par le profil authentifié."""
    query = select(TexteFollowUp).where(TexteFollowUp.profile_id == profile.id)
    if status:
        query = query.where(TexteFollowUp.status == status)
    query = query.order_by(TexteFollowUp.updated_at.desc())

    result = await db.execute(query)
    followups = result.scalars().all()

    return [_fu_to_out(fu) for fu in followups]


@router.post("/followups", response_model=FollowUpOut)
async def create_followup(
    data: FollowUpCreate,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Commencer à suivre un texte."""
    # Vérifier qu'on ne suit pas déjà ce texte
    existing = await db.execute(
        select(TexteFollowUp).where(
            TexteFollowUp.profile_id == profile.id,
            TexteFollowUp.texte_uid == data.texte_uid,
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Ce texte est déjà suivi")

    intervals = {"critical": 1, "high": 2, "medium": 5, "low": 10}

    fu = TexteFollowUp(
        profile_id=profile.id,
        texte_uid=data.texte_uid,
        status="watching",
        priority=data.priority,
        notes=data.notes,
        change_log=json.dumps([{
            "date": datetime.utcnow().isoformat(),
            "event": "Suivi démarré manuellement",
        }], ensure_ascii=False),
        next_check_at=datetime.utcnow() + timedelta(days=intervals.get(data.priority, 5)),
    )
    db.add(fu)
    await db.commit()
    await db.refresh(fu)

    return _fu_to_out(fu)


@router.put("/followups/{followup_id}", response_model=FollowUpOut)
async def update_followup(
    followup_id: int,
    data: FollowUpUpdate,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Mettre à jour un suivi (statut, priorité, notes)."""
    fu = await db.get(TexteFollowUp, followup_id)
    if not fu or fu.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Suivi introuvable")

    if data.status:
        fu.status = data.status
    if data.priority:
        fu.priority = data.priority
    if data.notes is not None:
        fu.notes = data.notes

    fu.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(fu)

    return _fu_to_out(fu)


@router.delete("/followups/{followup_id}")
async def delete_followup(
    followup_id: int,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Arrêter le suivi d'un texte."""
    fu = await db.get(TexteFollowUp, followup_id)
    if not fu or fu.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Suivi introuvable")

    await db.delete(fu)
    await db.commit()

    return {"detail": "Suivi supprimé"}


@router.get("/followups/{followup_id}/history")
async def get_followup_history(
    followup_id: int,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Historique des changements détectés sur un texte suivi."""
    fu = await db.get(TexteFollowUp, followup_id)
    if not fu or fu.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Suivi introuvable")

    changes = json.loads(fu.change_log or "[]")
    return {
        "followup_id": fu.id,
        "texte_uid": fu.texte_uid,
        "events": changes,
    }


def _fu_to_out(fu: TexteFollowUp) -> FollowUpOut:
    return FollowUpOut(
        id=fu.id,
        profile_id=fu.profile_id,
        texte_uid=fu.texte_uid,
        status=fu.status,
        priority=fu.priority,
        last_analysis=fu.last_analysis,
        notes=fu.notes,
        next_check_at=str(fu.next_check_at) if fu.next_check_at else None,
        commission_date=str(fu.commission_date) if fu.commission_date else None,
        created_at=str(fu.created_at) if fu.created_at else None,
        updated_at=str(fu.updated_at) if fu.updated_at else None,
    )

"""Routes actions — CRUD et exécution des ActionTasks."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.api.deps import get_current_profile, get_db
from legix.core.models import ActionTask, ClientProfile, ImpactAlert

logger = logging.getLogger(__name__)
router = APIRouter()


class ActionOut(BaseModel):
    id: int
    profile_id: int
    alert_id: int | None = None
    texte_uid: str | None = None
    action_type: str
    label: str
    rationale: str | None = None
    priority: int | None = None
    target_acteur_uids: list[str] | None = None
    status: str
    result_content: str | None = None
    result_format: str | None = None
    due_date: str | None = None
    completed_at: str | None = None
    created_at: str | None = None
    livrables: list[dict] | None = None

    model_config = {"from_attributes": True}


@router.get("/actions", response_model=list[ActionOut])
async def list_actions(
    status: str | None = None,
    texte_uid: str | None = None,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Liste les actions du profil authentifié."""
    query = select(ActionTask).where(ActionTask.profile_id == profile.id)
    if status:
        query = query.where(ActionTask.status == status)
    if texte_uid:
        query = query.where(ActionTask.texte_uid == texte_uid)
    query = query.order_by(ActionTask.created_at.desc())

    result = await db.execute(query)
    tasks = result.scalars().all()

    return [await _task_to_out_with_livrables(t, db) for t in tasks]


@router.get("/actions/{task_id}", response_model=ActionOut)
async def get_action(
    task_id: int,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Détail d'une action avec son contenu généré."""
    task = await db.get(ActionTask, task_id)
    if not task or task.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Action introuvable")
    return _task_to_out(task)


@router.post("/actions/{task_id}/execute", response_model=ActionOut)
async def execute_action(
    task_id: int,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Exécute une action via le RedacteurAgent."""
    task = await db.get(ActionTask, task_id)
    if not task or task.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Action introuvable")

    if task.status == "completed":
        raise HTTPException(status_code=400, detail="Action déjà exécutée")

    from legix.services.action_executor import execute_action as exec_action
    try:
        result = await exec_action(db, task_id)
        return _task_to_out(result)
    except Exception as e:
        logger.error("Erreur exécution action %d: %s", task_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/actions/{task_id}/export/pdf")
async def export_action_pdf(
    task_id: int,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Export PDF du résultat d'une action."""
    task = await db.get(ActionTask, task_id)
    if not task or task.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Action introuvable")

    if not task.result_content:
        raise HTTPException(status_code=400, detail="Aucun contenu à exporter")

    alert = await db.get(ImpactAlert, task.alert_id) if task.alert_id else None

    from legix.export.pdf import export_impact_note_pdf
    pdf_bytes = export_impact_note_pdf(
        company_name=profile.name or "Client",
        alert_summary=(alert.impact_summary or task.label) if alert else task.label,
        impact_level=(alert.impact_level or "medium") if alert else "medium",
        content=task.result_content,
        metadata={"date": str(task.completed_at or task.created_at)},
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="action_{task_id}.pdf"'},
    )


import json as _json

from legix.core.models import Livrable


def _task_to_out(task: ActionTask) -> ActionOut:
    target_uids = []
    if task.target_acteur_uids:
        try:
            target_uids = _json.loads(task.target_acteur_uids)
        except (_json.JSONDecodeError, TypeError):
            pass
    return ActionOut(
        id=task.id,
        profile_id=task.profile_id,
        alert_id=task.alert_id,
        texte_uid=task.texte_uid,
        action_type=task.action_type,
        label=task.label,
        rationale=task.rationale,
        priority=task.priority,
        target_acteur_uids=target_uids,
        status=task.status,
        result_content=task.result_content,
        result_format=task.result_format,
        due_date=str(task.due_date) if task.due_date else None,
        completed_at=str(task.completed_at) if task.completed_at else None,
        created_at=str(task.created_at) if task.created_at else None,
    )


async def _task_to_out_with_livrables(task: ActionTask, db) -> ActionOut:
    out = _task_to_out(task)
    result = await db.execute(
        select(Livrable).where(Livrable.action_id == task.id)
    )
    out.livrables = [
        {
            "id": l.id,
            "type": l.type,
            "title": l.title,
            "status": l.status,
            "format": l.format,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in result.scalars().all()
    ]
    return out

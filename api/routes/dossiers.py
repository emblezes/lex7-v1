"""Routes dossiers — actions IA, evenements, acteurs cles par dossier."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.api.deps import get_current_profile, get_db
from legix.core.models import ActionTask, ClientProfile, Texte

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Actions recommandees ---


@router.post("/dossiers/{texte_uid}/actions/generate")
async def generate_dossier_actions(
    texte_uid: str,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Genere des actions recommandees IA pour un dossier."""
    texte = await db.get(Texte, texte_uid)
    if not texte:
        raise HTTPException(status_code=404, detail="Texte introuvable")

    from legix.services.dossier_actions import generate_dossier_actions as gen_actions
    try:
        actions = await gen_actions(db, texte_uid, profile)
        return [_action_to_dict(a) for a in actions]
    except Exception as e:
        logger.error("Erreur generation actions %s: %s", texte_uid, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dossiers/{texte_uid}/actions")
async def list_dossier_actions(
    texte_uid: str,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Liste les actions liees a un dossier."""
    result = await db.execute(
        select(ActionTask)
        .where(
            ActionTask.texte_uid == texte_uid,
            ActionTask.profile_id == profile.id,
        )
        .order_by(ActionTask.priority, ActionTask.created_at.desc())
    )
    tasks = result.scalars().all()

    # Charger les livrables pour chaque action
    output = []
    for t in tasks:
        d = _action_to_dict(t)
        # Charger livrables
        from legix.core.models import Livrable
        livr_result = await db.execute(
            select(Livrable).where(Livrable.action_id == t.id)
        )
        d["livrables"] = [
            {
                "id": l.id,
                "type": l.type,
                "title": l.title,
                "status": l.status,
                "format": l.format,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in livr_result.scalars().all()
        ]
        output.append(d)

    return output


# --- Evenements ---


@router.get("/dossiers/{texte_uid}/evenements")
async def list_dossier_evenements(
    texte_uid: str,
    limit: int = 50,
    offset: int = 0,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Retourne la timeline fusionnee d'un dossier."""
    from legix.services.evenement_service import get_dossier_evenements
    return await get_dossier_evenements(
        db, texte_uid, profile_id=profile.id, limit=limit, offset=offset,
    )


class EvenementCreate(BaseModel):
    event_type: str
    title: str
    description: str | None = None
    severity: str = "info"
    source_ref: str | None = None
    source_url: str | None = None


@router.post("/dossiers/{texte_uid}/evenements")
async def create_dossier_evenement(
    texte_uid: str,
    body: EvenementCreate,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Cree un evenement manuellement."""
    from legix.services.evenement_service import create_evenement
    ev = await create_evenement(
        db,
        texte_uid=texte_uid,
        event_type=body.event_type,
        title=body.title,
        description=body.description,
        severity=body.severity,
        source_ref=body.source_ref,
        source_url=body.source_url,
        profile_id=profile.id,
    )
    return {
        "id": ev.id,
        "type": ev.event_type,
        "title": ev.title,
        "created_at": ev.created_at.isoformat() if ev.created_at else None,
    }


# --- Acteurs cles ---


@router.get("/dossiers/{texte_uid}/acteurs-cles")
async def get_dossier_acteurs_cles(
    texte_uid: str,
    limit: int = 10,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Retourne les acteurs cles d'un dossier avec scores d'influence."""
    from legix.services.acteur_influence import get_dossier_acteurs_cles
    return await get_dossier_acteurs_cles(
        db, texte_uid, profile_id=profile.id, limit=limit,
    )


# --- Helpers ---


def _action_to_dict(task: ActionTask) -> dict:
    import json
    return {
        "id": task.id,
        "profile_id": task.profile_id,
        "alert_id": task.alert_id,
        "texte_uid": task.texte_uid,
        "action_type": task.action_type,
        "label": task.label,
        "rationale": task.rationale,
        "priority": task.priority,
        "target_acteur_uids": (
            json.loads(task.target_acteur_uids)
            if task.target_acteur_uids else []
        ),
        "status": task.status,
        "result_content": task.result_content,
        "due_date": str(task.due_date) if task.due_date else None,
        "completed_at": str(task.completed_at) if task.completed_at else None,
        "created_at": str(task.created_at) if task.created_at else None,
    }

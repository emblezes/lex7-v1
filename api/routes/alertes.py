"""Routes alertes d'impact — feed chronologique et détail enrichi."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from legix.api.deps import PaginationParams, get_current_profile, get_db
from legix.core.models import (
    Acteur,
    Amendement,
    ClientProfile,
    ImpactAlert,
    Organe,
    Texte,
    amendement_cosignataires,
)
from legix.enrichment.scoring import compute_adoption_score_detailed

router = APIRouter()


def _serialize_alert(a: ImpactAlert) -> dict:
    # Parse action_required: JSON list or plain text
    actions = []
    if a.action_required:
        try:
            actions = json.loads(a.action_required)
        except (json.JSONDecodeError, TypeError):
            actions = [{"type": "note", "label": a.action_required, "agent_prompt": None}]

    # Parse actions_status
    actions_status = {}
    if a.actions_status:
        try:
            actions_status = json.loads(a.actions_status)
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "id": a.id,
        "profile_id": a.profile_id,
        "impact_level": a.impact_level,
        "impact_summary": a.impact_summary,
        "exposure_eur": a.exposure_eur,
        "matched_themes": json.loads(a.matched_themes) if a.matched_themes else [],
        "actions": actions,
        "actions_status": actions_status,
        "is_threat": a.is_threat,
        "is_read": a.is_read,
        "texte_uid": a.texte_uid,
        "amendement_uid": a.amendement_uid,
        "reunion_uid": a.reunion_uid,
        "compte_rendu_uid": a.compte_rendu_uid,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _serialize_acteur(a: Acteur) -> dict:
    """Serialise un acteur avec groupe politique."""
    groupe = a.groupe_politique
    return {
        "uid": a.uid,
        "civilite": a.civilite,
        "prenom": a.prenom,
        "nom": a.nom,
        "groupe_politique": (
            {
                "uid": groupe.uid,
                "libelle": groupe.libelle,
                "libelle_court": groupe.libelle_court,
            }
            if groupe
            else None
        ),
    }


@router.get("/alertes")
async def list_alertes(
    impact_level: str | None = None,
    is_threat: bool | None = None,
    unread_only: bool = False,
    pagination: PaginationParams = Depends(),
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ImpactAlert).where(
        ImpactAlert.profile_id == profile.id
    ).order_by(ImpactAlert.created_at.desc())

    if impact_level:
        stmt = stmt.where(ImpactAlert.impact_level == impact_level)
    if is_threat is not None:
        stmt = stmt.where(ImpactAlert.is_threat == is_threat)
    if unread_only:
        stmt = stmt.where(ImpactAlert.is_read == False)  # noqa: E712

    stmt = stmt.offset(pagination.offset).limit(pagination.limit)
    result = await db.execute(stmt)
    return [_serialize_alert(a) for a in result.scalars().all()]


@router.get("/alertes/{alert_id}")
async def get_alerte(
    alert_id: int,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Detail enrichi d'une alerte : amendement, auteur, adoption, cosignataires."""
    alert = await db.get(ImpactAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    if alert.profile_id != profile.id:
        raise HTTPException(status_code=403, detail="Accès interdit")

    data = _serialize_alert(alert)

    # ── Enrichissement amendement ──
    if alert.amendement_uid:
        result = await db.execute(
            select(Amendement)
            .options(
                joinedload(Amendement.auteur).joinedload(Acteur.groupe_politique),
                joinedload(Amendement.groupe),
            )
            .where(Amendement.uid == alert.amendement_uid)
        )
        amdt = result.unique().scalars().first()

        if amdt:
            # Score adoption detaille
            try:
                score_detail = await compute_adoption_score_detailed(db, amdt)
                adoption_score = score_detail["score"]
            except Exception:
                adoption_score = None
                score_detail = None

            # Cosignataires
            cosig_result = await db.execute(
                select(Acteur)
                .join(
                    amendement_cosignataires,
                    amendement_cosignataires.c.acteur_uid == Acteur.uid,
                )
                .options(joinedload(Acteur.groupe_politique))
                .where(
                    amendement_cosignataires.c.amendement_uid == amdt.uid
                )
            )
            cosignataires_raw = cosig_result.unique().scalars().all()

            cosignataires = [_serialize_acteur(c) for c in cosignataires_raw]
            groupes_set = {
                c["groupe_politique"]["libelle_court"]
                for c in cosignataires
                if c.get("groupe_politique")
            }
            # Ajouter le groupe de l'auteur
            if amdt.groupe and amdt.groupe.libelle_court:
                groupes_set.add(amdt.groupe.libelle_court)

            data["amendement"] = {
                "uid": amdt.uid,
                "numero": amdt.numero,
                "article_vise": amdt.article_vise,
                "etat": amdt.etat,
                "sort": amdt.sort,
                "date_depot": str(amdt.date_depot) if amdt.date_depot else None,
                "themes": json.loads(amdt.themes) if amdt.themes else [],
                "resume_ia": amdt.resume_ia,
                "expose_sommaire": amdt.expose_sommaire,
                "url_source": amdt.url_source,
                "auteur": (
                    _serialize_acteur(amdt.auteur) if amdt.auteur else None
                ),
                "auteur_nom": amdt.auteur_nom,
                "groupe": (
                    {
                        "uid": amdt.groupe.uid,
                        "libelle": amdt.groupe.libelle,
                        "libelle_court": amdt.groupe.libelle_court,
                    }
                    if amdt.groupe
                    else None
                ),
                "groupe_nom": amdt.groupe_nom,
                "adoption_score": round(adoption_score, 3) if adoption_score is not None else None,
                "adoption_breakdown": score_detail if score_detail else None,
                "cosignataires": cosignataires,
                "nb_groupes_differents": len(groupes_set),
                "convergence_transpartisane": len(groupes_set) >= 3,
            }

            # Stats auteur si disponible
            if amdt.auteur_ref:
                author_amdts = await db.execute(
                    select(Amendement).where(
                        Amendement.auteur_ref == amdt.auteur_ref
                    )
                )
                all_author_amdts = author_amdts.scalars().all()
                nb_total = len(all_author_amdts)
                nb_adoptes = sum(
                    1 for a in all_author_amdts
                    if a.sort and "adopt" in a.sort.lower()
                )
                taux = round(nb_adoptes / nb_total * 100, 1) if nb_total > 0 else 0

                data["amendement"]["auteur_stats"] = {
                    "nb_amendements": nb_total,
                    "nb_adoptes": nb_adoptes,
                    "taux_adoption": taux,
                }

    return data


@router.put("/alertes/{alert_id}/read")
async def mark_alerte_read(
    alert_id: int,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    alert = await db.get(ImpactAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    if alert.profile_id != profile.id:
        raise HTTPException(status_code=403, detail="Accès interdit")
    alert.is_read = True
    await db.commit()
    return {"status": "ok"}


class ActionStatusUpdate(BaseModel):
    status: str  # "done", "pending", "in_progress"


@router.put("/alertes/{alert_id}/actions/{action_index}")
async def update_action_status(
    alert_id: int,
    action_index: int,
    body: ActionStatusUpdate,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Met a jour le statut d'une action recommandee."""
    alert = await db.get(ImpactAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    if alert.profile_id != profile.id:
        raise HTTPException(status_code=403, detail="Accès interdit")

    statuses = {}
    if alert.actions_status:
        try:
            statuses = json.loads(alert.actions_status)
        except (json.JSONDecodeError, TypeError):
            pass

    statuses[str(action_index)] = body.status
    alert.actions_status = json.dumps(statuses)
    await db.commit()
    return {"status": "ok", "actions_status": statuses}

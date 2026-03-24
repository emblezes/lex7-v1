"""Routes textes suivis — dossiers consolides par texte pour un client."""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from legix.api.deps import get_db
from legix.core.models import (
    Amendement,
    ClientProfile,
    TexteBrief,
    TexteFollowUp,
    Texte,
)

router = APIRouter()


def _parse_json(val):
    if not val:
        return []
    try:
        return json.loads(val) if isinstance(val, str) else val
    except (json.JSONDecodeError, TypeError):
        return []


def _serialize_brief(b: TexteBrief, texte: Texte | None = None) -> dict:
    data = {
        "id": b.id,
        "profile_id": b.profile_id,
        "texte_uid": b.texte_uid,
        "followup_id": b.followup_id,
        "executive_summary": b.executive_summary,
        "force_map": _parse_json(b.force_map),
        "critical_amendments": _parse_json(b.critical_amendments),
        "key_contacts": _parse_json(b.key_contacts),
        "action_plan": _parse_json(b.action_plan),
        "exposure_eur": b.exposure_eur,
        "impact_level": b.impact_level,
        "is_threat": b.is_threat,
        "nb_amendements_analyzed": b.nb_amendements_analyzed,
        "nb_groupes": b.nb_groupes,
        "nb_deputes": b.nb_deputes,
        "version": b.version,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }
    if texte:
        data["texte"] = {
            "uid": texte.uid,
            "titre": texte.titre_court or texte.titre,
            "type_code": texte.type_code,
            "source": texte.source or "assemblee",
            "date_depot": texte.date_depot.isoformat() if texte.date_depot else None,
            "themes": _parse_json(texte.themes),
            "resume_ia": texte.resume_ia,
        }
    return data


@router.get("/profiles/{profile_id}/textes-suivis")
async def list_textes_suivis(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Liste des textes suivis avec resume du brief."""
    result = await db.execute(
        select(TexteBrief)
        .where(TexteBrief.profile_id == profile_id)
        .order_by(TexteBrief.updated_at.desc())
    )
    briefs = result.scalars().all()

    out = []
    for b in briefs:
        texte = await db.get(Texte, b.texte_uid)
        out.append(_serialize_brief(b, texte))

    return out


@router.get("/profiles/{profile_id}/textes-suivis/{texte_uid}")
async def get_texte_brief_detail(
    profile_id: int,
    texte_uid: str,
    db: AsyncSession = Depends(get_db),
):
    """Detail complet du brief pour un texte + profil."""
    result = await db.execute(
        select(TexteBrief).where(
            TexteBrief.profile_id == profile_id,
            TexteBrief.texte_uid == texte_uid,
        )
    )
    brief = result.scalar_one_or_none()
    if not brief:
        raise HTTPException(status_code=404, detail="Brief non trouve")

    texte = await db.get(Texte, texte_uid)
    data = _serialize_brief(brief, texte)

    # Ajouter le change log du followup si present
    if brief.followup_id:
        followup = await db.get(TexteFollowUp, brief.followup_id)
        if followup:
            data["followup"] = {
                "id": followup.id,
                "status": followup.status,
                "priority": followup.priority,
                "change_log": _parse_json(followup.change_log),
                "next_check_at": followup.next_check_at.isoformat() if followup.next_check_at else None,
            }

    # Nombre total d'amendements sur ce texte (pas juste ceux analyses)
    total_amdts = (await db.execute(
        select(func.count(Amendement.uid)).where(Amendement.texte_ref == texte_uid)
    )).scalar() or 0
    data["nb_amendements_total"] = total_amdts

    return data


@router.post("/profiles/{profile_id}/textes-suivis/{texte_uid}/refresh")
async def refresh_texte_brief(
    profile_id: int,
    texte_uid: str,
    db: AsyncSession = Depends(get_db),
):
    """Force la regeneration du brief pour un texte."""
    profile = await db.get(ClientProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profil introuvable")

    # Trouver le followup existant
    fu_result = await db.execute(
        select(TexteFollowUp).where(
            TexteFollowUp.profile_id == profile_id,
            TexteFollowUp.texte_uid == texte_uid,
        )
    )
    followup = fu_result.scalar_one_or_none()

    from legix.services.texte_brief import generate_texte_brief
    brief = await generate_texte_brief(db, texte_uid, profile, followup)

    texte = await db.get(Texte, texte_uid)
    return _serialize_brief(brief, texte)

"""Routes API — Stakeholders (CRM parties prenantes).

CRUD pour les profils de stakeholders + liens dossier + interactions.
"""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.database import get_db
from legix.core.models import (
    ContactInteraction,
    StakeholderDossierLink,
    StakeholderProfile,
)

router = APIRouter(prefix="/stakeholders", tags=["stakeholders"])


# --- Pydantic schemas ---

class StakeholderCreate(BaseModel):
    stakeholder_type: str
    nom: str
    prenom: str | None = None
    organisation: str | None = None
    titre: str | None = None
    email: str | None = None
    telephone: str | None = None
    twitter: str | None = None
    linkedin: str | None = None
    site_web: str | None = None
    acteur_uid: str | None = None
    key_themes: list[str] | None = None


class InteractionCreate(BaseModel):
    stakeholder_id: int
    interaction_type: str
    subject: str | None = None
    notes: str | None = None
    outcome: str | None = None
    follow_up_needed: bool = False
    follow_up_date: str | None = None
    dossier_texte_uid: str | None = None


# --- Routes ---

@router.get("")
async def list_stakeholders(
    stakeholder_type: str | None = None,
    theme: str | None = None,
    organisation: str | None = None,
    search: str | None = None,
    limit: int = Query(default=20, le=100),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Liste les stakeholders avec filtres."""
    query = select(StakeholderProfile).order_by(
        StakeholderProfile.influence_score.desc().nullslast()
    )

    if stakeholder_type:
        query = query.where(StakeholderProfile.stakeholder_type == stakeholder_type)
    if theme:
        query = query.where(StakeholderProfile.key_themes.ilike(f"%{theme}%"))
    if organisation:
        query = query.where(StakeholderProfile.organisation.ilike(f"%{organisation}%"))
    if search:
        query = query.where(
            StakeholderProfile.nom.ilike(f"%{search}%")
            | StakeholderProfile.prenom.ilike(f"%{search}%")
            | StakeholderProfile.organisation.ilike(f"%{search}%")
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    result = await db.execute(query.offset(offset).limit(limit))
    stakeholders = result.scalars().all()

    return {
        "items": [_serialize_stakeholder(s) for s in stakeholders],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/{stakeholder_id}")
async def get_stakeholder(stakeholder_id: int, db: AsyncSession = Depends(get_db)):
    """Détail d'un stakeholder."""
    s = await db.get(StakeholderProfile, stakeholder_id)
    if not s:
        raise HTTPException(404, "Stakeholder non trouvé")
    return _serialize_stakeholder(s, full=True)


@router.post("")
async def create_stakeholder(
    data: StakeholderCreate, db: AsyncSession = Depends(get_db)
):
    """Crée un nouveau stakeholder."""
    s = StakeholderProfile(
        stakeholder_type=data.stakeholder_type,
        nom=data.nom,
        prenom=data.prenom,
        organisation=data.organisation,
        titre=data.titre,
        email=data.email,
        telephone=data.telephone,
        twitter=data.twitter,
        linkedin=data.linkedin,
        site_web=data.site_web,
        acteur_uid=data.acteur_uid,
        key_themes=json.dumps(data.key_themes) if data.key_themes else None,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return _serialize_stakeholder(s)


@router.get("/{stakeholder_id}/dossiers")
async def stakeholder_dossiers(
    stakeholder_id: int, db: AsyncSession = Depends(get_db)
):
    """Dossiers liés à un stakeholder."""
    query = select(StakeholderDossierLink).where(
        StakeholderDossierLink.stakeholder_id == stakeholder_id
    )
    result = await db.execute(query)
    links = result.scalars().all()

    return [
        {
            "id": l.id,
            "texte_uid": l.texte_uid,
            "role": l.role,
            "position": l.position,
            "position_confidence": l.position_confidence,
            "relevance_score": l.relevance_score,
            "notes": l.notes,
        }
        for l in links
    ]


@router.get("/{stakeholder_id}/interactions")
async def stakeholder_interactions(
    stakeholder_id: int,
    profile_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Historique des interactions avec un stakeholder."""
    query = select(ContactInteraction).where(
        ContactInteraction.stakeholder_id == stakeholder_id
    ).order_by(ContactInteraction.date.desc())

    if profile_id:
        query = query.where(ContactInteraction.profile_id == profile_id)

    result = await db.execute(query)
    interactions = result.scalars().all()

    return [
        {
            "id": i.id,
            "interaction_type": i.interaction_type,
            "date": i.date.isoformat() if i.date else None,
            "subject": i.subject,
            "notes": i.notes,
            "outcome": i.outcome,
            "follow_up_needed": i.follow_up_needed,
            "follow_up_date": i.follow_up_date.isoformat() if i.follow_up_date else None,
            "dossier_texte_uid": i.dossier_texte_uid,
        }
        for i in interactions
    ]


@router.post("/{stakeholder_id}/interactions")
async def add_interaction(
    stakeholder_id: int,
    data: InteractionCreate,
    profile_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Ajoute une interaction avec un stakeholder."""
    interaction = ContactInteraction(
        profile_id=profile_id,
        stakeholder_id=stakeholder_id,
        interaction_type=data.interaction_type,
        subject=data.subject,
        notes=data.notes,
        outcome=data.outcome,
        follow_up_needed=data.follow_up_needed,
        dossier_texte_uid=data.dossier_texte_uid,
    )
    if data.follow_up_date:
        interaction.follow_up_date = datetime.fromisoformat(data.follow_up_date)

    db.add(interaction)
    await db.commit()
    await db.refresh(interaction)

    return {"id": interaction.id, "status": "created"}


def _serialize_stakeholder(s: StakeholderProfile, full: bool = False) -> dict:
    """Sérialise un StakeholderProfile."""
    data = {
        "id": s.id,
        "stakeholder_type": s.stakeholder_type,
        "nom": s.nom,
        "prenom": s.prenom,
        "organisation": s.organisation,
        "titre": s.titre,
        "influence_score": s.influence_score,
        "relationship_status": s.relationship_status,
        "key_themes": json.loads(s.key_themes) if s.key_themes else [],
        "email": s.email,
        "twitter": s.twitter,
    }

    if full:
        data.update({
            "acteur_uid": s.acteur_uid,
            "telephone": s.telephone,
            "linkedin": s.linkedin,
            "site_web": s.site_web,
            "bio_summary": s.bio_summary,
            "political_positioning": json.loads(s.political_positioning) if s.political_positioning else None,
            "past_positions": json.loads(s.past_positions) if s.past_positions else [],
            "influence_breakdown": json.loads(s.influence_breakdown) if s.influence_breakdown else None,
            "last_contact_date": s.last_contact_date.isoformat() if s.last_contact_date else None,
            "publications": json.loads(s.publications) if s.publications else [],
            "votes_summary": json.loads(s.votes_summary) if s.votes_summary else None,
            "media_appearances": json.loads(s.media_appearances) if s.media_appearances else [],
            "created_at": s.created_at.isoformat() if s.created_at else None,
        })

    return data

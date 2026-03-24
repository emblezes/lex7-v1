"""Routes amendements."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.api.deps import PaginationParams, get_db
from legix.core.models import Amendement

router = APIRouter()


def _serialize_amdt(a: Amendement) -> dict:
    return {
        "uid": a.uid,
        "legislature": a.legislature,
        "numero": a.numero,
        "texte_ref": a.texte_ref,
        "organe_examen": a.organe_examen,
        "auteur_ref": a.auteur_ref,
        "auteur_type": a.auteur_type,
        "groupe_ref": a.groupe_ref,
        "article_vise": a.article_vise,
        "dispositif": a.dispositif,
        "expose_sommaire": a.expose_sommaire,
        "date_depot": a.date_depot.isoformat() if a.date_depot else None,
        "etat": a.etat,
        "sort": a.sort,
        "source": a.source,
        "themes": json.loads(a.themes) if a.themes else [],
        "resume_ia": a.resume_ia,
        "score_impact": json.loads(a.score_impact) if a.score_impact else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.get("/amendements")
async def list_amendements(
    texte_ref: str | None = None,
    auteur_ref: str | None = None,
    groupe_ref: str | None = None,
    etat: str | None = None,
    sort_val: str | None = Query(None, alias="sort"),
    theme: str | None = None,
    source: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Amendement).order_by(Amendement.created_at.desc())

    if texte_ref:
        stmt = stmt.where(Amendement.texte_ref == texte_ref)
    if auteur_ref:
        stmt = stmt.where(Amendement.auteur_ref == auteur_ref)
    if groupe_ref:
        stmt = stmt.where(Amendement.groupe_ref == groupe_ref)
    if etat:
        stmt = stmt.where(Amendement.etat == etat)
    if sort_val:
        stmt = stmt.where(Amendement.sort == sort_val)
    if theme:
        stmt = stmt.where(Amendement.themes.ilike(f'%"{theme}"%'))
    if source:
        stmt = stmt.where(Amendement.source == source)
    if date_from:
        stmt = stmt.where(Amendement.date_depot >= date_from)
    if date_to:
        stmt = stmt.where(Amendement.date_depot <= date_to)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            Amendement.dispositif.ilike(pattern) | Amendement.expose_sommaire.ilike(pattern)
        )

    stmt = stmt.offset(pagination.offset).limit(pagination.limit)
    result = await db.execute(stmt)
    return [_serialize_amdt(a) for a in result.scalars().all()]


@router.get("/amendements/{uid}")
async def get_amendement(uid: str, db: AsyncSession = Depends(get_db)):
    amdt = await db.get(Amendement, uid)
    if not amdt:
        raise HTTPException(status_code=404, detail="Amendement non trouvé")
    return _serialize_amdt(amdt)

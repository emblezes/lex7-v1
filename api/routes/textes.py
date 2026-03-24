"""Routes textes législatifs."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from legix.api.deps import PaginationParams, get_db
from legix.core.models import Acteur, Amendement, Organe, Texte


# Mapping source brute → libellé lisible
SOURCE_LABELS = {
    "assemblee": "Assemblée nationale",
    "senat": "Sénat",
    "gouvernement": "Gouvernement",
    "jorf": "Journal officiel",
}

router = APIRouter()


def _build_url_source(t: Texte) -> str | None:
    """Generate a fallback URL for textes that don't have one stored."""
    if t.source == "assemblee" and t.uid:
        # e.g. PIONANR5L17B0008 → https://www.assemblee-nationale.fr/dyn/17/textes/l17b0008_proposition-loi
        # Simpler: link to the dossier page which always works
        if t.dossier_ref:
            return f"https://www.assemblee-nationale.fr/dyn/17/dossiers/{t.dossier_ref}"
    return None


def _serialize_texte(t: Texte) -> dict:
    return {
        "uid": t.uid,
        "legislature": t.legislature,
        "denomination": t.denomination,
        "titre": t.titre,
        "titre_court": t.titre_court,
        "type_code": t.type_code,
        "type_libelle": t.type_libelle,
        "date_depot": t.date_depot.isoformat() if t.date_depot else None,
        "date_publication": t.date_publication.isoformat() if t.date_publication else None,
        "source": t.source,
        "source_label": SOURCE_LABELS.get(t.source, t.source),
        "themes": json.loads(t.themes) if t.themes else [],
        "resume_ia": t.resume_ia,
        "score_impact": t.score_impact,
        "url_source": t.url_source or _build_url_source(t),
        "dossier_ref": t.dossier_ref,
        "organe_ref": t.organe_ref,
        "auteur_texte": t.auteur_texte,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


@router.get("/textes")
async def list_textes(
    type_code: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
    theme: str | None = None,
    source: str | None = None,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Texte).order_by(Texte.created_at.desc())

    if type_code:
        stmt = stmt.where(Texte.type_code == type_code)
    if date_from:
        stmt = stmt.where(Texte.date_depot >= date_from)
    if date_to:
        stmt = stmt.where(Texte.date_depot <= date_to)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(Texte.titre.ilike(pattern) | Texte.titre_court.ilike(pattern))
    if theme:
        stmt = stmt.where(Texte.themes.ilike(f'%"{theme}"%'))
    if source:
        stmt = stmt.where(Texte.source == source)

    stmt = stmt.offset(pagination.offset).limit(pagination.limit)
    result = await db.execute(stmt)
    return [_serialize_texte(t) for t in result.scalars().all()]


@router.get("/textes/{uid}")
async def get_texte(uid: str, db: AsyncSession = Depends(get_db)):
    # Charger le texte avec ses auteurs (eager load)
    stmt = (
        select(Texte)
        .where(Texte.uid == uid)
        .options(selectinload(Texte.auteurs))
    )
    result = await db.execute(stmt)
    texte = result.scalars().first()
    if not texte:
        raise HTTPException(status_code=404, detail="Texte non trouvé")

    data = _serialize_texte(texte)

    # ── Commission de renvoi (résoudre le code → nom) ──
    if texte.organe_ref:
        organe = await db.get(Organe, texte.organe_ref)
        if organe:
            data["commission"] = {
                "uid": organe.uid,
                "libelle": organe.libelle,
                "libelle_court": organe.libelle_court,
                "type": organe.type_libelle,
            }

    # ── Auteurs du texte ──
    auteurs_data = []
    for acteur in texte.auteurs:
        # Charger le groupe politique de chaque auteur
        groupe = None
        if acteur.groupe_politique_ref:
            groupe_obj = await db.get(Organe, acteur.groupe_politique_ref)
            if groupe_obj:
                groupe = {
                    "uid": groupe_obj.uid,
                    "libelle": groupe_obj.libelle,
                    "libelle_court": groupe_obj.libelle_court,
                }
        auteurs_data.append({
            "uid": acteur.uid,
            "civilite": acteur.civilite,
            "prenom": acteur.prenom,
            "nom": acteur.nom,
            "groupe_politique": groupe,
        })
    data["auteurs"] = auteurs_data

    # ── Nombre d'amendements ──
    count = (await db.execute(
        select(func.count(Amendement.uid)).where(Amendement.texte_ref == uid)
    )).scalar() or 0
    data["amendements_count"] = count

    # ── Stats amendements par sort ──
    sort_stats_stmt = (
        select(Amendement.sort, func.count(Amendement.uid))
        .where(Amendement.texte_ref == uid)
        .where(Amendement.sort.isnot(None))
        .where(Amendement.sort != "")
        .group_by(Amendement.sort)
    )
    sort_stats = (await db.execute(sort_stats_stmt)).all()
    data["amendements_stats"] = {row[0]: row[1] for row in sort_stats}

    # ── Top amendements avec dispositif (pour affichage contenu) ──
    top_amdt_stmt = (
        select(Amendement)
        .where(Amendement.texte_ref == uid)
        .options(selectinload(Amendement.auteur))
        .order_by(Amendement.date_depot.desc())
        .limit(10)
    )
    top_amdts = (await db.execute(top_amdt_stmt)).scalars().all()

    # Résoudre les noms de groupes des amendements
    groupe_cache: dict[str, dict | None] = {}

    async def _resolve_groupe(ref: str | None) -> dict | None:
        if not ref:
            return None
        if ref not in groupe_cache:
            g = await db.get(Organe, ref)
            groupe_cache[ref] = {
                "libelle": g.libelle,
                "libelle_court": g.libelle_court,
            } if g else None
        return groupe_cache[ref]

    amendements_list = []
    for a in top_amdts:
        auteur_info = None
        if a.auteur:
            auteur_info = {
                "uid": a.auteur.uid,
                "civilite": a.auteur.civilite,
                "prenom": a.auteur.prenom,
                "nom": a.auteur.nom,
            }
        groupe_info = await _resolve_groupe(a.groupe_ref)

        amendements_list.append({
            "uid": a.uid,
            "numero": a.numero,
            "article_vise": a.article_vise,
            "etat": a.etat,
            "sort": a.sort,
            "auteur_ref": a.auteur_ref,
            "auteur": auteur_info,
            "auteur_type": a.auteur_type,
            "auteur_nom": a.auteur_nom,
            "groupe_ref": a.groupe_ref,
            "groupe": groupe_info,
            "groupe_nom": a.groupe_nom,
            "dispositif": a.dispositif,
            "expose_sommaire": a.expose_sommaire,
            "date_depot": a.date_depot.isoformat() if a.date_depot else None,
            "themes": json.loads(a.themes) if a.themes else [],
            "resume_ia": a.resume_ia,
            "url_source": a.url_source,
        })
    data["amendements"] = amendements_list

    return data


@router.get("/textes/{uid}/amendements")
async def get_texte_amendements(
    uid: str,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Amendement)
        .where(Amendement.texte_ref == uid)
        .order_by(Amendement.date_depot.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    result = await db.execute(stmt)
    return [
        {
            "uid": a.uid, "numero": a.numero, "article_vise": a.article_vise,
            "etat": a.etat, "sort": a.sort, "auteur_ref": a.auteur_ref,
            "date_depot": a.date_depot.isoformat() if a.date_depot else None,
            "themes": json.loads(a.themes) if a.themes else [],
            "resume_ia": a.resume_ia,
        }
        for a in result.scalars().all()
    ]

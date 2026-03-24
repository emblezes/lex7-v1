"""Routes acteurs (députés, sénateurs)."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from legix.api.deps import PaginationParams, get_db
from legix.core.models import Acteur, Amendement, Organe

router = APIRouter()


def _serialize_acteur(a: Acteur, groupe: Organe | None = None) -> dict:
    gp = groupe or a.groupe_politique if hasattr(a, "groupe_politique") and a.groupe_politique else None
    data = {
        "uid": a.uid,
        "civilite": a.civilite,
        "prenom": a.prenom,
        "nom": a.nom,
        "groupe_politique_ref": a.groupe_politique_ref,
        "profession": a.profession,
        "date_naissance": str(a.date_naissance) if a.date_naissance else None,
        "email": a.email,
        "telephone": a.telephone,
        "telephone_2": a.telephone_2,
        "site_web": a.site_web,
        "twitter": a.twitter,
        "facebook": a.facebook,
        "instagram": a.instagram,
        "linkedin": a.linkedin,
        "adresse_an": a.adresse_an,
        "adresse_circo": a.adresse_circo,
        "collaborateurs": json.loads(a.collaborateurs) if a.collaborateurs else [],
        "hatvp_url": a.hatvp_url,
        "source": a.source,
    }
    if gp:
        data["groupe_politique"] = {
            "uid": gp.uid,
            "libelle": gp.libelle,
            "libelle_court": gp.libelle_court,
        }
    return data


@router.get("/acteurs/groupes")
async def list_groupes(db: AsyncSession = Depends(get_db)):
    """Liste des groupes politiques avec nombre de deputes."""
    result = await db.execute(
        select(
            Organe.uid,
            Organe.libelle,
            Organe.libelle_court,
            func.count(Acteur.uid).label("nb_deputes"),
        )
        .join(Acteur, Acteur.groupe_politique_ref == Organe.uid)
        .where(Organe.type_code == "GP")
        .group_by(Organe.uid, Organe.libelle, Organe.libelle_court)
        .order_by(func.count(Acteur.uid).desc())
    )
    return [
        {"uid": r.uid, "libelle": r.libelle, "libelle_court": r.libelle_court, "nb_deputes": r.nb_deputes}
        for r in result.all()
    ]


@router.get("/acteurs")
async def list_acteurs(
    groupe_ref: str | None = None,
    search: str | None = None,
    with_stats: bool = Query(False, description="Inclure stats amendements par acteur"),
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Acteur)
        .options(joinedload(Acteur.groupe_politique))
        .order_by(Acteur.nom)
    )

    if groupe_ref:
        stmt = stmt.where(Acteur.groupe_politique_ref == groupe_ref)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(Acteur.nom.ilike(pattern) | Acteur.prenom.ilike(pattern))

    # Compter le total (avant pagination)
    count_stmt = select(func.count(Acteur.uid))
    if groupe_ref:
        count_stmt = count_stmt.where(Acteur.groupe_politique_ref == groupe_ref)
    if search:
        pattern = f"%{search}%"
        count_stmt = count_stmt.where(Acteur.nom.ilike(pattern) | Acteur.prenom.ilike(pattern))
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.offset(pagination.offset).limit(pagination.limit)
    result = await db.execute(stmt)
    acteurs = result.unique().scalars().all()

    items = [_serialize_acteur(a) for a in acteurs]

    # Stats amendements si demande
    if with_stats and acteurs:
        uids = [a.uid for a in acteurs]

        # Nombre d'amendements par acteur
        nb_result = await db.execute(
            select(Amendement.auteur_ref, func.count(Amendement.uid))
            .where(Amendement.auteur_ref.in_(uids))
            .group_by(Amendement.auteur_ref)
        )
        nb_map = dict(nb_result.all())

        # Nombre d'adoptes par acteur
        adopt_result = await db.execute(
            select(Amendement.auteur_ref, func.count(Amendement.uid))
            .where(
                Amendement.auteur_ref.in_(uids),
                Amendement.sort.ilike("%adopt%"),
            )
            .group_by(Amendement.auteur_ref)
        )
        adopt_map = dict(adopt_result.all())

        for item in items:
            uid = item["uid"]
            nb = nb_map.get(uid, 0)
            nb_adoptes = adopt_map.get(uid, 0)
            item["stats"] = {
                "nb_amendements": nb,
                "nb_adoptes": nb_adoptes,
                "taux_adoption": round(nb_adoptes / nb, 3) if nb > 0 else 0,
            }

    return {"items": items, "total": total}


@router.get("/acteurs/{uid}")
async def get_acteur(uid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Acteur)
        .options(joinedload(Acteur.groupe_politique))
        .where(Acteur.uid == uid)
    )
    acteur = result.unique().scalars().first()
    if not acteur:
        raise HTTPException(status_code=404, detail="Acteur non trouve")

    data = _serialize_acteur(acteur)

    # Intelligence : stats adoption, themes, derniers amendements, textes deposes
    from legix.agents.intelligence import (
        depute_full_profile,
        depute_adoption_by_theme,
        depute_cosignataires_frequents,
        depute_recent_activity,
        depute_textes_deposes,
    )

    profile = await depute_full_profile(db, uid)
    if "error" not in profile:
        data["intelligence"] = {
            "stats": profile["stats"],
            "adoption_par_theme": dict(
                list((await depute_adoption_by_theme(db, uid)).items())[:8]
            ),
            "cosignataires_frequents": await depute_cosignataires_frequents(db, uid, limit=5),
            "activite_recente_30j": await depute_recent_activity(db, uid, days=30),
            "textes_deposes": await depute_textes_deposes(db, uid, limit=20),
        }

    return data


@router.get("/acteurs/{uid}/influence")
async def get_acteur_influence(uid: str, db: AsyncSession = Depends(get_db)):
    """Calcule et retourne le score d'influence d'un acteur."""
    from legix.services.acteur_influence import compute_influence_score
    result = await compute_influence_score(db, uid)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/acteurs/{uid}/amendements")
async def get_acteur_amendements(
    uid: str,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Amendement)
        .where(Amendement.auteur_ref == uid)
        .order_by(Amendement.date_depot.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    result = await db.execute(stmt)
    return [
        {
            "uid": a.uid, "numero": a.numero, "texte_ref": a.texte_ref,
            "article_vise": a.article_vise, "etat": a.etat, "sort": a.sort,
            "date_depot": a.date_depot.isoformat() if a.date_depot else None,
        }
        for a in result.scalars().all()
    ]

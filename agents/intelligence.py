"""Fonctions d'intelligence legislative — memoire de l'agent.

Requetes SQL async qui exploitent la DB (amendements, votes, cosignatures)
pour produire des analyses riches. Utilisees comme outils agent via chat_tools.
"""

import json
from datetime import datetime, timedelta

from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from legix.core.models import (
    Acteur,
    Amendement,
    Organe,
    Texte,
    amendement_cosignataires,
    texte_auteurs,
)
from legix.enrichment.scoring import _adoption_rate, compute_adoption_score


# ── Depute ──────────────────────────────────────────────────────────


async def depute_full_profile(db: AsyncSession, acteur_uid: str) -> dict:
    """Profil complet d'un acteur : identite, groupe, stats globales."""
    result = await db.execute(
        select(Acteur)
        .options(joinedload(Acteur.groupe_politique))
        .where(Acteur.uid == acteur_uid)
    )
    acteur = result.unique().scalars().first()
    if not acteur:
        return {"error": f"Acteur {acteur_uid} non trouve"}

    groupe = acteur.groupe_politique
    nom = f"{acteur.prenom or ''} {acteur.nom or ''}".strip()

    # Stats amendements
    result = await db.execute(
        select(Amendement).where(Amendement.auteur_ref == acteur_uid)
    )
    amdts = result.scalars().all()

    nb_total = len(amdts)
    nb_adoptes = sum(1 for a in amdts if a.sort and "adopt" in a.sort.lower())
    nb_rejetes = sum(1 for a in amdts if a.sort and "rejet" in a.sort.lower())
    nb_retires = sum(1 for a in amdts if a.sort and "retir" in a.sort.lower())
    nb_tombes = sum(1 for a in amdts if a.sort and "tomb" in a.sort.lower())
    nb_sorted = sum(1 for a in amdts if a.sort)
    taux_adoption = _adoption_rate(nb_adoptes, nb_sorted) if nb_sorted > 0 else 0.5

    return {
        "uid": acteur.uid,
        "nom": nom,
        "groupe": (groupe.libelle_court or groupe.libelle) if groupe else None,
        "groupe_uid": groupe.uid if groupe else None,
        "profession": acteur.profession,
        "email": acteur.email,
        "stats": {
            "nb_amendements": nb_total,
            "nb_adoptes": nb_adoptes,
            "nb_rejetes": nb_rejetes,
            "nb_retires": nb_retires,
            "nb_tombes": nb_tombes,
            "taux_adoption": round(taux_adoption, 3),
        },
    }


async def depute_adoption_by_theme(
    db: AsyncSession, acteur_uid: str
) -> dict[str, dict]:
    """Taux d'adoption par theme pour un acteur. Retourne top themes."""
    result = await db.execute(
        select(Amendement).where(Amendement.auteur_ref == acteur_uid)
    )
    amdts = result.scalars().all()

    theme_stats: dict[str, dict] = {}
    for a in amdts:
        themes = json.loads(a.themes) if a.themes else []
        for t in themes:
            if t not in theme_stats:
                theme_stats[t] = {"total": 0, "adoptes": 0}
            theme_stats[t]["total"] += 1
            if a.sort and "adopt" in a.sort.lower():
                theme_stats[t]["adoptes"] += 1

    # Calculer taux et trier par activite
    result_themes = {}
    for t, s in sorted(theme_stats.items(), key=lambda x: -x[1]["total"]):
        result_themes[t] = {
            "total": s["total"],
            "adoptes": s["adoptes"],
            "taux_adoption": round(_adoption_rate(s["adoptes"], s["total"]), 3),
        }

    return result_themes


async def depute_cosignataires_frequents(
    db: AsyncSession, acteur_uid: str, limit: int = 5
) -> list[dict]:
    """Cosignataires les plus frequents d'un depute."""
    # Amendements de cet acteur
    amdt_uids_stmt = select(Amendement.uid).where(
        Amendement.auteur_ref == acteur_uid
    )

    # Cosignataires sur ces amendements
    result = await db.execute(
        select(
            amendement_cosignataires.c.acteur_uid,
            func.count().label("count"),
        )
        .where(
            amendement_cosignataires.c.amendement_uid.in_(amdt_uids_stmt),
            amendement_cosignataires.c.acteur_uid != acteur_uid,
        )
        .group_by(amendement_cosignataires.c.acteur_uid)
        .order_by(func.count().desc())
        .limit(limit)
    )
    rows = result.all()

    cosignataires = []
    for uid, count in rows:
        acteur_result = await db.execute(
            select(Acteur)
            .options(joinedload(Acteur.groupe_politique))
            .where(Acteur.uid == uid)
        )
        a = acteur_result.unique().scalars().first()
        if a:
            cosignataires.append({
                "uid": a.uid,
                "nom": f"{a.prenom or ''} {a.nom or ''}".strip(),
                "groupe": (
                    a.groupe_politique.libelle_court
                    if a.groupe_politique
                    else None
                ),
                "nb_cosignatures": count,
            })

    return cosignataires


async def depute_recent_activity(
    db: AsyncSession, acteur_uid: str, days: int = 30
) -> list[dict]:
    """Amendements recents d'un depute, avec titre du texte parent."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(Amendement)
        .options(joinedload(Amendement.groupe), joinedload(Amendement.texte))
        .where(
            Amendement.auteur_ref == acteur_uid,
            Amendement.date_depot >= cutoff,
        )
        .order_by(Amendement.date_depot.desc())
        .limit(10)
    )
    amdts = result.unique().scalars().all()

    return [
        {
            "uid": a.uid,
            "numero": a.numero,
            "texte_ref": a.texte_ref,
            "texte_titre": (
                a.texte.titre_court or a.texte.titre if a.texte else None
            ),
            "article_vise": a.article_vise,
            "sort": a.sort,
            "etat": a.etat,
            "date_depot": str(a.date_depot) if a.date_depot else None,
            "themes": json.loads(a.themes) if a.themes else [],
            "resume_ia": a.resume_ia,
        }
        for a in amdts
    ]


async def depute_textes_deposes(
    db: AsyncSession, acteur_uid: str, limit: int = 20
) -> list[dict]:
    """Textes deposes par un acteur (via table texte_auteurs)."""
    result = await db.execute(
        select(Texte)
        .join(texte_auteurs, texte_auteurs.c.texte_uid == Texte.uid)
        .where(texte_auteurs.c.acteur_uid == acteur_uid)
        .order_by(Texte.date_depot.desc())
        .limit(limit)
    )
    textes = result.scalars().all()

    return [
        {
            "uid": t.uid,
            "titre": t.titre_court or t.titre,
            "type_code": t.type_code,
            "denomination": t.denomination,
            "date_depot": str(t.date_depot) if t.date_depot else None,
            "themes": json.loads(t.themes) if t.themes else [],
            "source": t.source,
        }
        for t in textes
    ]


async def depute_by_name(db: AsyncSession, name: str) -> Acteur | None:
    """Trouve un acteur par nom (recherche flexible)."""
    pattern = f"%{name}%"
    result = await db.execute(
        select(Acteur)
        .options(joinedload(Acteur.groupe_politique))
        .where(Acteur.nom.ilike(pattern) | Acteur.prenom.ilike(pattern))
    )
    return result.unique().scalars().first()


# ── Groupe politique ────────────────────────────────────────────────


async def groupe_adoption_rate(
    db: AsyncSession, groupe_uid: str, theme: str | None = None
) -> dict:
    """Taux d'adoption d'un groupe, global ou filtre par theme."""
    result = await db.execute(
        select(Organe).where(Organe.uid == groupe_uid)
    )
    organe = result.scalars().first()
    if not organe:
        return {"error": f"Groupe {groupe_uid} non trouve"}

    stmt = select(Amendement).where(Amendement.groupe_ref == groupe_uid)
    if theme:
        stmt = stmt.where(Amendement.themes.ilike(f'%"{theme}"%'))

    result = await db.execute(stmt)
    amdts = result.scalars().all()

    nb_total = len(amdts)
    nb_sorted = sum(1 for a in amdts if a.sort)
    nb_adoptes = sum(1 for a in amdts if a.sort and "adopt" in a.sort.lower())
    nb_rejetes = sum(1 for a in amdts if a.sort and "rejet" in a.sort.lower())
    taux = _adoption_rate(nb_adoptes, nb_sorted) if nb_sorted > 0 else 0.5

    # Themes principaux du groupe
    theme_counts: dict[str, int] = {}
    for a in amdts:
        for t in json.loads(a.themes) if a.themes else []:
            theme_counts[t] = theme_counts.get(t, 0) + 1
    top_themes = sorted(theme_counts.items(), key=lambda x: -x[1])[:8]

    return {
        "groupe": organe.libelle_court or organe.libelle,
        "uid": organe.uid,
        "filtre_theme": theme,
        "stats": {
            "nb_amendements": nb_total,
            "nb_sorted": nb_sorted,
            "nb_adoptes": nb_adoptes,
            "nb_rejetes": nb_rejetes,
            "taux_adoption": round(taux, 3),
        },
        "themes_principaux": [
            {"theme": t, "count": c} for t, c in top_themes
        ],
    }


async def groupe_top_deputes(
    db: AsyncSession, groupe_uid: str, limit: int = 5
) -> list[dict]:
    """Deputes les plus actifs d'un groupe."""
    result = await db.execute(
        select(
            Amendement.auteur_ref,
            func.count().label("count"),
        )
        .where(
            Amendement.groupe_ref == groupe_uid,
            Amendement.auteur_ref.isnot(None),
        )
        .group_by(Amendement.auteur_ref)
        .order_by(func.count().desc())
        .limit(limit)
    )
    rows = result.all()

    deputes = []
    for uid, count in rows:
        acteur_result = await db.execute(
            select(Acteur).where(Acteur.uid == uid)
        )
        a = acteur_result.scalars().first()
        if a:
            # Taux adoption individuel
            total = (await db.execute(
                select(func.count()).where(
                    Amendement.auteur_ref == uid,
                    Amendement.sort.isnot(None),
                )
            )).scalar() or 0
            adopted = (await db.execute(
                select(func.count()).where(
                    Amendement.auteur_ref == uid,
                    Amendement.sort.ilike("%adopt%"),
                )
            )).scalar() or 0

            deputes.append({
                "uid": a.uid,
                "nom": f"{a.prenom or ''} {a.nom or ''}".strip(),
                "nb_amendements": count,
                "taux_adoption": round(_adoption_rate(adopted, total), 3),
            })

    return deputes


async def groupe_by_name(db: AsyncSession, name: str) -> Organe | None:
    """Trouve un groupe par nom (recherche flexible)."""
    pattern = f"%{name}%"
    result = await db.execute(
        select(Organe).where(
            and_(
                Organe.type_code == "GP",
                Organe.libelle_court.ilike(pattern)
                | Organe.libelle.ilike(pattern),
            )
        )
    )
    return result.scalars().first()


# ── Texte / dynamique ──────────────────────────────────────────────


async def texte_amendment_dynamics(db: AsyncSession, texte_uid: str) -> dict:
    """Dynamique complete des amendements sur un texte."""
    result = await db.execute(
        select(Texte).where(Texte.uid == texte_uid)
    )
    texte = result.scalars().first()
    if not texte:
        return {"error": f"Texte {texte_uid} non trouve"}

    result = await db.execute(
        select(Amendement)
        .options(joinedload(Amendement.auteur), joinedload(Amendement.groupe))
        .where(Amendement.texte_ref == texte_uid)
    )
    amdts = result.unique().scalars().all()

    nb_total = len(amdts)
    nb_adoptes = sum(1 for a in amdts if a.sort and "adopt" in a.sort.lower())
    nb_rejetes = sum(1 for a in amdts if a.sort and "rejet" in a.sort.lower())
    nb_gouv = sum(
        1 for a in amdts
        if a.auteur_type and "gouvernement" in a.auteur_type.lower()
    )

    # Groupes impliques
    groupe_stats: dict[str, dict] = {}
    for a in amdts:
        gname = (
            (a.groupe.libelle_court or a.groupe.libelle) if a.groupe else "Inconnu"
        )
        if gname not in groupe_stats:
            groupe_stats[gname] = {"total": 0, "adoptes": 0}
        groupe_stats[gname]["total"] += 1
        if a.sort and "adopt" in a.sort.lower():
            groupe_stats[gname]["adoptes"] += 1

    groupes = [
        {
            "groupe": g,
            "nb_amendements": s["total"],
            "nb_adoptes": s["adoptes"],
            "taux_adoption": round(
                _adoption_rate(s["adoptes"], s["total"]), 3
            ),
        }
        for g, s in sorted(groupe_stats.items(), key=lambda x: -x[1]["total"])
    ]

    # Deputes les plus actifs
    depute_counts: dict[str, dict] = {}
    for a in amdts:
        if a.auteur_ref and a.auteur:
            nom = f"{a.auteur.prenom or ''} {a.auteur.nom or ''}".strip()
            if nom not in depute_counts:
                depute_counts[nom] = {"total": 0, "adoptes": 0}
            depute_counts[nom]["total"] += 1
            if a.sort and "adopt" in a.sort.lower():
                depute_counts[nom]["adoptes"] += 1

    top_deputes = [
        {"nom": n, "nb_amendements": s["total"], "nb_adoptes": s["adoptes"]}
        for n, s in sorted(depute_counts.items(), key=lambda x: -x[1]["total"])[:5]
    ]

    # Themes des amendements
    theme_counts: dict[str, int] = {}
    for a in amdts:
        for t in json.loads(a.themes) if a.themes else []:
            theme_counts[t] = theme_counts.get(t, 0) + 1
    top_themes = sorted(theme_counts.items(), key=lambda x: -x[1])[:5]

    return {
        "texte": {
            "uid": texte.uid,
            "titre": texte.titre_court or texte.titre,
            "type": texte.type_code,
            "themes": json.loads(texte.themes) if texte.themes else [],
        },
        "stats": {
            "nb_amendements": nb_total,
            "nb_adoptes": nb_adoptes,
            "nb_rejetes": nb_rejetes,
            "nb_gouvernementaux": nb_gouv,
            "taux_adoption": round(
                _adoption_rate(nb_adoptes, nb_total), 3
            ) if nb_total > 0 else 0,
        },
        "groupes": groupes,
        "deputes_actifs": top_deputes,
        "themes_amendements": [
            {"theme": t, "count": c} for t, c in top_themes
        ],
        "signal_acceleration_gouv": nb_gouv >= 3,
    }


# ── Amendement / reseau ────────────────────────────────────────────


async def amendement_cosignataire_network(
    db: AsyncSession, amdt_uid: str
) -> dict:
    """Reseau complet d'un amendement : auteur, cosignataires, score."""
    result = await db.execute(
        select(Amendement)
        .options(
            joinedload(Amendement.auteur),
            joinedload(Amendement.groupe),
            joinedload(Amendement.texte),
        )
        .where(Amendement.uid == amdt_uid)
    )
    amdt = result.unique().scalars().first()
    if not amdt:
        return {"error": f"Amendement {amdt_uid} non trouve"}

    # Profil auteur
    auteur_profile = None
    if amdt.auteur_ref:
        auteur_profile = await depute_full_profile(db, amdt.auteur_ref)

    # Score adoption
    score = await compute_adoption_score(db, amdt)

    # Cosignataires
    result = await db.execute(
        select(amendement_cosignataires.c.acteur_uid).where(
            amendement_cosignataires.c.amendement_uid == amdt_uid
        )
    )
    cosig_uids = [row[0] for row in result.all()]

    cosignataires = []
    groupes_set = set()
    for uid in cosig_uids:
        acteur_result = await db.execute(
            select(Acteur)
            .options(joinedload(Acteur.groupe_politique))
            .where(Acteur.uid == uid)
        )
        a = acteur_result.unique().scalars().first()
        if a:
            gnom = (
                a.groupe_politique.libelle_court
                if a.groupe_politique
                else None
            )
            if gnom:
                groupes_set.add(gnom)
            cosignataires.append({
                "uid": a.uid,
                "nom": f"{a.prenom or ''} {a.nom or ''}".strip(),
                "groupe": gnom,
            })

    return {
        "amendement": {
            "uid": amdt.uid,
            "numero": amdt.numero,
            "article_vise": amdt.article_vise,
            "sort": amdt.sort,
            "etat": amdt.etat,
            "themes": json.loads(amdt.themes) if amdt.themes else [],
            "resume_ia": amdt.resume_ia,
        },
        "auteur": auteur_profile,
        "score_adoption": round(score, 3),
        "cosignataires": cosignataires,
        "nb_cosignataires": len(cosignataires),
        "nb_groupes_differents": len(groupes_set),
        "convergence_transpartisane": len(groupes_set) >= 3,
        "texte_parent": {
            "uid": amdt.texte.uid if amdt.texte else None,
            "titre": (
                amdt.texte.titre_court or amdt.texte.titre
                if amdt.texte
                else None
            ),
        },
    }

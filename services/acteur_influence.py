"""Service calcul du scoring d'influence des acteurs."""

import json
import logging

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.models import (
    Acteur,
    Amendement,
    Organe,
    TexteBrief,
    amendement_cosignataires,
)

logger = logging.getLogger(__name__)


async def compute_influence_score(
    db: AsyncSession,
    acteur_uid: str,
) -> dict:
    """Calcule le score d'influence d'un acteur.

    Criteres ponderes :
    - Nombre d'amendements deposes (poids 0.3)
    - Taux d'adoption (poids 0.3)
    - Commissions actives pertinentes (poids 0.2)
    - Convergence transpartisane / cosignatures (poids 0.2)
    """
    acteur = await db.get(Acteur, acteur_uid)
    if not acteur:
        return {"error": f"Acteur {acteur_uid} introuvable"}

    # Nombre d'amendements
    nb_amdts_result = await db.execute(
        select(func.count(Amendement.uid)).where(
            Amendement.auteur_ref == acteur_uid
        )
    )
    nb_amendements = nb_amdts_result.scalar() or 0

    # Taux d'adoption
    nb_adoptes_result = await db.execute(
        select(func.count(Amendement.uid)).where(
            Amendement.auteur_ref == acteur_uid,
            Amendement.sort.ilike("%adopt%"),
        )
    )
    nb_adoptes = nb_adoptes_result.scalar() or 0
    taux_adoption = nb_adoptes / nb_amendements if nb_amendements > 0 else 0

    # Cosignatures (convergence)
    nb_cosig_result = await db.execute(
        select(func.count()).where(
            amendement_cosignataires.c.acteur_uid == acteur_uid
        )
    )
    nb_cosignatures = nb_cosig_result.scalar() or 0

    # Cosignatures multi-groupes (convergence transpartisane)
    cosig_groupes_result = await db.execute(
        select(func.count(func.distinct(Amendement.groupe_ref))).where(
            Amendement.uid.in_(
                select(amendement_cosignataires.c.amendement_uid).where(
                    amendement_cosignataires.c.acteur_uid == acteur_uid
                )
            )
        )
    )
    nb_groupes_cosig = cosig_groupes_result.scalar() or 0

    # Scoring
    # Amendements : 0-100, normalise sur 50 amdts = 100
    score_amendements = min(nb_amendements / 50 * 100, 100)

    # Adoption : 0-100, direct
    score_adoption = taux_adoption * 100

    # Commissions : simpliste — on donne 50 par defaut (pas de donnees structurees)
    score_commissions = 50  # TODO: enrichir quand les donnees de commissions seront disponibles

    # Convergence : normalise sur 20 cosignatures = 100, bonus si multi-groupes
    score_convergence = min(nb_cosignatures / 20 * 80, 80)
    if nb_groupes_cosig >= 3:
        score_convergence = min(score_convergence + 20, 100)

    # Score global pondere
    influence_score = round(
        score_amendements * 0.3
        + score_adoption * 0.3
        + score_commissions * 0.2
        + score_convergence * 0.2,
        1,
    )

    return {
        "uid": acteur_uid,
        "nom": f"{acteur.prenom or ''} {acteur.nom or ''}".strip(),
        "influence_score": influence_score,
        "breakdown": {
            "amendements": {
                "score": round(score_amendements, 1),
                "count": nb_amendements,
                "weight": 0.3,
            },
            "adoption": {
                "score": round(score_adoption, 1),
                "rate": round(taux_adoption, 3),
                "adopted": nb_adoptes,
                "total": nb_amendements,
                "weight": 0.3,
            },
            "commissions": {
                "score": round(score_commissions, 1),
                "weight": 0.2,
            },
            "convergence": {
                "score": round(score_convergence, 1),
                "cosignatures": nb_cosignatures,
                "groupes_differents": nb_groupes_cosig,
                "weight": 0.2,
            },
        },
    }


async def get_dossier_acteurs_cles(
    db: AsyncSession,
    texte_uid: str,
    profile_id: int,
    limit: int = 10,
) -> list[dict]:
    """Retourne les acteurs cles d'un dossier avec scores d'influence.

    Combine les key_contacts du brief avec une analyse des auteurs
    d'amendements critiques, et enrichit chaque acteur.
    """
    from sqlalchemy.orm import joinedload

    # Charger le brief
    result = await db.execute(
        select(TexteBrief).where(
            TexteBrief.profile_id == profile_id,
            TexteBrief.texte_uid == texte_uid,
        )
    )
    brief = result.scalar_one_or_none()

    acteur_uids: dict[str, dict] = {}

    # 1. key_contacts du brief
    if brief and brief.key_contacts:
        try:
            contacts = json.loads(brief.key_contacts)
            for c in contacts:
                uid = c.get("uid")
                if uid:
                    acteur_uids[uid] = {
                        "source": "brief",
                        "nb_amendements_dossier": c.get("nb_amendements", 0),
                        "taux_adoption_dossier": c.get("taux_adoption", 0),
                        "why_relevant": c.get("why_relevant", ""),
                    }
        except (json.JSONDecodeError, TypeError):
            pass

    # 2. Auteurs d'amendements sur ce texte (top par volume)
    stmt = (
        select(
            Amendement.auteur_ref,
            func.count(Amendement.uid).label("nb"),
        )
        .where(
            Amendement.texte_ref == texte_uid,
            Amendement.auteur_ref.isnot(None),
        )
        .group_by(Amendement.auteur_ref)
        .order_by(func.count(Amendement.uid).desc())
        .limit(20)
    )
    result = await db.execute(stmt)
    for row in result.all():
        uid = row[0]
        if uid and uid not in acteur_uids:
            acteur_uids[uid] = {
                "source": "amendements",
                "nb_amendements_dossier": row[1],
            }

    # 3. Enrichir chaque acteur avec son score d'influence
    enriched = []
    for uid, ctx in list(acteur_uids.items())[:limit]:
        influence = await compute_influence_score(db, uid)
        if "error" in influence:
            continue

        # Charger l'acteur pour le groupe
        acteur = await db.get(Acteur, uid)
        groupe_nom = None
        if acteur and acteur.groupe_politique_ref:
            groupe = await db.get(Organe, acteur.groupe_politique_ref)
            if groupe:
                groupe_nom = groupe.libelle_court or groupe.libelle

        enriched.append({
            **influence,
            "groupe": groupe_nom,
            "nb_amendements_dossier": ctx.get("nb_amendements_dossier", 0),
            "taux_adoption_dossier": ctx.get("taux_adoption_dossier", 0),
            "why_relevant": ctx.get("why_relevant", ""),
            "source": ctx.get("source", ""),
        })

    # Tri par influence_score desc
    enriched.sort(key=lambda x: x.get("influence_score", 0), reverse=True)
    return enriched[:limit]

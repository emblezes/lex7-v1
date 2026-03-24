"""Scoring — probabilité d'adoption des amendements.

Score composite 0-1 :
  - Taux auteur   (35%)
  - Taux groupe   (30%)
  - Taux commission (20%)
  - Bonus gouvernement (15%)
"""

import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.models import Amendement


def _adoption_rate(adopted: int, total: int) -> float:
    if total == 0:
        return 0.5
    return (adopted + 1) / (total + 2)


async def compute_adoption_score(db: AsyncSession, amdt: Amendement) -> float:
    """Calcule un score composite de probabilité d'adoption (0-1)."""
    breakdown = await compute_adoption_score_detailed(db, amdt)
    return breakdown["score"]


async def compute_adoption_score_detailed(db: AsyncSession, amdt: Amendement) -> dict:
    """Calcule le score avec le detail de chaque facteur."""
    # --- Taux auteur (35%) ---
    auteur_rate = 0.5
    auteur_total = 0
    auteur_adopted = 0
    if amdt.auteur_ref:
        auteur_total = (await db.execute(
            select(func.count(Amendement.uid)).where(
                Amendement.auteur_ref == amdt.auteur_ref, Amendement.sort.isnot(None),
            )
        )).scalar() or 0
        auteur_adopted = (await db.execute(
            select(func.count(Amendement.uid)).where(
                Amendement.auteur_ref == amdt.auteur_ref, Amendement.sort.ilike("%adopt%"),
            )
        )).scalar() or 0
        auteur_rate = _adoption_rate(auteur_adopted, auteur_total)

    # --- Taux groupe (30%) ---
    groupe_rate = 0.5
    groupe_total = 0
    groupe_adopted = 0
    if amdt.groupe_ref:
        groupe_total = (await db.execute(
            select(func.count(Amendement.uid)).where(
                Amendement.groupe_ref == amdt.groupe_ref, Amendement.sort.isnot(None),
            )
        )).scalar() or 0
        groupe_adopted = (await db.execute(
            select(func.count(Amendement.uid)).where(
                Amendement.groupe_ref == amdt.groupe_ref, Amendement.sort.ilike("%adopt%"),
            )
        )).scalar() or 0
        groupe_rate = _adoption_rate(groupe_adopted, groupe_total)

    # --- Taux commission (20%) ---
    commission_rate = 0.5
    commission_total = 0
    commission_adopted = 0
    if amdt.organe_examen:
        commission_total = (await db.execute(
            select(func.count(Amendement.uid)).where(
                Amendement.organe_examen == amdt.organe_examen, Amendement.sort.isnot(None),
            )
        )).scalar() or 0
        commission_adopted = (await db.execute(
            select(func.count(Amendement.uid)).where(
                Amendement.organe_examen == amdt.organe_examen, Amendement.sort.ilike("%adopt%"),
            )
        )).scalar() or 0
        commission_rate = _adoption_rate(commission_adopted, commission_total)

    # --- Bonus gouvernement (15%) ---
    is_gouvernement = bool(
        amdt.auteur_type and "gouvernement" in amdt.auteur_type.lower()
    )
    gouv_score = 0.9 if is_gouvernement else 0.0

    score = (
        auteur_rate * 0.35
        + groupe_rate * 0.30
        + commission_rate * 0.20
        + gouv_score * 0.15
    )
    score = round(min(max(score, 0.0), 1.0), 3)

    return {
        "score": score,
        "auteur": {
            "rate": round(auteur_rate, 3),
            "adopted": auteur_adopted,
            "total": auteur_total,
            "weight": 0.35,
        },
        "groupe": {
            "rate": round(groupe_rate, 3),
            "adopted": groupe_adopted,
            "total": groupe_total,
            "weight": 0.30,
        },
        "commission": {
            "rate": round(commission_rate, 3),
            "adopted": commission_adopted,
            "total": commission_total,
            "weight": 0.20,
        },
        "gouvernement": {
            "is_gouvernement": is_gouvernement,
            "score": gouv_score,
            "weight": 0.15,
        },
    }


async def batch_compute_scores(db: AsyncSession) -> int:
    """Calcule les scores pour les amendements qui en ont besoin.

    Cible :
    1. Amendements sans score (nouveaux)
    2. Amendements dont le sort a change recemment (updated_at > scored_at)
       → on detecte ca via un sort non vide + score present mais ancien
    """
    from datetime import datetime, timedelta

    count = 0

    # 1. Amendements sans score (nouveaux)
    stmt = select(Amendement).where(
        Amendement.score_impact.is_(None) | (Amendement.score_impact == "")
    )
    result = await db.execute(stmt)
    for amdt in result.scalars().all():
        try:
            score = await compute_adoption_score(db, amdt)
            amdt.score_impact = json.dumps({"adoption_score": score})
            count += 1
        except Exception:
            continue

    # 2. Amendements avec sort change recemment (updated_at dans les 24h)
    # et qui ont deja un score → re-scorer
    cutoff = datetime.utcnow() - timedelta(hours=24)
    stmt2 = select(Amendement).where(
        Amendement.score_impact.isnot(None),
        Amendement.updated_at >= cutoff,
        Amendement.sort.isnot(None),
        Amendement.sort != "",
    )
    result2 = await db.execute(stmt2)
    for amdt in result2.scalars().all():
        try:
            score = await compute_adoption_score(db, amdt)
            amdt.score_impact = json.dumps({"adoption_score": score})
            count += 1
        except Exception:
            continue

    if count > 0:
        await db.commit()
    return count

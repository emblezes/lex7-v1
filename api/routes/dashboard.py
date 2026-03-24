"""Route dashboard — stats agrégées et feed temps réel."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.api.deps import get_current_profile, get_db
from legix.core.models import Amendement, ClientProfile, ImpactAlert, Reunion, Signal, Texte

router = APIRouter()


@router.get("/dashboard")
async def get_dashboard(
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Stats agrégées pour le tableau de bord principal."""
    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    # Compteurs
    urgent_count = (await db.execute(
        select(func.count(ImpactAlert.id)).where(
            ImpactAlert.profile_id == profile.id,
            ImpactAlert.impact_level == "critical", ImpactAlert.is_read == False,  # noqa: E712
        )
    )).scalar() or 0

    watch_count = (await db.execute(
        select(func.count(ImpactAlert.id)).where(
            ImpactAlert.profile_id == profile.id,
            ImpactAlert.impact_level.in_(["high", "medium"]), ImpactAlert.is_read == False,  # noqa: E712
        )
    )).scalar() or 0

    total_exposure = (await db.execute(
        select(func.sum(ImpactAlert.exposure_eur)).where(
            ImpactAlert.profile_id == profile.id,
            ImpactAlert.is_read == False,  # noqa: E712
        )
    )).scalar() or 0

    # Signaux récents
    signals_result = await db.execute(
        select(Signal)
        .where(Signal.created_at >= last_7d, Signal.is_dismissed == False)  # noqa: E712
        .order_by(Signal.created_at.desc())
        .limit(10)
    )
    signals = [
        {
            "id": s.id, "type": s.signal_type, "severity": s.severity,
            "title": s.title, "created_at": s.created_at.isoformat(),
        }
        for s in signals_result.scalars().all()
    ]

    # Textes récents
    textes_result = await db.execute(
        select(Texte)
        .where(Texte.created_at >= last_24h)
        .order_by(Texte.created_at.desc())
        .limit(10)
    )
    recent_textes = [
        {
            "uid": t.uid, "titre": t.titre_court or t.titre,
            "type": t.type_code, "source": t.source,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in textes_result.scalars().all()
    ]

    # Amendements récents
    amdts_result = await db.execute(
        select(Amendement)
        .where(Amendement.created_at >= last_24h)
        .order_by(Amendement.created_at.desc())
        .limit(10)
    )
    recent_amdts = [
        {
            "uid": a.uid, "numero": a.numero,
            "texte_ref": a.texte_ref, "etat": a.etat,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in amdts_result.scalars().all()
    ]

    # Réunions à venir
    reunions_result = await db.execute(
        select(Reunion)
        .where(Reunion.date_debut >= now)
        .order_by(Reunion.date_debut.asc())
        .limit(5)
    )
    upcoming_reunions = [
        {
            "uid": r.uid, "date_debut": r.date_debut.isoformat() if r.date_debut else None,
            "organe_ref": r.organe_ref, "etat": r.etat,
        }
        for r in reunions_result.scalars().all()
    ]

    return {
        "stats": {
            "urgent": urgent_count,
            "watch": watch_count,
            "exposure_eur": round(total_exposure, 2),
        },
        "signals": signals,
        "recent_textes": recent_textes,
        "recent_amendements": recent_amdts,
        "upcoming_reunions": upcoming_reunions,
    }

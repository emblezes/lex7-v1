"""Routes signaux faibles."""

import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.api.deps import PaginationParams, get_db
from legix.core.models import Signal

router = APIRouter()


def _serialize_signal(s: Signal) -> dict:
    return {
        "id": s.id,
        "signal_type": s.signal_type,
        "severity": s.severity,
        "title": s.title,
        "description": s.description,
        "themes": json.loads(s.themes) if s.themes else [],
        "texte_ref": s.texte_ref,
        "amendement_refs": json.loads(s.amendement_refs) if s.amendement_refs else [],
        "data_snapshot": json.loads(s.data_snapshot) if s.data_snapshot else {},
        "is_read": s.is_read,
        "is_dismissed": s.is_dismissed,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.get("/signaux")
async def list_signaux(
    signal_type: str | None = None,
    severity: str | None = None,
    unread_only: bool = False,
    days: int = Query(30, ge=1, le=365),
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.utcnow() - timedelta(days=days)
    stmt = select(Signal).where(
        Signal.created_at >= cutoff, Signal.is_dismissed == False,  # noqa: E712
    ).order_by(Signal.created_at.desc())

    if signal_type:
        stmt = stmt.where(Signal.signal_type == signal_type)
    if severity:
        stmt = stmt.where(Signal.severity == severity)
    if unread_only:
        stmt = stmt.where(Signal.is_read == False)  # noqa: E712

    stmt = stmt.offset(pagination.offset).limit(pagination.limit)
    result = await db.execute(stmt)
    return [_serialize_signal(s) for s in result.scalars().all()]


@router.get("/signaux/summary")
async def signaux_summary(db: AsyncSession = Depends(get_db)):
    cutoff = datetime.utcnow() - timedelta(days=7)

    # Counts par type
    type_counts = {}
    stmt = (
        select(Signal.signal_type, func.count(Signal.id))
        .where(Signal.created_at >= cutoff, Signal.is_dismissed == False)  # noqa: E712
        .group_by(Signal.signal_type)
    )
    for row in (await db.execute(stmt)).all():
        type_counts[row[0]] = row[1]

    # Counts par severity
    severity_counts = {}
    stmt = (
        select(Signal.severity, func.count(Signal.id))
        .where(Signal.created_at >= cutoff, Signal.is_dismissed == False)  # noqa: E712
        .group_by(Signal.severity)
    )
    for row in (await db.execute(stmt)).all():
        severity_counts[row[0]] = row[1]

    # 5 derniers
    stmt = (
        select(Signal)
        .where(Signal.is_dismissed == False)  # noqa: E712
        .order_by(Signal.created_at.desc())
        .limit(5)
    )
    latest = [_serialize_signal(s) for s in (await db.execute(stmt)).scalars().all()]

    return {
        "by_type": type_counts,
        "by_severity": severity_counts,
        "latest": latest,
    }


@router.get("/signaux/{signal_id}")
async def get_signal(signal_id: int, db: AsyncSession = Depends(get_db)):
    signal = await db.get(Signal, signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail="Signal non trouvé")
    return _serialize_signal(signal)


@router.put("/signaux/{signal_id}/read")
async def mark_signal_read(signal_id: int, db: AsyncSession = Depends(get_db)):
    signal = await db.get(Signal, signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail="Signal non trouvé")
    signal.is_read = True
    await db.commit()
    return {"status": "ok"}


@router.put("/signaux/{signal_id}/dismiss")
async def dismiss_signal(signal_id: int, db: AsyncSession = Depends(get_db)):
    signal = await db.get(Signal, signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail="Signal non trouvé")
    signal.is_dismissed = True
    await db.commit()
    return {"status": "ok"}

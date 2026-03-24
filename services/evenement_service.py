"""Service evenements — aggregation multi-source pour la timeline d'un dossier."""

import json
import logging
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.models import (
    Amendement,
    Evenement,
    ImpactAlert,
    TexteFollowUp,
)

logger = logging.getLogger(__name__)


async def get_dossier_evenements(
    db: AsyncSession,
    texte_uid: str,
    profile_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Aggrege tous les evenements d'un dossier en un seul flux.

    Combine :
    1. Evenements stockes en DB (table evenements)
    2. Alertes liees a ce texte_uid
    3. change_log du followup
    4. Amendements recents sur ce texte
    """
    events: list[dict] = []

    # 1. Evenements DB
    stmt = select(Evenement).where(Evenement.texte_uid == texte_uid)
    if profile_id:
        stmt = stmt.where(
            (Evenement.profile_id == profile_id) | (Evenement.profile_id.is_(None))
        )
    result = await db.execute(stmt)
    for ev in result.scalars().all():
        events.append({
            "id": f"ev-{ev.id}",
            "type": ev.event_type,
            "title": ev.title,
            "description": ev.description,
            "severity": ev.severity,
            "source_ref": ev.source_ref,
            "source_url": ev.source_url,
            "date": ev.created_at.isoformat() if ev.created_at else None,
        })

    # 2. Alertes liees au texte
    if profile_id:
        stmt = select(ImpactAlert).where(
            ImpactAlert.texte_uid == texte_uid,
            ImpactAlert.profile_id == profile_id,
        )
        result = await db.execute(stmt)
        for alert in result.scalars().all():
            events.append({
                "id": f"alert-{alert.id}",
                "type": "alerte",
                "title": f"Alerte {alert.impact_level}" + (
                    " — menace" if alert.is_threat else " — opportunite"
                ),
                "description": (alert.impact_summary or "")[:200],
                "severity": alert.impact_level,
                "source_ref": f"alert-{alert.id}",
                "source_url": None,
                "date": alert.created_at.isoformat() if alert.created_at else None,
            })

    # 3. change_log du followup
    if profile_id:
        stmt = select(TexteFollowUp).where(
            TexteFollowUp.texte_uid == texte_uid,
            TexteFollowUp.profile_id == profile_id,
        )
        result = await db.execute(stmt)
        followup = result.scalar_one_or_none()
        if followup and followup.change_log:
            try:
                logs = json.loads(followup.change_log)
                for log in logs:
                    events.append({
                        "id": f"log-{log.get('date', '')}",
                        "type": "suivi",
                        "title": log.get("event", "Mise a jour"),
                        "description": log.get("detail", ""),
                        "severity": "info",
                        "source_ref": None,
                        "source_url": None,
                        "date": log.get("date"),
                    })
            except (json.JSONDecodeError, TypeError):
                pass

    # 4. Amendements recents
    stmt = (
        select(Amendement)
        .where(Amendement.texte_ref == texte_uid)
        .order_by(Amendement.date_depot.desc())
        .limit(20)
    )
    result = await db.execute(stmt)
    for amdt in result.scalars().all():
        severity = "info"
        if amdt.sort and "adopt" in amdt.sort.lower():
            severity = "warning"

        events.append({
            "id": f"amdt-{amdt.uid}",
            "type": "amendement",
            "title": f"Amendement {amdt.numero or amdt.uid}",
            "description": (
                f"par {amdt.auteur_nom or 'Inconnu'}"
                + (f" ({amdt.groupe_nom})" if amdt.groupe_nom else "")
                + (f" — {amdt.sort}" if amdt.sort else "")
            ),
            "severity": severity,
            "source_ref": amdt.uid,
            "source_url": amdt.url_source,
            "date": amdt.date_depot.isoformat() if amdt.date_depot else None,
        })

    # Tri par date desc
    events.sort(
        key=lambda e: e.get("date") or "1970-01-01",
        reverse=True,
    )

    return events[offset:offset + limit]


async def create_evenement(
    db: AsyncSession,
    texte_uid: str,
    event_type: str,
    title: str,
    description: str | None = None,
    severity: str = "info",
    source_ref: str | None = None,
    source_url: str | None = None,
    profile_id: int | None = None,
    data: dict | None = None,
) -> Evenement:
    """Cree un evenement en DB."""
    ev = Evenement(
        texte_uid=texte_uid,
        profile_id=profile_id,
        event_type=event_type,
        title=title,
        description=description,
        severity=severity,
        source_ref=source_ref,
        source_url=source_url,
        data=json.dumps(data, ensure_ascii=False) if data else None,
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return ev

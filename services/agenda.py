"""Service d'anticipation agenda — alertes proactives avant commissions.

Scrute les réunions à venir (J-7, J-3, J-1), matche les thèmes
avec les secteurs des clients, et crée des briefings d'anticipation.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.database import async_session
from legix.core.models import (
    Briefing,
    ClientProfile,
    NotificationQueue,
    Reunion,
)

logger = logging.getLogger(__name__)


async def check_upcoming_reunions():
    """Job périodique : détecte les réunions pertinentes à venir."""
    async with async_session() as db:
        now = datetime.utcnow()

        # Fenêtres d'alerte : J-7, J-3, J-1
        windows = [
            ("J-7", now + timedelta(days=6), now + timedelta(days=8)),
            ("J-3", now + timedelta(days=2), now + timedelta(days=4)),
            ("J-1", now + timedelta(hours=12), now + timedelta(days=2)),
        ]

        profiles_result = await db.execute(
            select(ClientProfile).where(ClientProfile.is_active.is_(True))
        )
        profiles = profiles_result.scalars().all()

        if not profiles:
            return

        for label, window_start, window_end in windows:
            reunions_result = await db.execute(
                select(Reunion).where(
                    Reunion.date_debut >= window_start,
                    Reunion.date_debut < window_end,
                )
            )
            reunions = reunions_result.scalars().all()

            for reunion in reunions:
                for profile in profiles:
                    if _matches_profile(reunion, profile):
                        await _create_agenda_notification(
                            db, reunion, profile, label
                        )

        await db.commit()


def _matches_profile(reunion: Reunion, profile: ClientProfile) -> bool:
    """Vérifie si une réunion concerne les secteurs d'un profil client."""
    odj = (reunion.odj or "").lower()
    lieu = (reunion.lieu or "").lower()
    text = f"{odj} {lieu}"

    if not text.strip():
        return False

    # Matcher sur les secteurs du profil
    sectors = profile.sectors or []
    for sector in sectors:
        sector_lower = sector.lower()
        if sector_lower in text:
            return True

    # Matcher sur les mots-clés du nom de l'entreprise
    if profile.name and profile.name.lower() in text:
        return True

    # Matcher sur les risques clés
    key_risks = profile.key_risks or []
    for risk in key_risks:
        # Prendre les mots significatifs du risque (> 4 chars)
        words = [w.lower() for w in risk.split() if len(w) > 4]
        if any(w in text for w in words):
            return True

    return False


async def _create_agenda_notification(
    db: AsyncSession,
    reunion: Reunion,
    profile: ClientProfile,
    window_label: str,
):
    """Crée une notification proactive pour une réunion à venir."""
    # Éviter les doublons : vérifier si on a déjà notifié pour cette réunion
    existing = await db.execute(
        select(NotificationQueue).where(
            NotificationQueue.profile_id == profile.id,
            NotificationQueue.subject.ilike(f"%{reunion.uid}%"),
        )
    )
    if existing.scalars().first():
        return

    date_str = reunion.date_debut.strftime("%d/%m/%Y %Hh%M") if reunion.date_debut else "N/A"
    organe = reunion.organe_ref or "Commission"
    odj_preview = (reunion.odj or "Ordre du jour non disponible")[:300]

    priority = "instant" if window_label == "J-1" else "normal"
    channel = "telegram" if (window_label == "J-1" and profile.telegram_bot_enabled) else "email"

    db.add(NotificationQueue(
        profile_id=profile.id,
        channel=channel,
        priority=priority,
        subject=f"[{window_label}] Réunion {organe} — {date_str} ({reunion.uid})",
        body=(
            f"Une réunion pertinente pour {profile.name} est prévue {window_label} :\n\n"
            f"Organe : {organe}\n"
            f"Date : {date_str}\n"
            f"Lieu : {reunion.lieu or 'N/A'}\n\n"
            f"Ordre du jour :\n{odj_preview}\n\n"
            f"Nous vous recommandons de préparer un briefing d'anticipation."
        ),
    ))

    logger.info(
        "Notification agenda %s créée pour %s — réunion %s",
        window_label, profile.name, reunion.uid,
    )

"""Service de suivi proactif — mémoire active sur les textes suivis.

Vérifie périodiquement les textes suivis, détecte les changements
(nouveaux amendements, commissions à venir), et relance le client
sur les actions non traitées.
"""

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.database import async_session
from legix.core.models import (
    ActionTask,
    Amendement,
    ClientProfile,
    NotificationQueue,
    TexteFollowUp,
    Texte,
)

logger = logging.getLogger(__name__)


async def check_followups():
    """Job quotidien : re-analyse les textes suivis avec changements."""
    async with async_session() as db:
        now = datetime.utcnow()

        # 1. Textes dont le next_check_at est dépassé
        result = await db.execute(
            select(TexteFollowUp).where(
                TexteFollowUp.status == "watching",
                TexteFollowUp.next_check_at <= now,
            )
        )
        followups = result.scalars().all()

        for fu in followups:
            try:
                await _check_single_followup(db, fu, now)
            except Exception as e:
                logger.error("Erreur suivi texte %s: %s", fu.texte_uid, e)

        # 2. Textes avec commission dans les 3 prochains jours
        upcoming = await db.execute(
            select(TexteFollowUp).where(
                TexteFollowUp.status == "watching",
                TexteFollowUp.commission_date.isnot(None),
                TexteFollowUp.commission_date <= now + timedelta(days=3),
                TexteFollowUp.commission_date > now,
            )
        )
        for fu in upcoming.scalars().all():
            days_until = (fu.commission_date - now).days
            profile = await db.get(ClientProfile, fu.profile_id)
            if not profile:
                continue

            texte = await db.get(Texte, fu.texte_uid)
            titre = (texte.titre_court or texte.titre or fu.texte_uid) if texte else fu.texte_uid

            db.add(NotificationQueue(
                profile_id=fu.profile_id,
                channel="telegram" if profile.telegram_bot_enabled else "email",
                priority="instant" if days_until <= 1 else "normal",
                subject=f"Commission dans {days_until}j — {titre[:60]}",
                body=(
                    f"Le texte « {titre} » passe en commission "
                    f"{'demain' if days_until <= 1 else f'dans {days_until} jours'}.\n\n"
                    f"Priorité : {fu.priority}\n"
                    f"Statut : {fu.status}"
                ),
            ))

        await db.commit()

        if followups:
            logger.info("Suivi textes : %d textes vérifiés", len(followups))


async def _check_single_followup(
    db: AsyncSession, fu: TexteFollowUp, now: datetime
):
    """Vérifie un seul texte suivi pour détecter des changements."""
    # Compter les nouveaux amendements depuis la dernière vérification
    new_amdts_count = await db.execute(
        select(func.count(Amendement.uid)).where(
            Amendement.texte_ref == fu.texte_uid,
            Amendement.created_at >= fu.updated_at,
        )
    )
    new_count = new_amdts_count.scalar() or 0

    if new_count > 0:
        # Log le changement
        changes = json.loads(fu.change_log or "[]")
        changes.append({
            "date": now.isoformat(),
            "event": f"{new_count} nouveaux amendements détectés",
        })
        fu.change_log = json.dumps(changes, ensure_ascii=False)

        # Re-trigger une analyse si > 3 amendements
        if new_count >= 3:
            from legix.agents.trigger import on_new_document
            texte = await db.get(Texte, fu.texte_uid)
            profile = await db.get(ClientProfile, fu.profile_id)
            if texte and profile:
                alerts = await on_new_document(db, texte, profiles=[profile])
                if alerts:
                    changes.append({
                        "date": now.isoformat(),
                        "event": f"Re-analyse déclenchée — {len(alerts)} alertes",
                        "alert_ids": [a.id for a in alerts],
                    })
                    fu.change_log = json.dumps(changes, ensure_ascii=False)
                    fu.last_analysis = json.dumps({
                        "alert_id": alerts[0].id,
                        "impact_level": alerts[0].impact_level,
                        "date": now.isoformat(),
                    })

            # Notifier le client
            if profile:
                db.add(NotificationQueue(
                    profile_id=fu.profile_id,
                    channel="email",
                    priority="normal",
                    subject=f"[LegiX] Activité sur texte suivi — {fu.texte_uid[:30]}",
                    body=(
                        f"{new_count} nouveaux amendements détectés sur un texte que vous suivez.\n"
                        f"Priorité : {fu.priority}"
                    ),
                ))

    # Planifier le prochain check selon la priorité
    intervals = {
        "critical": timedelta(days=1),
        "high": timedelta(days=2),
        "medium": timedelta(days=5),
        "low": timedelta(days=10),
    }
    fu.next_check_at = now + intervals.get(fu.priority, timedelta(days=5))
    fu.updated_at = now


async def check_pending_action_reminders():
    """Job quotidien : relance sur les actions en attente depuis > 48h."""
    async with async_session() as db:
        cutoff = datetime.utcnow() - timedelta(hours=48)

        result = await db.execute(
            select(ActionTask).where(
                ActionTask.status == "pending",
                ActionTask.created_at <= cutoff,
            )
        )
        pending = result.scalars().all()

        for task in pending:
            profile = await db.get(ClientProfile, task.profile_id)
            if not profile:
                continue

            # Vérifier qu'on n'a pas déjà relancé récemment
            existing_notif = await db.execute(
                select(NotificationQueue).where(
                    NotificationQueue.profile_id == task.profile_id,
                    NotificationQueue.subject.ilike(f"%action en attente%{task.label[:30]}%"),
                    NotificationQueue.created_at >= datetime.utcnow() - timedelta(hours=24),
                )
            )
            if existing_notif.scalars().first():
                continue

            db.add(NotificationQueue(
                profile_id=task.profile_id,
                channel="email",
                priority="normal",
                subject=f"[LegiX] Action en attente : {task.label[:60]}",
                body=(
                    f"Vous avez une action en attente depuis plus de 48h :\n\n"
                    f"Action : {task.label}\n"
                    f"Type : {task.action_type}\n"
                    f"Créée le : {task.created_at.strftime('%d/%m/%Y %H:%M') if task.created_at else 'N/A'}\n\n"
                    f"Connectez-vous à LegiX pour la traiter ou la déléguer."
                ),
            ))

        await db.commit()

        if pending:
            logger.info("Relances actions : %d actions en attente > 48h", len(pending))

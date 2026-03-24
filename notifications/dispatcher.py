"""Dispatcher de notifications — traite la NotificationQueue."""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.database import async_session
from legix.core.models import ClientProfile, ImpactAlert, NotificationQueue
from legix.notifications.email import EmailNotifier
from legix.notifications.telegram import TelegramNotifier

logger = logging.getLogger(__name__)

telegram = TelegramNotifier()
email_notifier = EmailNotifier()


def _is_within_notification_hours(profile: ClientProfile) -> bool:
    """Vérifie si l'heure actuelle est dans les heures de notification du client."""
    hours = profile.notification_hours or "08:00-20:00"
    try:
        start_str, end_str = hours.split("-")
        start_h, start_m = map(int, start_str.split(":"))
        end_h, end_m = map(int, end_str.split(":"))
        now = datetime.utcnow()
        current_minutes = now.hour * 60 + now.minute
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m
        return start_minutes <= current_minutes <= end_minutes
    except (ValueError, AttributeError):
        return True  # En cas d'erreur de parsing, on envoie


async def dispatch_pending():
    """Traite toutes les notifications en attente."""
    async with async_session() as db:
        await _dispatch_batch(db)


async def _dispatch_batch(db: AsyncSession):
    """Récupère et envoie les notifications pending."""
    result = await db.execute(
        select(NotificationQueue)
        .where(NotificationQueue.status == "pending")
        .order_by(NotificationQueue.created_at)
        .limit(50)
    )
    notifications = result.scalars().all()

    if not notifications:
        return

    sent_count = 0
    for notif in notifications:
        profile = await db.get(ClientProfile, notif.profile_id)
        if not profile:
            notif.status = "failed"
            notif.error_message = "Profil introuvable"
            continue

        # Vérifier les heures de notification (sauf instant)
        if notif.priority != "instant" and not _is_within_notification_hours(profile):
            continue

        success = False

        if notif.channel == "telegram":
            if not profile.telegram_chat_id:
                notif.status = "failed"
                notif.error_message = "Pas de chat_id Telegram"
                continue

            # Charger l'alerte pour le formatage
            impact_level = "medium"
            alert_id = notif.alert_id
            if alert_id:
                alert = await db.get(ImpactAlert, alert_id)
                if alert:
                    impact_level = alert.impact_level

            text = telegram.format_alert(
                subject=notif.subject or "Notification LegiX",
                body=notif.body,
                impact_level=impact_level,
                alert_id=alert_id,
            )
            success = await telegram.send_message(profile.telegram_chat_id, text)

        elif notif.channel == "email":
            if not profile.email:
                notif.status = "failed"
                notif.error_message = "Pas d'email"
                continue

            impact_level = "medium"
            alert_id = notif.alert_id
            if alert_id:
                alert = await db.get(ImpactAlert, alert_id)
                if alert:
                    impact_level = alert.impact_level

            html = email_notifier.format_alert_html(
                subject=notif.subject or "Notification LegiX",
                body=notif.body,
                impact_level=impact_level,
                alert_id=alert_id,
            )
            success = await email_notifier.send_email(
                to=profile.email,
                subject=notif.subject or "Notification LegiX",
                body_html=html,
                body_text=notif.body,
            )

        if success:
            notif.status = "sent"
            notif.sent_at = datetime.utcnow()
            sent_count += 1
        else:
            notif.status = "failed"
            notif.error_message = "Échec d'envoi"

    await db.commit()

    if sent_count:
        logger.info("Notifications envoyées: %d/%d", sent_count, len(notifications))

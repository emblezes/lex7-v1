"""Scheduler — APScheduler intégré au lifespan FastAPI.

Planifie et exécute les tâches périodiques du pipeline proactif LegiX.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


class LegiXScheduler:
    """Gestionnaire de tâches planifiées LegiX."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()

    def start(self):
        """Enregistre tous les jobs et démarre le scheduler."""

        # Pipeline complet : collect → enrich → score → detect → trigger
        self.scheduler.add_job(
            _run_pipeline,
            IntervalTrigger(minutes=5),
            id="collect_and_process",
            name="Pipeline proactif (5 min)",
            max_instances=1,
            replace_existing=True,
        )

        # Détection de signaux faibles (peut tourner sans collecte)
        self.scheduler.add_job(
            _run_detect_signals,
            IntervalTrigger(minutes=30),
            id="detect_signals",
            name="Détection signaux faibles (30 min)",
            max_instances=1,
            replace_existing=True,
        )

        # Briefings quotidiens à 07h00
        self.scheduler.add_job(
            _run_briefings,
            CronTrigger(hour=7, minute=0),
            id="generate_briefings",
            name="Briefings quotidiens (07h00)",
            max_instances=1,
            replace_existing=True,
        )

        # Vérification agenda parlementaire (J-7, J-3, J-1) toutes les 6h
        self.scheduler.add_job(
            _run_check_agenda,
            IntervalTrigger(hours=6),
            id="check_agenda",
            name="Anticipation agenda (6h)",
            max_instances=1,
            replace_existing=True,
        )

        # Dispatch notifications en attente toutes les 5 min
        self.scheduler.add_job(
            _run_dispatch_notifications,
            IntervalTrigger(minutes=5),
            id="dispatch_notifications",
            name="Dispatch notifications (5 min)",
            max_instances=1,
            replace_existing=True,
        )

        # Vérification suivi textes quotidien à 09h00
        self.scheduler.add_job(
            _run_check_followups,
            CronTrigger(hour=9, minute=0),
            id="check_followups",
            name="Suivi textes (09h00)",
            max_instances=1,
            replace_existing=True,
        )

        # Relance actions en attente quotidien à 10h00
        self.scheduler.add_job(
            _run_check_action_reminders,
            CronTrigger(hour=10, minute=0),
            id="check_action_reminders",
            name="Relance actions (10h00)",
            max_instances=1,
            replace_existing=True,
        )

        self.scheduler.start()
        logger.info("Scheduler LegiX démarré — %d jobs enregistrés", len(self.scheduler.get_jobs()))

    def stop(self):
        """Arrête le scheduler."""
        self.scheduler.shutdown(wait=False)
        logger.info("Scheduler LegiX arrêté")


# --- Fonctions wrapper pour chaque job ---


async def _run_pipeline():
    """Wrapper pour le pipeline complet."""
    try:
        from legix.pipeline import collect_and_process
        await collect_and_process()
    except Exception as e:
        logger.exception("Erreur job pipeline: %s", e)


async def _run_detect_signals():
    """Wrapper pour la détection de signaux."""
    try:
        from legix.core.database import async_session
        from legix.enrichment.signals import detect_all
        async with async_session() as db:
            count = await detect_all(db)
            if count:
                logger.info("Signaux détectés: %d", count)
    except Exception as e:
        logger.exception("Erreur job signaux: %s", e)


async def _run_briefings():
    """Wrapper pour la génération de briefings."""
    try:
        from legix.services.briefing_generation import generate_all_briefings
        await generate_all_briefings()
    except Exception as e:
        logger.exception("Erreur job briefings: %s", e)


async def _run_check_agenda():
    """Wrapper pour l'anticipation d'agenda."""
    try:
        from legix.services.agenda import check_upcoming_reunions
        await check_upcoming_reunions()
    except Exception as e:
        logger.exception("Erreur job agenda: %s", e)


async def _run_dispatch_notifications():
    """Wrapper pour le dispatch de notifications."""
    try:
        from legix.notifications.dispatcher import dispatch_pending
        await dispatch_pending()
    except Exception as e:
        logger.exception("Erreur job notifications: %s", e)


async def _run_check_followups():
    """Wrapper pour le suivi de textes."""
    try:
        from legix.services.followup import check_followups
        await check_followups()
    except Exception as e:
        logger.exception("Erreur job followups: %s", e)


async def _run_check_action_reminders():
    """Wrapper pour les relances d'actions."""
    try:
        from legix.services.followup import check_pending_action_reminders
        await check_pending_action_reminders()
    except Exception as e:
        logger.exception("Erreur job action reminders: %s", e)

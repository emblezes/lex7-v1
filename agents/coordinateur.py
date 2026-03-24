"""Agent Coordinateur — orchestration déterministe multi-étapes.

PAS un agent LLM. C'est du code Python qui chaîne les autres agents
et les fonctions d'intelligence pour produire un dossier complet
quand un texte critique est détecté.
"""

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.agents.chat_tools import (
    analyze_depute,
    analyze_groupe,
    get_client_profile,
)
from legix.core.models import (
    ActionTask,
    Amendement,
    ClientProfile,
    ImpactAlert,
    NotificationQueue,
    Reunion,
    TexteFollowUp,
)

logger = logging.getLogger(__name__)


class CoordinateurAgent:
    """Orchestre les chaînes d'actions pour les alertes critiques/hautes."""

    async def orchestrate(
        self,
        db: AsyncSession,
        alert: ImpactAlert,
        profile: ClientProfile,
    ) -> dict:
        """Point d'entrée : orchestre selon le niveau d'impact."""
        if alert.impact_level == "critical":
            return await self._orchestrate_critical(db, alert, profile)
        elif alert.impact_level == "high":
            return await self._orchestrate_high(db, alert, profile)
        return {}

    async def _orchestrate_critical(
        self,
        db: AsyncSession,
        alert: ImpactAlert,
        profile: ClientProfile,
    ) -> dict:
        """Chaîne complète pour alerte critique :
        1. Intelligence auteur
        2. Intelligence groupe
        3. Vérification agenda
        4. Création ActionTasks (note COMEX, email, suivi)
        5. Création TexteFollowUp
        6. Notification Telegram instantanée
        """
        results: dict = {"level": "critical"}

        # 1. Intelligence sur l'auteur de l'amendement
        auteur_info = None
        if alert.amendement_uid:
            amdt = await db.get(Amendement, alert.amendement_uid)
            if amdt and amdt.auteur_ref:
                try:
                    auteur_info = await analyze_depute(db, amdt.auteur_ref)
                    results["auteur"] = auteur_info.get("nom", amdt.auteur_ref)
                except Exception as e:
                    logger.warning("Intelligence auteur échouée: %s", e)

            # 2. Intelligence sur le groupe politique
            if amdt and amdt.groupe_ref:
                try:
                    groupe_info = await analyze_groupe(db, amdt.groupe_ref)
                    results["groupe"] = groupe_info
                except Exception as e:
                    logger.warning("Intelligence groupe échouée: %s", e)

        # 3. Vérifier l'agenda (réunions à venir sur ce texte)
        texte_uid = alert.texte_uid
        if texte_uid:
            commission_date = await self._find_next_reunion(db, texte_uid)
            results["commission_date"] = commission_date.isoformat() if commission_date else None

        # 4. Créer les ActionTasks
        auteur_name = results.get("auteur", "")

        # Note COMEX urgente
        db.add(ActionTask(
            profile_id=profile.id,
            alert_id=alert.id,
            action_type="draft_note",
            label="Rédiger une note d'impact COMEX sous 48h",
            agent_prompt=(
                f"Rédige une note d'impact urgente pour le COMEX de {profile.name}. "
                f"Texte concerné : {texte_uid or 'N/A'}. "
                f"Résumé de l'alerte : {(alert.impact_summary or '')[:300]}. "
                f"Analyse les risques pour chaque division, chiffre l'exposition financière, "
                f"et propose des recommandations concrètes."
            ),
            due_date=datetime.utcnow() + timedelta(hours=48),
        ))

        # Email parlementaire si auteur identifié
        if auteur_name:
            db.add(ActionTask(
                profile_id=profile.id,
                alert_id=alert.id,
                action_type="draft_email",
                label=f"Contacter {auteur_name} (auteur)",
                agent_prompt=(
                    f"Rédige un email professionnel à {auteur_name} pour solliciter "
                    f"un échange sur ce texte au nom de {profile.name}. "
                    f"Contexte : {(alert.impact_summary or '')[:200]}. "
                    f"Ton diplomatique et constructif."
                ),
                due_date=datetime.utcnow() + timedelta(days=3),
            ))

        # Plan de mitigation
        db.add(ActionTask(
            profile_id=profile.id,
            alert_id=alert.id,
            action_type="draft_note",
            label="Préparer un scénario de mitigation avec chiffrage",
            agent_prompt=(
                f"Rédige un plan de mitigation structuré pour {profile.name} "
                f"face à cette menace réglementaire. "
                f"Contexte : {(alert.impact_summary or '')[:200]}. "
                f"Inclus les options juridiques, le calendrier et l'estimation des coûts."
            ),
            due_date=datetime.utcnow() + timedelta(days=5),
        ))

        # 5. Créer le TexteFollowUp
        if texte_uid:
            existing = await db.execute(
                select(TexteFollowUp).where(
                    TexteFollowUp.profile_id == profile.id,
                    TexteFollowUp.texte_uid == texte_uid,
                )
            )
            if not existing.scalars().first():
                commission_date_val = results.get("commission_date")
                db.add(TexteFollowUp(
                    profile_id=profile.id,
                    texte_uid=texte_uid,
                    status="watching",
                    priority="critical",
                    last_analysis=json.dumps({
                        "alert_id": alert.id,
                        "impact_level": alert.impact_level,
                        "summary": (alert.impact_summary or "")[:300],
                        "date": datetime.utcnow().isoformat(),
                    }),
                    change_log=json.dumps([{
                        "date": datetime.utcnow().isoformat(),
                        "event": "Détection initiale — alerte critique",
                        "alert_id": alert.id,
                    }], ensure_ascii=False),
                    next_check_at=datetime.utcnow() + timedelta(days=2),
                    commission_date=(
                        datetime.fromisoformat(commission_date_val)
                        if commission_date_val else None
                    ),
                ))

        # 6. Notification Telegram instantanée
        if profile.telegram_chat_id and profile.telegram_bot_enabled:
            summary = (alert.impact_summary or "Alerte critique détectée")[:300]
            db.add(NotificationQueue(
                profile_id=profile.id,
                channel="telegram",
                priority="instant",
                subject=f"ALERTE CRITIQUE — {profile.name}",
                body=(
                    f"{'MENACE' if alert.is_threat else 'OPPORTUNITÉ'} CRITIQUE\n\n"
                    f"{summary}\n\n"
                    f"Exposition estimée : {alert.exposure_eur:,.0f} EUR"
                    if alert.exposure_eur else
                    f"{'MENACE' if alert.is_threat else 'OPPORTUNITÉ'} CRITIQUE\n\n{summary}"
                ),
                alert_id=alert.id,
            ))

        # Notification email aussi
        if profile.email:
            db.add(NotificationQueue(
                profile_id=profile.id,
                channel="email",
                priority="instant",
                subject=f"[LegiX] Alerte critique — {profile.name}",
                body=(alert.impact_summary or "Alerte critique détectée")[:500],
                alert_id=alert.id,
            ))

        await db.commit()

        # Generer des actions recommandees liees au dossier
        texte_uid = alert.texte_uid
        if texte_uid:
            try:
                from legix.services.dossier_actions import generate_dossier_actions
                await generate_dossier_actions(db, texte_uid, profile)
                logger.info("Actions dossier generees pour %s / %s", profile.name, texte_uid)
            except Exception as e:
                logger.warning("Generation actions dossier echouee: %s", e)

        logger.info(
            "Orchestration critique terminée pour %s — alert #%d",
            profile.name, alert.id,
        )
        return results

    async def _orchestrate_high(
        self,
        db: AsyncSession,
        alert: ImpactAlert,
        profile: ClientProfile,
    ) -> dict:
        """Chaîne réduite pour alerte haute :
        1. Création ActionTask (analyse détaillée)
        2. Création TexteFollowUp
        3. Notification email
        """
        results: dict = {"level": "high"}

        # ActionTask : analyse d'impact détaillée
        db.add(ActionTask(
            profile_id=profile.id,
            alert_id=alert.id,
            action_type="draft_note",
            label=f"Analyse d'impact détaillée pour {profile.name}",
            agent_prompt=(
                f"Rédige une analyse d'impact détaillée pour {profile.name} "
                f"évaluant les coûts de mise en conformité par division "
                f"et les risques juridiques. "
                f"Contexte : {(alert.impact_summary or '')[:300]}"
            ),
            due_date=datetime.utcnow() + timedelta(days=5),
        ))

        # TexteFollowUp
        texte_uid = alert.texte_uid
        if texte_uid:
            existing = await db.execute(
                select(TexteFollowUp).where(
                    TexteFollowUp.profile_id == profile.id,
                    TexteFollowUp.texte_uid == texte_uid,
                )
            )
            if not existing.scalars().first():
                db.add(TexteFollowUp(
                    profile_id=profile.id,
                    texte_uid=texte_uid,
                    status="watching",
                    priority="high",
                    last_analysis=json.dumps({
                        "alert_id": alert.id,
                        "impact_level": alert.impact_level,
                        "date": datetime.utcnow().isoformat(),
                    }),
                    change_log=json.dumps([{
                        "date": datetime.utcnow().isoformat(),
                        "event": "Détection — alerte haute",
                        "alert_id": alert.id,
                    }], ensure_ascii=False),
                    next_check_at=datetime.utcnow() + timedelta(days=5),
                ))

        # Notification email
        if profile.email:
            db.add(NotificationQueue(
                profile_id=profile.id,
                channel="email",
                priority="normal",
                subject=f"[LegiX] Alerte importante — {profile.name}",
                body=(alert.impact_summary or "Alerte importante détectée")[:500],
                alert_id=alert.id,
            ))

        await db.commit()
        return results

    # --- Workflow 2 : Signal d'anticipation ---

    async def orchestrate_anticipation(
        self,
        db: AsyncSession,
        report_id: int,
        profile: ClientProfile,
    ) -> dict:
        """Workflow anticipation : rapport think tank → analyse → position → livrables.

        1. Analyse du rapport (AnticipateurAgent)
        2. Évaluation d'impact (AnalysteAgent)
        3. Planification (PlanificateurAgent)
        4. Production note de position (RédacteurAgent via ActionTask)
        """
        from legix.core.models import AnticipationReport

        report = await db.get(AnticipationReport, report_id)
        if not report:
            return {"error": "Rapport non trouvé"}

        results: dict = {"workflow": "anticipation", "report_id": report_id}

        # Créer un ActionTask pour analyse approfondie
        db.add(ActionTask(
            profile_id=profile.id,
            action_type="draft_note",
            label=f"Analyse d'anticipation : {report.title[:80]}",
            agent_prompt=(
                f"Analyse ce rapport de {report.source_name} : '{report.title}'. "
                f"Résumé : {report.resume_ia or 'Non disponible'}. "
                f"Évalue la probabilité que ses recommandations deviennent loi, "
                f"l'impact pour {profile.name}, et les actions à mener MAINTENANT "
                f"pour anticiper."
            ),
            priority=2,
            due_date=datetime.utcnow() + timedelta(days=7),
        ))

        # Si probabilité législative élevée, créer aussi une note de position
        if report.legislative_probability and report.legislative_probability > 0.5:
            db.add(ActionTask(
                profile_id=profile.id,
                action_type="draft_note",
                label=f"Note de position préventive : {report.title[:60]}",
                agent_prompt=(
                    f"Rédige une note de position pour {profile.name} sur le sujet "
                    f"'{report.title}' (source : {report.source_name}). "
                    f"Le rapport a une probabilité législative de {report.legislative_probability:.0%}. "
                    f"La note doit positionner {profile.name} de manière proactive "
                    f"AVANT que le débat législatif ne commence."
                ),
                priority=2,
                due_date=datetime.utcnow() + timedelta(days=10),
            ))
            results["position_paper_created"] = True

        # Notification
        if profile.email:
            db.add(NotificationQueue(
                profile_id=profile.id,
                channel="email",
                priority="normal",
                subject=f"[LegiX] Signal anticipation — {report.source_name}",
                body=(
                    f"Nouveau signal d'anticipation détecté.\n\n"
                    f"Source : {report.source_name}\n"
                    f"Titre : {report.title}\n"
                    f"Probabilité législative : {report.legislative_probability or 'N/A'}\n\n"
                    f"Une analyse approfondie est en cours."
                ),
            ))

        await db.commit()
        logger.info("Workflow anticipation lancé pour %s — rapport #%d", profile.name, report_id)
        return results

    # --- Workflow 3 : Crise presse ---

    async def orchestrate_press_crisis(
        self,
        db: AsyncSession,
        article_id: int,
        profile: ClientProfile,
    ) -> dict:
        """Workflow riposte : article négatif → analyse → réponse.

        1. Analyse de l'article (RiposteAgent)
        2. Identification journaliste (CartographeAgent)
        3. Préparation réponse (RédacteurAgent via ActionTask)
        """
        from legix.core.models import PressArticle

        article = await db.get(PressArticle, article_id)
        if not article:
            return {"error": "Article non trouvé"}

        results: dict = {"workflow": "press_crisis", "article_id": article_id}

        # ActionTask : préparer la réponse
        urgency_hours = {
            "critical": 4,
            "high": 24,
            "medium": 48,
            "low": 72,
        }
        hours = urgency_hours.get(article.response_urgency or "medium", 48)

        db.add(ActionTask(
            profile_id=profile.id,
            action_type="draft_note",
            label=f"Riposte presse : {article.title[:60]}",
            agent_prompt=(
                f"Prépare une réponse pour {profile.name} à cet article : "
                f"'{article.title}' ({article.source_name}). "
                f"Sentiment : {article.sentiment or 'non analysé'}. "
                f"Rédige des éléments de langage, un communiqué réactif si nécessaire, "
                f"et identifie les points à corriger/nuancer."
            ),
            priority=1 if article.response_urgency == "critical" else 2,
            due_date=datetime.utcnow() + timedelta(hours=hours),
        ))

        # Marquer l'article comme en cours de traitement
        article.response_status = "draft"
        await db.commit()

        # Notification urgente si critique
        if article.response_urgency == "critical" and profile.telegram_chat_id:
            db.add(NotificationQueue(
                profile_id=profile.id,
                channel="telegram",
                priority="instant",
                subject=f"PRESSE — Réponse urgente requise",
                body=(
                    f"Article critique détecté dans {article.source_name}.\n"
                    f"Titre : {article.title}\n"
                    f"Une réponse est en préparation."
                ),
            ))
            await db.commit()

        logger.info("Workflow riposte lancé pour %s — article #%d", profile.name, article_id)
        return results

    # --- Workflow 4 : Onboarding client ---

    async def orchestrate_onboarding(
        self,
        db: AsyncSession,
        profile: ClientProfile,
    ) -> dict:
        """Workflow onboarding : scan backlog → analyse → configuration veille.

        1. Enrichissement client (OnboarderAgent)
        2. Scan des dossiers existants (VeilleurAgent)
        3. Analyse du backlog (AnalysteAgent)
        4. Configuration veille (Coordinateur)
        """
        results: dict = {"workflow": "onboarding", "profile_id": profile.id}

        # Créer ActionTask pour scan initial
        db.add(ActionTask(
            profile_id=profile.id,
            action_type="monitor",
            label=f"Scan initial des dossiers pour {profile.name}",
            agent_prompt=(
                f"Effectue un scan complet des textes législatifs en cours "
                f"pertinents pour {profile.name} (secteurs : {profile.sectors}). "
                f"Identifie les dossiers prioritaires et crée des TexteFollowUp "
                f"pour chacun."
            ),
            priority=1,
            due_date=datetime.utcnow() + timedelta(days=1),
        ))

        # Créer ActionTask pour rapport d'intégration
        db.add(ActionTask(
            profile_id=profile.id,
            action_type="draft_note",
            label=f"Rapport d'intégration pour {profile.name}",
            agent_prompt=(
                f"Rédige un rapport d'intégration complet pour {profile.name}. "
                f"Inclus : paysage réglementaire actuel, dossiers en cours, "
                f"signaux d'anticipation, parties prenantes clés, "
                f"et recommandations pour les 90 prochains jours."
            ),
            priority=2,
            due_date=datetime.utcnow() + timedelta(days=3),
        ))

        await db.commit()
        logger.info("Workflow onboarding lancé pour %s", profile.name)
        return results

    # --- Utilitaire ---

    async def _find_next_reunion(
        self, db: AsyncSession, texte_uid: str
    ) -> datetime | None:
        """Cherche la prochaine réunion de commission traitant ce texte."""
        now = datetime.utcnow()
        pattern = f"%{texte_uid}%"
        result = await db.execute(
            select(Reunion)
            .where(
                Reunion.date_debut > now,
                Reunion.odj.ilike(pattern),
            )
            .order_by(Reunion.date_debut)
            .limit(1)
        )
        reunion = result.scalars().first()
        return reunion.date_debut if reunion else None

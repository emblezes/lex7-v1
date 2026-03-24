"""Service de génération de briefings quotidiens personnalisés.

Collecte les alertes récentes, signaux, réunions à venir et textes suivis
pour chaque profil client, puis génère un briefing structuré via Claude.
"""

import json
import logging
from datetime import datetime, timedelta

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.config import settings
from legix.core.database import async_session
from legix.core.models import (
    ActionTask,
    Briefing,
    ClientProfile,
    ImpactAlert,
    NotificationQueue,
    Reunion,
    Signal,
    TexteFollowUp,
)

logger = logging.getLogger(__name__)


async def generate_all_briefings():
    """Génère les briefings pour tous les profils actifs qui les reçoivent."""
    async with async_session() as db:
        result = await db.execute(
            select(ClientProfile).where(
                ClientProfile.is_active.is_(True),
                ClientProfile.receive_briefing.is_(True),
            )
        )
        profiles = result.scalars().all()

        for profile in profiles:
            try:
                briefing = await generate_daily_briefing(db, profile)
                if briefing:
                    logger.info("Briefing généré pour %s (#%d)", profile.name, briefing.id)
            except Exception as e:
                logger.error("Erreur briefing pour %s: %s", profile.name, e)


async def generate_daily_briefing(
    db: AsyncSession, profile: ClientProfile
) -> Briefing | None:
    """Génère le briefing quotidien pour un profil client."""
    now = datetime.utcnow()
    yesterday = now - timedelta(hours=24)

    # 1. Collecter les données du jour
    # Alertes récentes
    alerts_result = await db.execute(
        select(ImpactAlert)
        .where(
            ImpactAlert.profile_id == profile.id,
            ImpactAlert.created_at >= yesterday,
        )
        .order_by(ImpactAlert.impact_level.desc())
    )
    alerts = alerts_result.scalars().all()

    # Signaux faibles
    sectors = json.loads(profile.sectors) if profile.sectors else []
    signals = []
    for sector in sectors:
        sig_result = await db.execute(
            select(Signal)
            .where(
                Signal.created_at >= yesterday,
                Signal.is_dismissed.is_(False),
                Signal.themes.ilike(f"%{sector}%"),
            )
            .limit(5)
        )
        signals.extend(sig_result.scalars().all())

    # Réunions à venir (J+1 à J+7)
    reunions_result = await db.execute(
        select(Reunion)
        .where(
            Reunion.date_debut >= now,
            Reunion.date_debut <= now + timedelta(days=7),
        )
        .order_by(Reunion.date_debut)
        .limit(10)
    )
    reunions = reunions_result.scalars().all()

    # Textes suivis avec changements
    followups_result = await db.execute(
        select(TexteFollowUp)
        .where(
            TexteFollowUp.profile_id == profile.id,
            TexteFollowUp.status == "watching",
        )
    )
    followups = followups_result.scalars().all()

    # Actions en attente
    actions_result = await db.execute(
        select(ActionTask)
        .where(
            ActionTask.profile_id == profile.id,
            ActionTask.status == "pending",
        )
    )
    pending_actions = actions_result.scalars().all()

    # Si rien à signaler, pas de briefing
    if not alerts and not signals and not followups:
        return None

    # 2. Construire le contexte pour Claude
    context_parts = []

    if alerts:
        context_parts.append("ALERTES RÉCENTES (24h) :")
        for a in alerts[:10]:
            threat = "MENACE" if a.is_threat else "OPPORTUNITÉ"
            context_parts.append(
                f"- [{a.impact_level.upper()}] {threat} : {(a.impact_summary or '')[:200]}"
            )

    if signals:
        context_parts.append("\nSIGNAUX FAIBLES :")
        seen = set()
        for s in signals:
            if s.id not in seen:
                seen.add(s.id)
                context_parts.append(f"- [{s.severity}] {s.title}")

    if reunions:
        context_parts.append("\nAGENDA PARLEMENTAIRE (7 jours) :")
        for r in reunions[:5]:
            date_str = r.date_debut.strftime("%d/%m %Hh%M") if r.date_debut else "?"
            context_parts.append(f"- {date_str} : {r.resume_ia or r.uid}")

    if followups:
        context_parts.append(f"\nTEXTES SUIVIS : {len(followups)} textes en surveillance active")

    if pending_actions:
        context_parts.append(f"\nACTIONS EN ATTENTE : {len(pending_actions)} actions à traiter")
        for a in pending_actions[:3]:
            context_parts.append(f"- {a.label}")

    context = "\n".join(context_parts)

    # 3. Appel Claude pour synthèse
    if not settings.anthropic_api_key:
        return None

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    company = profile.name
    sectors_str = ", ".join(sectors)

    prompt = f"""Tu es l'intelligence réglementaire de {company} (secteurs : {sectors_str}).

Génère un briefing matinal concis et actionnable à partir des données ci-dessous.

{context}

FORMAT DU BRIEFING :
1. SYNTHÈSE (2-3 phrases : ce qu'il faut retenir aujourd'hui)
2. ALERTES PRIORITAIRES (les 3 plus importantes, avec action recommandée)
3. SIGNAUX À SURVEILLER (tendances émergentes)
4. AGENDA (ce qui arrive cette semaine)
5. ACTIONS EN ATTENTE (rappel des actions non traitées)

RÈGLES :
- Sois spécifique à {company}
- Priorise l'actionnable sur l'informatif
- Français professionnel, concis
- Si rien de critique, dis-le clairement ("journée calme")
"""

    try:
        response = client.messages.create(
            model=settings.enrichment_model,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        briefing_text = response.content[0].text.strip()
    except Exception as e:
        logger.error("Erreur Claude pour briefing: %s", e)
        return None

    # 4. Sauvegarder le briefing
    briefing = Briefing(
        profile_id=profile.id,
        title=f"Briefing du {now.strftime('%d/%m/%Y')} — {company}",
        content=json.dumps({
            "text": briefing_text,
            "stats": {
                "alerts_count": len(alerts),
                "signals_count": len(set(s.id for s in signals)),
                "followups_count": len(followups),
                "pending_actions": len(pending_actions),
            },
        }, ensure_ascii=False),
        period_start=yesterday,
        period_end=now,
        delivered_dashboard=True,
    )
    db.add(briefing)
    await db.commit()
    await db.refresh(briefing)

    # 5. Queue les notifications
    # Email digest
    if profile.email and profile.email_digest_enabled:
        db.add(NotificationQueue(
            profile_id=profile.id,
            channel="email",
            priority="digest",
            subject=f"[LegiX] Briefing du {now.strftime('%d/%m/%Y')} — {company}",
            body=briefing_text[:500],
            briefing_id=briefing.id,
        ))

    # Telegram résumé (si activé)
    if profile.telegram_chat_id and profile.telegram_bot_enabled:
        # Extraire juste la synthèse (premières lignes)
        summary = briefing_text[:300]
        db.add(NotificationQueue(
            profile_id=profile.id,
            channel="telegram",
            priority="normal",
            subject=f"Briefing — {company}",
            body=summary,
            briefing_id=briefing.id,
        ))

    await db.commit()
    return briefing

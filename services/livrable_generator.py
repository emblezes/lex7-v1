"""Service generation de livrables via RedacteurAgent — 14 types.

Utilise le systeme de templates (document_templates.py) pour produire
des livrables adaptes a l'interlocuteur et au contexte du client.
"""

import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.models import (
    ActionTask,
    AnticipationReport,
    ClientProfile,
    ImpactAlert,
    Livrable,
    PressArticle,
    StakeholderProfile,
    TexteBrief,
)
from legix.services.document_templates import (
    build_prompt,
    get_all_types,
    get_template,
)

logger = logging.getLogger(__name__)


async def generate_livrable(
    db: AsyncSession,
    action_id: int,
    livrable_type: str,
    target_audience: str = "interne",
) -> Livrable:
    """Genere un livrable a partir d'une action.

    Supporte les 14 types de livrables definis dans document_templates.py.
    Charge le contexte complet et adapte le prompt a l'interlocuteur.

    Args:
        db: Session DB
        action_id: ID de l'ActionTask source
        livrable_type: Type de livrable (brief_executif, note_position, email_parlementaire, etc.)
        target_audience: Interlocuteur (politique, journaliste, regulateur, interne, direction)
    """
    task = await db.get(ActionTask, action_id)
    if not task:
        raise ValueError(f"ActionTask {action_id} introuvable")

    profile = await db.get(ClientProfile, task.profile_id)
    if not profile:
        raise ValueError(f"ClientProfile {task.profile_id} introuvable")

    # --- Collecter tout le contexte disponible ---
    context_data: dict = {}

    # Contexte de l'action
    context_data["action"] = f"{task.label}\n{task.rationale or ''}"
    if task.agent_prompt:
        context_data["instructions_specifiques"] = task.agent_prompt

    # TexteBrief (dossier legislatif)
    if task.texte_uid:
        result = await db.execute(
            select(TexteBrief).where(
                TexteBrief.profile_id == task.profile_id,
                TexteBrief.texte_uid == task.texte_uid,
            )
        )
        brief = result.scalar_one_or_none()
        if brief:
            context_data["texte_brief"] = {
                "texte_uid": task.texte_uid,
                "impact_level": brief.impact_level,
                "executive_summary": brief.executive_summary,
                "force_map": json.loads(brief.force_map) if brief.force_map else None,
                "critical_amendments": json.loads(brief.critical_amendments) if brief.critical_amendments else None,
                "key_contacts": json.loads(brief.key_contacts) if brief.key_contacts else None,
                "action_plan": json.loads(brief.action_plan) if brief.action_plan else None,
                "exposure_eur": brief.exposure_eur,
            }

    # ImpactAlert
    if task.alert_id:
        alert = await db.get(ImpactAlert, task.alert_id)
        if alert:
            context_data["impact_alert"] = {
                "impact_level": alert.impact_level,
                "impact_summary": alert.impact_summary,
                "exposure_eur": alert.exposure_eur,
                "is_threat": alert.is_threat,
                "matched_themes": json.loads(alert.matched_themes) if alert.matched_themes else [],
            }

    # Profil client (résumé)
    context_data["client_profile"] = {
        "name": profile.name,
        "sectors": json.loads(profile.sectors) if profile.sectors else [],
        "business_lines": json.loads(profile.business_lines) if profile.business_lines else [],
        "products": json.loads(profile.products) if profile.products else [],
        "regulatory_focus": json.loads(profile.regulatory_focus) if profile.regulatory_focus else [],
        "description": profile.description,
        "pa_strategy": profile.pa_strategy,
        "pa_priorities": json.loads(profile.pa_priorities) if profile.pa_priorities else [],
    }

    # Acteurs cibles (stakeholders)
    if task.target_acteur_uids:
        try:
            uids = json.loads(task.target_acteur_uids)
            if uids:
                context_data["target_actors"] = uids
                # Charger les profils stakeholders si disponibles
                for uid in uids[:3]:  # Max 3 pour pas surcharger le prompt
                    stakeholder = await db.execute(
                        select(StakeholderProfile).where(
                            StakeholderProfile.acteur_uid == uid
                        )
                    )
                    s = stakeholder.scalar_one_or_none()
                    if s:
                        context_data[f"stakeholder_{uid}"] = {
                            "nom": f"{s.prenom or ''} {s.nom}".strip(),
                            "organisation": s.organisation,
                            "key_themes": json.loads(s.key_themes) if s.key_themes else [],
                            "bio_summary": s.bio_summary,
                            "relationship_status": s.relationship_status,
                        }
        except (json.JSONDecodeError, TypeError):
            pass

    # --- Construire le prompt via le systeme de templates ---
    prompt = build_prompt(
        livrable_type=livrable_type,
        company_name=profile.name,
        target_audience=target_audience,
        context_data=context_data,
    )

    # --- Appeler le RedacteurAgent ---
    from legix.agents.redacteur import RedacteurAgent
    from legix.agents.chat_tools import get_client_profile

    profile_dict = await get_client_profile(db, profile_id=profile.id)

    agent = RedacteurAgent()
    content = await agent.run(prompt, db=db, profile=profile_dict)

    # --- Creer le Livrable ---
    template = get_template(livrable_type)
    title = template.label if template else livrable_type
    if task.label:
        title = f"{title} — {task.label[:60]}"

    livrable = Livrable(
        action_id=action_id,
        profile_id=profile.id,
        type=livrable_type,
        title=title,
        content=content,
        format="markdown",
        status="draft",
        metadata_=json.dumps({
            "target_audience": target_audience,
            "template_version": "v2",
        }),
    )
    db.add(livrable)
    await db.commit()
    await db.refresh(livrable)

    logger.info(
        "Livrable genere: #%d type=%s audience=%s action=#%d (%d chars)",
        livrable.id, livrable_type, target_audience, action_id, len(content),
    )
    return livrable


async def list_available_types() -> list[dict]:
    """Retourne les types de livrables disponibles."""
    return get_all_types()

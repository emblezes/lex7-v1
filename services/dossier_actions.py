"""Service generation d'actions recommandees IA pour un dossier."""

import json
import logging
import re
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.models import (
    ActionTask,
    ClientProfile,
    TexteBrief,
    Texte,
)

logger = logging.getLogger(__name__)


async def generate_dossier_actions(
    db: AsyncSession,
    texte_uid: str,
    profile: ClientProfile,
) -> list[ActionTask]:
    """Genere des actions recommandees IA pour un dossier texte.

    Charge le TexteBrief, appelle le StrategeAgent pour produire
    des actions structurees, et les cree en DB.
    """
    # Charger le brief existant
    result = await db.execute(
        select(TexteBrief).where(
            TexteBrief.profile_id == profile.id,
            TexteBrief.texte_uid == texte_uid,
        )
    )
    brief = result.scalar_one_or_none()

    texte = await db.get(Texte, texte_uid)
    texte_titre = texte.titre_court or texte.titre or texte_uid if texte else texte_uid

    # Construire le prompt pour le StrategeAgent
    context_parts = [
        f"DOSSIER : {texte_titre} ({texte_uid})",
    ]

    if brief:
        context_parts.append(f"NIVEAU D'IMPACT : {brief.impact_level}")
        context_parts.append(f"TYPE : {'MENACE' if brief.is_threat else 'OPPORTUNITE'}")
        if brief.exposure_eur:
            context_parts.append(f"EXPOSITION : {brief.exposure_eur:,.0f} EUR")
        if brief.executive_summary:
            context_parts.append(f"RESUME : {brief.executive_summary[:500]}")

        # Contacts cles
        key_contacts = json.loads(brief.key_contacts or "[]")
        if key_contacts:
            names = [c.get("nom", "") for c in key_contacts[:5]]
            context_parts.append(f"CONTACTS CLES : {', '.join(names)}")

        # Plan d'action existant
        action_plan = json.loads(brief.action_plan or "[]")
        if action_plan:
            context_parts.append("PLAN D'ACTION DU BRIEF :")
            for ap in action_plan[:5]:
                context_parts.append(f"  - P{ap.get('priority', '?')}: {ap.get('action', '')}")

    prompt = "\n".join(context_parts) + "\n\n"
    prompt += (
        f"Pour {profile.name}, genere entre 3 et 5 actions concretes "
        f"a executer sur ce dossier.\n\n"
        f"REPONDS EN JSON STRICT — un array d'objets avec les champs :\n"
        f"- action_type: draft_note | draft_email | draft_amendment | monitor\n"
        f"- label: description courte de l'action\n"
        f"- rationale: explication du pourquoi (1-2 phrases)\n"
        f"- priority: 1 (urgent) a 5 (faible)\n"
        f"- target_acteur_uids: liste d'UIDs d'acteurs cibles (peut etre vide)\n\n"
        f"Exemple : [{{\"action_type\": \"draft_note\", \"label\": \"...\", "
        f"\"rationale\": \"...\", \"priority\": 1, \"target_acteur_uids\": []}}]\n\n"
        f"REPONDS UNIQUEMENT AVEC LE JSON, sans texte autour."
    )

    # Appeler le StrategeAgent
    from legix.agents.stratege import StrategeAgent
    agent = StrategeAgent()

    profile_dict = {
        "name": profile.name,
        "sectors": json.loads(profile.sectors or "[]"),
        "business_lines": json.loads(profile.business_lines or "[]"),
        "products": json.loads(profile.products or "[]"),
        "regulatory_focus": json.loads(profile.regulatory_focus or "[]"),
        "context_note": profile.context_note,
        "description": profile.description,
    }

    raw = await agent.run(prompt, db=db, profile=profile_dict)

    # Parser le JSON
    actions_data = _parse_actions_json(raw)

    # Creer les ActionTasks
    created = []
    for ad in actions_data[:5]:
        task = ActionTask(
            profile_id=profile.id,
            texte_uid=texte_uid,
            action_type=ad.get("action_type", "draft_note"),
            label=ad.get("label", "Action recommandee"),
            rationale=ad.get("rationale"),
            priority=ad.get("priority", 3),
            target_acteur_uids=json.dumps(
                ad.get("target_acteur_uids", []), ensure_ascii=False
            ),
            agent_prompt=_build_execution_prompt(ad, brief, profile, texte_titre),
            due_date=datetime.utcnow() + timedelta(days=ad.get("priority", 3) * 2),
        )
        db.add(task)
        created.append(task)

    await db.commit()
    for t in created:
        await db.refresh(t)

    logger.info(
        "Actions generees pour %s / %s : %d actions",
        profile.name, texte_uid, len(created),
    )
    return created


def _parse_actions_json(raw: str) -> list[dict]:
    """Parse le JSON d'actions depuis la reponse agent."""
    # Extraire JSON array
    json_match = re.search(r'```json\s*(.*?)\s*```', raw, re.DOTALL)
    candidate = json_match.group(1) if json_match else raw

    # Trouver le premier [ ... ]
    start = candidate.find('[')
    if start >= 0:
        depth = 0
        for i in range(start, len(candidate)):
            if candidate[i] == '[':
                depth += 1
            elif candidate[i] == ']':
                depth -= 1
                if depth == 0:
                    candidate = candidate[start:i + 1]
                    break

    try:
        result = json.loads(candidate)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    logger.warning("Echec parsing actions JSON, fallback")
    return [
        {
            "action_type": "draft_note",
            "label": "Analyser l'impact de ce texte",
            "rationale": "Analyse generee automatiquement",
            "priority": 2,
            "target_acteur_uids": [],
        }
    ]


def _build_execution_prompt(
    action_data: dict,
    brief: TexteBrief | None,
    profile: ClientProfile,
    texte_titre: str,
) -> str:
    """Construit le prompt d'execution pour le RedacteurAgent."""
    parts = [
        f"ACTION : {action_data.get('label', '')}",
        f"TYPE : {action_data.get('action_type', 'draft_note')}",
        f"DOSSIER : {texte_titre}",
        f"CLIENT : {profile.name}",
    ]
    if action_data.get("rationale"):
        parts.append(f"CONTEXTE : {action_data['rationale']}")
    if brief and brief.executive_summary:
        parts.append(f"RESUME DU DOSSIER : {brief.executive_summary[:300]}")
    return "\n".join(parts)

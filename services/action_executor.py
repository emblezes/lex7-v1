"""Service d'exécution d'actions — lance le RedacteurAgent sur une ActionTask."""

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from legix.agents.chat_tools import get_client_profile
from legix.agents.redacteur import RedacteurAgent
from legix.core.models import ActionTask, ImpactAlert

logger = logging.getLogger(__name__)


async def execute_action(db: AsyncSession, task_id: int) -> ActionTask:
    """Exécute une ActionTask via le RedacteurAgent.

    Charge le contexte de l'alerte, construit un prompt enrichi,
    lance l'agent et stocke le résultat.
    """
    task = await db.get(ActionTask, task_id)
    if not task:
        raise ValueError(f"ActionTask {task_id} introuvable")

    if task.status == "completed":
        return task

    task.status = "in_progress"
    await db.commit()

    try:
        # Charger le contexte
        profile_dict = await get_client_profile(db, profile_id=task.profile_id)

        # Construire le prompt enrichi avec le contexte de l'alerte
        prompt_parts = []

        if task.alert_id:
            alert = await db.get(ImpactAlert, task.alert_id)
            if alert:
                prompt_parts.append(f"CONTEXTE DE L'ALERTE :")
                prompt_parts.append(f"- Niveau d'impact : {alert.impact_level}")
                prompt_parts.append(f"- Type : {'MENACE' if alert.is_threat else 'OPPORTUNITÉ'}")
                if alert.exposure_eur:
                    prompt_parts.append(f"- Exposition estimée : {alert.exposure_eur:,.0f} EUR")
                prompt_parts.append(f"- Résumé : {alert.impact_summary or 'N/A'}")
                if alert.texte_uid:
                    prompt_parts.append(f"- Document source : {alert.texte_uid}")
                if alert.amendement_uid:
                    prompt_parts.append(f"- Amendement : {alert.amendement_uid}")
                prompt_parts.append("")

        prompt_parts.append("MISSION :")
        prompt_parts.append(task.agent_prompt or task.label)

        prompt = "\n".join(prompt_parts)

        # Lancer le RedacteurAgent
        agent = RedacteurAgent()
        result = await agent.run(prompt, db=db, profile=profile_dict)

        task.result_content = result
        task.result_format = "markdown"
        task.status = "completed"
        task.completed_at = datetime.utcnow()

        logger.info(
            "Action exécutée: #%d '%s' (%d chars)",
            task.id, task.label[:50], len(result),
        )

    except Exception as e:
        logger.error("Erreur exécution action #%d: %s", task_id, e)
        task.status = "failed"
        task.result_content = f"Erreur : {str(e)}"

    await db.commit()
    return task

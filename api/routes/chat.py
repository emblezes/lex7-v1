"""Route chat — conversation avec les 8 agents IA LegiX.

Supporte :
- Chat direct avec un agent nomme
- Routing automatique (agent="auto") qui choisit le bon agent
- Mode LangGraph (use_langgraph=true) pour traces LangSmith
"""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from legix.api.deps import get_current_profile, get_db
from legix.core.models import ClientProfile
from legix.agents.veilleur import VeilleurAgent
from legix.agents.analyste import AnalysteAgent
from legix.agents.stratege import StrategeAgent
from legix.agents.redacteur import RedacteurAgent

logger = logging.getLogger(__name__)
router = APIRouter()

# Agents natifs (async, pas LangGraph)
AGENTS = {
    "veilleur": VeilleurAgent,
    "analyste": AnalysteAgent,
    "stratege": StrategeAgent,
    "redacteur": RedacteurAgent,
}

# Mapping pour le routing automatique
AGENT_ROUTING = {
    # Mots-cles → agent
    "rapport": "anticipateur",
    "think tank": "anticipateur",
    "anticipation": "anticipateur",
    "pre-legislatif": "anticipateur",
    "inspection": "anticipateur",
    "cour des comptes": "anticipateur",
    "stakeholder": "cartographe",
    "partie prenante": "cartographe",
    "carte des acteurs": "cartographe",
    "qui est pour": "cartographe",
    "qui est contre": "cartographe",
    "profil": "profil_acteur",
    "persona": "profil_acteur",
    "reaction": "profil_acteur",
    "simuler": "profil_acteur",
    "comment reagirait": "profil_acteur",
    "presse": "riposte",
    "journaliste": "riposte",
    "article": "riposte",
    "riposte": "riposte",
    "communique": "riposte",
    "media": "riposte",
    "calendrier": "planificateur",
    "planning": "planificateur",
    "priorite": "planificateur",
    "feuille de route": "planificateur",
    "fenetre": "planificateur",
    "quand agir": "planificateur",
    "redige": "redacteur",
    "email": "redacteur",
    "note": "redacteur",
    "brief": "redacteur",
    "amendement": "analyste",
    "impact": "analyste",
    "analyse": "analyste",
    "strategie": "stratege",
    "plan d'action": "stratege",
    "allies": "stratege",
    "rapport de force": "stratege",
}

# Agents LangGraph (avec traces LangSmith)
LANGGRAPH_AGENTS = [
    "veilleur", "analyste", "stratege",
    "anticipateur", "cartographe", "profil_acteur",
    "riposte", "planificateur",
]


def auto_route_agent(message: str) -> str:
    """Choisit automatiquement le bon agent selon le message."""
    msg_lower = message.lower()
    for keyword, agent_name in AGENT_ROUTING.items():
        if keyword in msg_lower:
            return agent_name
    return "veilleur"  # Par defaut


class ChatRequest(BaseModel):
    message: str
    agent: str = "auto"  # "auto" = routing automatique
    profile_id: int | None = None
    texte_uid: str | None = None
    use_langgraph: bool = False  # Si True, utilise LangGraph (traces LangSmith)


class ChatResponse(BaseModel):
    response: str
    agent: str
    agent_routed: bool = False  # True si le routing auto a choisi l'agent
    profile_id: int | None = None
    texte_uid: str | None = None


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Envoie un message a un agent IA LegiX.

    Le profile_id est forcé depuis le token JWT authentifié.
    L'agent raisonne dans le contexte du client (secteurs, notes, etc.)
    et utilise ses outils d'intelligence legislative.
    Si texte_uid est fourni, le contexte du dossier est injecté.
    """
    import json
    from sqlalchemy import select
    from legix.core.models import TexteBrief, ActionTask, Texte

    # Force profile_id from authenticated user regardless of client input
    request.profile_id = profile.id

    # Routing automatique
    agent_routed = False
    if request.agent == "auto":
        request.agent = auto_route_agent(request.message)
        agent_routed = True
        logger.info("Auto-routing: '%s' -> agent %s", request.message[:50], request.agent)

    # Mode LangGraph (traces LangSmith)
    if request.use_langgraph or request.agent in LANGGRAPH_AGENTS and request.agent not in AGENTS:
        try:
            from legix.agents.langchain_agents import chat as lg_chat
            response_text = lg_chat(request.agent, message)
            return ChatResponse(
                response=response_text,
                agent=request.agent,
                agent_routed=agent_routed,
                profile_id=request.profile_id,
                texte_uid=request.texte_uid,
            )
        except Exception as e:
            logger.error("LangGraph agent %s erreur: %s", request.agent, e)
            return ChatResponse(
                response=f"Erreur agent LangGraph: {str(e)}",
                agent=request.agent,
            )

    agent_class = AGENTS.get(request.agent)
    if not agent_class:
        # Fallback vers LangGraph pour les agents non-natifs
        try:
            from legix.agents.langchain_agents import chat as lg_chat
            response_text = lg_chat(request.agent, message)
            return ChatResponse(
                response=response_text,
                agent=request.agent,
                agent_routed=agent_routed,
                profile_id=request.profile_id,
                texte_uid=request.texte_uid,
            )
        except Exception as e:
            available = list(AGENTS.keys()) + [a for a in LANGGRAPH_AGENTS if a not in AGENTS]
            return ChatResponse(
                response=f"Agent '{request.agent}' inconnu. Agents : {', '.join(available)}",
                agent=request.agent,
            )

    # Construire le message enrichi si texte_uid fourni
    message = request.message
    if request.texte_uid:
        context_parts = []

        # TexteBrief
        result = await db.execute(
            select(TexteBrief).where(
                TexteBrief.profile_id == profile.id,
                TexteBrief.texte_uid == request.texte_uid,
            )
        )
        brief = result.scalar_one_or_none()
        if brief:
            texte = await db.get(Texte, request.texte_uid)
            context_parts.append(
                f"CONTEXTE DOSSIER : {texte.titre_court or texte.titre or request.texte_uid}"
                if texte else f"CONTEXTE DOSSIER : {request.texte_uid}"
            )
            context_parts.append(f"Impact : {brief.impact_level}")
            if brief.executive_summary:
                context_parts.append(f"Resume : {brief.executive_summary[:400]}")
            if brief.exposure_eur:
                context_parts.append(f"Exposition : {brief.exposure_eur:,.0f} EUR")

            # Contacts cles
            try:
                contacts = json.loads(brief.key_contacts or "[]")
                if contacts:
                    names = [c.get("nom", "") for c in contacts[:5]]
                    context_parts.append(f"Contacts cles : {', '.join(names)}")
            except (json.JSONDecodeError, TypeError):
                pass

        # Actions existantes
        result = await db.execute(
            select(ActionTask).where(
                ActionTask.texte_uid == request.texte_uid,
                ActionTask.profile_id == profile.id,
            ).limit(5)
        )
        actions = result.scalars().all()
        if actions:
            context_parts.append("Actions en cours :")
            for a in actions:
                context_parts.append(f"  - [{a.status}] {a.label}")

        if context_parts:
            message = "\n".join(context_parts) + f"\n\nQUESTION : {request.message}"

    agent = agent_class()
    logger.info(
        "Chat [%s] profil=%s texte=%s: %s",
        request.agent,
        request.profile_id,
        request.texte_uid or "none",
        request.message[:100],
    )

    try:
        response_text = await agent.run(
            message,
            db=db,
            profile_id=request.profile_id,
        )
        return ChatResponse(
            response=response_text,
            agent=request.agent,
            agent_routed=agent_routed,
            profile_id=request.profile_id,
            texte_uid=request.texte_uid,
        )
    except Exception as e:
        logger.error("Erreur agent %s: %s", request.agent, e)
        return ChatResponse(
            response=f"Erreur lors du traitement : {str(e)}",
            agent=request.agent,
        )

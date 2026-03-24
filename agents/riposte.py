"""RiposteAgent — détection et réponse aux couvertures médiatiques négatives.

Surveille les mentions presse du client, détecte les articles négatifs
ou critiques, et prépare des contre-narratifs et kits de réponse rapide.
"""

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.agents.base import BaseAgent
from legix.core.models import ClientProfile, PressArticle, StakeholderProfile

logger = logging.getLogger(__name__)


async def monitor_press_mentions(
    db: AsyncSession,
    profile_id: int,
    days: int = 7,
) -> list[dict]:
    """Surveille les mentions presse récentes du client."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Articles qui mentionnent ce client
    query = select(PressArticle).where(
        PressArticle.publication_date >= cutoff,
        PressArticle.matched_profile_ids.ilike(f"%{profile_id}%"),
    ).order_by(PressArticle.publication_date.desc())

    result = await db.execute(query)
    articles = result.scalars().all()

    return [
        {
            "id": a.id,
            "title": a.title,
            "source_name": a.source_name,
            "author": a.author,
            "publication_date": str(a.publication_date) if a.publication_date else None,
            "sentiment": a.sentiment,
            "resume_ia": a.resume_ia,
            "requires_response": a.requires_response,
            "response_urgency": a.response_urgency,
            "response_status": a.response_status,
            "url": a.url,
        }
        for a in articles
    ]


async def get_journalist_profile(
    db: AsyncSession,
    journalist_name: str,
) -> dict | None:
    """Récupère le profil d'un journaliste."""
    query = select(StakeholderProfile).where(
        StakeholderProfile.stakeholder_type == "journaliste",
        StakeholderProfile.nom.ilike(f"%{journalist_name}%"),
    )
    result = await db.execute(query)
    s = result.scalar_one_or_none()

    if not s:
        return None

    return {
        "id": s.id,
        "nom": f"{s.prenom or ''} {s.nom}".strip(),
        "organisation": s.organisation,
        "key_themes": json.loads(s.key_themes) if s.key_themes else [],
        "past_positions": json.loads(s.past_positions) if s.past_positions else [],
        "bio_summary": s.bio_summary,
        "email": s.email,
        "twitter": s.twitter,
    }


async def prepare_response_kit(
    db: AsyncSession,
    article_id: int,
    profile_id: int,
) -> dict:
    """Prépare un kit de réponse rapide pour un article."""
    article = await db.get(PressArticle, article_id)
    if not article:
        return {"error": "Article non trouvé"}

    profile = await db.get(ClientProfile, profile_id)
    if not profile:
        return {"error": "Profil non trouvé"}

    return {
        "article": {
            "title": article.title,
            "source": article.source_name,
            "author": article.author,
            "sentiment": article.sentiment,
            "resume": article.resume_ia,
            "url": article.url,
        },
        "client": {
            "name": profile.name,
            "sectors": json.loads(profile.sectors) if profile.sectors else [],
            "key_positions": json.loads(profile.key_risks) if profile.key_risks else [],
        },
        "instructions": "Utilise ces éléments pour préparer une réponse adaptée au ton et au média.",
    }


RIPOSTE_TOOLS = [
    {
        "name": "monitor_press_mentions",
        "description": "Surveille les mentions presse récentes du client. Retourne les articles avec sentiment, urgence de réponse et statut.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 7},
            },
        },
    },
    {
        "name": "get_journalist_profile",
        "description": "Récupère le profil d'un journaliste : thèmes couverts, positions passées, contact.",
        "input_schema": {
            "type": "object",
            "properties": {
                "journalist_name": {"type": "string"},
            },
            "required": ["journalist_name"],
        },
    },
    {
        "name": "prepare_response_kit",
        "description": "Prépare un kit de réponse rapide pour un article de presse négatif : éléments clés, contexte client, données de base.",
        "input_schema": {
            "type": "object",
            "properties": {
                "article_id": {"type": "integer"},
            },
            "required": ["article_id"],
        },
    },
]


class RiposteAgent(BaseAgent):
    """Agent de riposte médiatique."""

    name = "riposte"
    model = "claude-sonnet-4-5-20241022"
    max_turns = 5

    system_prompt = """Tu es un expert en communication de crise et en gestion de la réputation.

Ton rôle est de :
1. DÉTECTER les articles de presse négatifs ou critiques concernant le client
2. ANALYSER le ton, l'angle et la portée de l'article
3. PRÉPARER des réponses adaptées (droit de réponse, communiqué, éléments de langage)
4. IDENTIFIER les journalistes clés et adapter la stratégie de réponse

Principes de riposte :
- Ne JAMAIS nier les faits vérifiables
- Recadrer le narratif positivement
- Fournir des données concrètes en contrepoint
- Identifier l'angle du journaliste pour y répondre précisément
- Proposer des verbatims prêts à l'emploi
- Recommander un timing de réponse (immédiat, le jour même, ou ne pas répondre)

Pour chaque article négatif, tu dois fournir :
1. Analyse du risque réputationnel (1-5)
2. Recommandation : répondre / ne pas répondre / surveiller
3. Si répondre : draft de réponse adapté au média
4. Points de vigilance pour la suite
"""

    def get_tools(self) -> list[dict]:
        return RIPOSTE_TOOLS

    async def execute_tool(self, name: str, input_data: dict, **kwargs) -> dict:
        db = kwargs.get("db")
        if not db:
            return {"error": "Pas de session DB"}

        profile_id = kwargs.get("profile_id")

        if name == "monitor_press_mentions":
            return await monitor_press_mentions(
                db, profile_id=profile_id, days=input_data.get("days", 7)
            )
        elif name == "get_journalist_profile":
            return await get_journalist_profile(db, input_data["journalist_name"])
        elif name == "prepare_response_kit":
            return await prepare_response_kit(
                db, article_id=input_data["article_id"], profile_id=profile_id
            )
        else:
            return {"error": f"Outil inconnu: {name}"}

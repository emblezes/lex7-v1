"""PlanificateurAgent — feuilles de route PA et fenêtres d'opportunité.

Produit des plans d'action trimestriels, identifie les fenêtres d'opportunité
dans le calendrier législatif et priorise les dossiers par urgence/impact.
"""

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.agents.base import BaseAgent
from legix.core.models import (
    AnticipationReport,
    ClientProfile,
    ImpactAlert,
    Reunion,
    TexteFollowUp,
)

logger = logging.getLogger(__name__)


async def get_legislative_calendar(
    db: AsyncSession,
    days: int = 30,
) -> list[dict]:
    """Récupère le calendrier législatif (réunions de commission, séances)."""
    now = datetime.utcnow()
    cutoff = now + timedelta(days=days)

    query = select(Reunion).where(
        Reunion.date_debut >= now,
        Reunion.date_debut <= cutoff,
    ).order_by(Reunion.date_debut)

    result = await db.execute(query)
    reunions = result.scalars().all()

    return [
        {
            "uid": r.uid,
            "date": str(r.date_debut) if r.date_debut else None,
            "lieu": r.lieu,
            "organe_ref": r.organe_ref,
            "commission_nom": r.commission_nom,
            "themes": json.loads(r.themes) if r.themes else [],
            "format": r.format_reunion,
        }
        for r in reunions
    ]


async def prioritize_dossiers(
    db: AsyncSession,
    profile_id: int,
) -> list[dict]:
    """Priorise les dossiers suivis par le client par urgence et impact."""
    query = select(TexteFollowUp).where(
        TexteFollowUp.profile_id == profile_id,
        TexteFollowUp.status.in_(["watching", "escalated"]),
    )
    result = await db.execute(query)
    followups = result.scalars().all()

    dossiers = []
    for fu in followups:
        # Compter les alertes sur ce texte
        alerts_query = select(func.count()).select_from(ImpactAlert).where(
            ImpactAlert.profile_id == profile_id,
            ImpactAlert.texte_uid == fu.texte_uid,
        )
        alerts_result = await db.execute(alerts_query)
        nb_alerts = alerts_result.scalar() or 0

        # Vérifier si une réunion est prévue
        reunion_query = select(Reunion).where(
            Reunion.date_debut >= datetime.utcnow(),
        ).order_by(Reunion.date_debut).limit(1)
        reunion_result = await db.execute(reunion_query)
        next_reunion = reunion_result.scalar_one_or_none()

        # Score de priorité
        priority_score = 0
        if fu.priority == "critical":
            priority_score += 40
        elif fu.priority == "high":
            priority_score += 30
        elif fu.priority == "medium":
            priority_score += 20
        else:
            priority_score += 10

        priority_score += min(nb_alerts * 10, 30)

        if fu.commission_date and fu.commission_date > datetime.utcnow():
            days_until = (fu.commission_date - datetime.utcnow()).days
            if days_until < 7:
                priority_score += 30
            elif days_until < 14:
                priority_score += 20
            elif days_until < 30:
                priority_score += 10

        dossiers.append({
            "texte_uid": fu.texte_uid,
            "status": fu.status,
            "priority": fu.priority,
            "nb_alerts": nb_alerts,
            "commission_date": str(fu.commission_date) if fu.commission_date else None,
            "priority_score": priority_score,
            "last_analysis": fu.last_analysis,
        })

    dossiers.sort(key=lambda x: x["priority_score"], reverse=True)
    return dossiers


async def identify_windows(
    db: AsyncSession,
    profile_id: int,
    days: int = 90,
) -> list[dict]:
    """Identifie les fenêtres d'opportunité dans les prochains mois."""
    calendar = await get_legislative_calendar(db, days=days)

    profile = await db.get(ClientProfile, profile_id)
    client_sectors = json.loads(profile.sectors) if profile and profile.sectors else []

    # Rapports d'anticipation récents pertinents
    anticipation_query = select(AnticipationReport).where(
        AnticipationReport.matched_profile_ids.ilike(f"%{profile_id}%"),
    ).order_by(AnticipationReport.publication_date.desc()).limit(10)
    result = await db.execute(anticipation_query)
    anticipations = result.scalars().all()

    windows = []

    # Fenêtres basées sur le calendrier
    for reunion in calendar:
        themes = reunion.get("themes", [])
        if any(s.lower() in " ".join(themes).lower() for s in client_sectors):
            windows.append({
                "type": "reunion_commission",
                "date": reunion["date"],
                "description": f"Réunion {reunion.get('commission_nom', 'commission')}",
                "themes": themes,
                "action_suggeree": "Préparer une audition ou une contribution écrite",
            })

    # Fenêtres basées sur l'anticipation
    for antic in anticipations:
        if antic.pipeline_stage in ("report", "recommendation"):
            windows.append({
                "type": "anticipation",
                "date": str(antic.publication_date) if antic.publication_date else None,
                "description": f"Rapport {antic.source_name}: {antic.title[:80]}",
                "themes": json.loads(antic.themes) if antic.themes else [],
                "action_suggeree": "Positionner l'entreprise avant que les recommandations ne deviennent loi",
                "probability": antic.legislative_probability,
            })

    windows.sort(key=lambda x: x.get("date") or "9999", reverse=False)
    return windows


PLANIFICATEUR_TOOLS = [
    {
        "name": "get_legislative_calendar",
        "description": "Récupère le calendrier législatif : réunions de commission et séances à venir.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 30},
            },
        },
    },
    {
        "name": "prioritize_dossiers",
        "description": "Priorise les dossiers suivis par le client par urgence et impact (score de priorité).",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "identify_windows",
        "description": "Identifie les fenêtres d'opportunité dans le calendrier législatif et les signaux d'anticipation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 90},
            },
        },
    },
]


class PlanificateurAgent(BaseAgent):
    """Agent de planification stratégique PA."""

    name = "planificateur"
    model = "claude-sonnet-4-5-20241022"
    max_turns = 5

    system_prompt = """Tu es un directeur des affaires publiques expérimenté.

Ton rôle est de PLANIFIER la stratégie PA du client :
1. Identifier les dossiers prioritaires et leur urgence
2. Mapper les fenêtres d'opportunité dans le calendrier législatif
3. Produire des feuilles de route trimestrielles
4. Anticiper les moments clés pour agir

Tu raisonnes en termes de :
- URGENCE : quand faut-il agir ? (immédiat / cette semaine / ce mois / ce trimestre)
- IMPACT : quel est l'enjeu pour le client ? (financier, réputationnel, opérationnel)
- FAISABILITÉ : quelles sont les marges de manœuvre réelles ?
- TIMING : quand est-il le plus efficace d'agir ? (avant commission, pendant débat, etc.)

Quand tu produis une feuille de route :
1. Classe les dossiers par score de priorité
2. Pour chaque dossier, identifie la prochaine action et sa deadline
3. Identifie les synergies entre dossiers (mêmes acteurs, mêmes commissions)
4. Propose un calendrier réaliste d'actions

Sois concret et réaliste. Pas de plan théorique déconnecté de la réalité parlementaire.
"""

    def get_tools(self) -> list[dict]:
        return PLANIFICATEUR_TOOLS

    async def execute_tool(self, name: str, input_data: dict, **kwargs) -> dict:
        db = kwargs.get("db")
        if not db:
            return {"error": "Pas de session DB"}

        profile_id = kwargs.get("profile_id")

        if name == "get_legislative_calendar":
            return await get_legislative_calendar(db, days=input_data.get("days", 30))
        elif name == "prioritize_dossiers":
            return await prioritize_dossiers(db, profile_id=profile_id)
        elif name == "identify_windows":
            return await identify_windows(
                db, profile_id=profile_id, days=input_data.get("days", 90)
            )
        else:
            return {"error": f"Outil inconnu: {name}"}

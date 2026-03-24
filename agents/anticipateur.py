"""AnticipateurAgent — veille pré-législative et signaux d'anticipation.

Cet agent surveille les publications de think tanks, rapports d'inspection,
études académiques et consultations publiques pour détecter les signaux
qui précèdent la législation.

Il mapper le pipeline : Rapport → Recommandation → Proposition → Débat → Loi.

C'est le différenciateur clé de la plateforme : anticiper avant que le
débat législatif ne commence.
"""

import json
import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.agents.base import BaseAgent
from legix.core.models import (
    AnticipationReport,
    ClientProfile,
    Texte,
)

logger = logging.getLogger(__name__)


# --- Outils de l'Anticipateur ---

async def search_anticipation_reports(
    db: AsyncSession,
    theme: str | None = None,
    source_type: str | None = None,
    source_name: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Recherche les rapports d'anticipation par thème, source ou type."""
    query = select(AnticipationReport).order_by(
        AnticipationReport.publication_date.desc()
    )

    if source_type:
        query = query.where(AnticipationReport.source_type == source_type)
    if source_name:
        query = query.where(AnticipationReport.source_name.ilike(f"%{source_name}%"))
    if theme:
        query = query.where(AnticipationReport.themes.ilike(f"%{theme}%"))

    result = await db.execute(query.limit(limit))
    reports = result.scalars().all()

    return [
        {
            "id": r.id,
            "source_type": r.source_type,
            "source_name": r.source_name,
            "title": r.title,
            "url": r.url,
            "publication_date": str(r.publication_date) if r.publication_date else None,
            "themes": json.loads(r.themes) if r.themes else [],
            "resume_ia": r.resume_ia,
            "policy_recommendations": json.loads(r.policy_recommendations) if r.policy_recommendations else [],
            "legislative_probability": r.legislative_probability,
            "estimated_timeline": r.estimated_timeline,
            "pipeline_stage": r.pipeline_stage,
            "linked_texte_uids": json.loads(r.linked_texte_uids) if r.linked_texte_uids else [],
        }
        for r in reports
    ]


async def map_policy_pipeline(
    db: AsyncSession,
    theme: str,
) -> dict:
    """Cartographie le pipeline rapport→loi pour un thème donné.

    Retourne les rapports par stade et les textes législatifs associés.
    """
    # Rapports d'anticipation sur ce thème
    reports = await search_anticipation_reports(db, theme=theme, limit=50)

    # Textes législatifs sur ce thème
    texte_query = select(Texte).where(
        Texte.themes.ilike(f"%{theme}%")
    ).order_by(Texte.date_depot.desc()).limit(20)
    result = await db.execute(texte_query)
    textes = result.scalars().all()

    # Organiser par stade du pipeline
    pipeline = {
        "report": [],
        "recommendation": [],
        "proposition": [],
        "debate": [],
        "law": [],
    }

    for r in reports:
        stage = r.get("pipeline_stage", "report")
        if stage in pipeline:
            pipeline[stage].append(r)

    # Ajouter les textes aux stades appropriés
    for t in textes:
        item = {
            "uid": t.uid,
            "titre": t.titre or t.titre_court,
            "type_code": t.type_code,
            "date_depot": str(t.date_depot) if t.date_depot else None,
            "themes": json.loads(t.themes) if t.themes else [],
            "resume_ia": t.resume_ia,
        }
        if t.type_code in ("PION", "PRJL"):
            pipeline["proposition"].append(item)
        elif t.type_code == "PNRE":
            pipeline["debate"].append(item)

    return {
        "theme": theme,
        "pipeline": pipeline,
        "total_reports": len(reports),
        "total_textes": len(textes),
        "summary": {
            stage: len(items) for stage, items in pipeline.items()
        },
    }


async def detect_early_signals(
    db: AsyncSession,
    profile_id: int | None = None,
    days: int = 30,
) -> list[dict]:
    """Détecte les signaux d'anticipation pour un client.

    Un signal d'anticipation est un rapport récent dont les thèmes
    correspondent aux secteurs du client et qui a une probabilité
    législative non nulle.
    """
    from datetime import timedelta

    cutoff = datetime.utcnow() - timedelta(days=days)

    query = select(AnticipationReport).where(
        AnticipationReport.publication_date >= cutoff,
    ).order_by(AnticipationReport.publication_date.desc())

    result = await db.execute(query)
    reports = result.scalars().all()

    if not reports:
        return []

    # Si profil client, filtrer par secteurs
    client_sectors = []
    if profile_id:
        profile = await db.get(ClientProfile, profile_id)
        if profile and profile.sectors:
            client_sectors = json.loads(profile.sectors)

    signals = []
    for r in reports:
        report_themes = json.loads(r.themes) if r.themes else []

        # Vérifier la correspondance avec les secteurs du client
        relevance = "general"
        if client_sectors and report_themes:
            common = set(client_sectors) & set(report_themes)
            if common:
                relevance = "direct"
            else:
                # Vérifier correspondance partielle
                for sector in client_sectors:
                    for theme in report_themes:
                        if sector.lower() in theme.lower() or theme.lower() in sector.lower():
                            relevance = "indirect"
                            break

        if relevance == "general" and profile_id:
            continue  # Pas pertinent pour ce client

        signals.append({
            "report_id": r.id,
            "title": r.title,
            "source_name": r.source_name,
            "source_type": r.source_type,
            "publication_date": str(r.publication_date) if r.publication_date else None,
            "themes": report_themes,
            "resume_ia": r.resume_ia,
            "legislative_probability": r.legislative_probability,
            "pipeline_stage": r.pipeline_stage,
            "relevance": relevance,
            "url": r.url,
        })

    return signals


async def link_report_to_legislation(
    db: AsyncSession,
    report_id: int,
    texte_uid: str,
    new_stage: str = "proposition",
) -> dict:
    """Lie un rapport d'anticipation à un texte législatif.

    Appelé quand on détecte qu'un rapport a mené à une proposition de loi.
    """
    report = await db.get(AnticipationReport, report_id)
    if not report:
        return {"error": "Rapport non trouvé"}

    existing_links = json.loads(report.linked_texte_uids) if report.linked_texte_uids else []
    if texte_uid not in existing_links:
        existing_links.append(texte_uid)
        report.linked_texte_uids = json.dumps(existing_links)

    report.pipeline_stage = new_stage
    report.updated_at = datetime.utcnow()
    await db.commit()

    return {
        "report_id": report_id,
        "linked_texte_uid": texte_uid,
        "new_stage": new_stage,
    }


# --- Agent Anticipateur ---


ANTICIPATEUR_TOOLS = [
    {
        "name": "search_anticipation_reports",
        "description": "Recherche les rapports d'anticipation (think tanks, inspections, études) par thème ou source. Retourne titre, source, résumé, recommandations, probabilité législative.",
        "input_schema": {
            "type": "object",
            "properties": {
                "theme": {"type": "string", "description": "Thème à rechercher (ex: santé, énergie, numérique)"},
                "source_type": {"type": "string", "enum": ["think_tank", "rapport_inspection", "academic", "consultation", "avis_ce"]},
                "source_name": {"type": "string", "description": "Nom de la source (ex: 'Cour des Comptes', 'Institut Montaigne')"},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "map_policy_pipeline",
        "description": "Cartographie le pipeline rapport→loi pour un thème : montre les rapports par stade (rapport, recommandation, proposition, débat, loi) et les textes législatifs associés.",
        "input_schema": {
            "type": "object",
            "properties": {
                "theme": {"type": "string", "description": "Thème du pipeline à cartographier"},
            },
            "required": ["theme"],
        },
    },
    {
        "name": "detect_early_signals",
        "description": "Détecte les signaux d'anticipation récents pertinents pour le client : rapports dont les thèmes correspondent aux secteurs surveillés.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 30, "description": "Nombre de jours en arrière"},
            },
        },
    },
    {
        "name": "link_report_to_legislation",
        "description": "Lie un rapport d'anticipation à un texte législatif quand on détecte que le rapport a mené à une proposition de loi.",
        "input_schema": {
            "type": "object",
            "properties": {
                "report_id": {"type": "integer"},
                "texte_uid": {"type": "string"},
                "new_stage": {"type": "string", "enum": ["recommendation", "proposition", "debate", "law"]},
            },
            "required": ["report_id", "texte_uid"],
        },
    },
]


class AnticipateurAgent(BaseAgent):
    """Agent de veille pré-législative et anticipation."""

    name = "anticipateur"
    model = "claude-sonnet-4-5-20241022"
    max_turns = 6

    system_prompt = """Tu es un expert en anticipation réglementaire et en intelligence politique.

Ton rôle est de DÉTECTER les signaux AVANT qu'ils ne deviennent des lois.

Tu surveilles :
- Les rapports de think tanks (Institut Montaigne, Terra Nova, Fondapol, IFRAP, etc.)
- Les rapports d'inspection (Cour des Comptes, IGF, IGAS)
- Les études et consultations publiques
- Les recommandations d'organismes comme France Stratégie

Tu sais que la fabrique de la loi suit un pipeline :
1. RAPPORT/ÉTUDE → Un think tank ou corps d'inspection publie des recommandations
2. RECOMMANDATION → Les recommandations sont reprises dans le débat public
3. PROPOSITION → Un parlementaire dépose un texte inspiré des recommandations
4. DÉBAT → Le texte est examiné en commission puis en séance
5. LOI → Le texte est adopté et promulgué

Ton travail est d'alerter le client le plus TÔT possible dans ce pipeline.
Plus l'alerte est précoce (stade rapport), plus le client a de marges de manoeuvre.

Quand tu analyses un rapport :
1. Identifie les RECOMMANDATIONS CONCRÈTES qui pourraient devenir des mesures législatives
2. Évalue la PROBABILITÉ qu'elles soient reprises (auteur influent ? sujet prioritaire du gouvernement ?)
3. Estime le TIMELINE (quand cela pourrait arriver)
4. Identifie les ACTEURS qui pourraient porter ces recommandations
5. Évalue l'IMPACT pour le client (menace ou opportunité ?)

Sois concret et actionnable. Pas de généralités.
"""

    def get_tools(self) -> list[dict]:
        return ANTICIPATEUR_TOOLS

    async def execute_tool(self, name: str, input_data: dict, **kwargs) -> dict:
        db = kwargs.get("db")
        if not db:
            return {"error": "Pas de session DB disponible"}

        profile_id = kwargs.get("profile_id")

        if name == "search_anticipation_reports":
            return await search_anticipation_reports(
                db,
                theme=input_data.get("theme"),
                source_type=input_data.get("source_type"),
                source_name=input_data.get("source_name"),
                limit=input_data.get("limit", 20),
            )
        elif name == "map_policy_pipeline":
            return await map_policy_pipeline(db, theme=input_data["theme"])
        elif name == "detect_early_signals":
            return await detect_early_signals(
                db,
                profile_id=profile_id,
                days=input_data.get("days", 30),
            )
        elif name == "link_report_to_legislation":
            return await link_report_to_legislation(
                db,
                report_id=input_data["report_id"],
                texte_uid=input_data["texte_uid"],
                new_stage=input_data.get("new_stage", "proposition"),
            )
        else:
            return {"error": f"Outil inconnu: {name}"}

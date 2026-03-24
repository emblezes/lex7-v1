"""CartographeAgent — cartographie des stakeholders par dossier.

Construit et maintient les cartes de parties prenantes :
- Qui est pour, qui est contre, qui est indécis
- Scores d'influence et de pertinence par dossier
- Relations entre stakeholders (coalitions, oppositions)
"""

import json
import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.agents.base import BaseAgent
from legix.core.models import (
    Acteur,
    Amendement,
    Organe,
    StakeholderDossierLink,
    StakeholderProfile,
    Texte,
)

logger = logging.getLogger(__name__)


async def build_stakeholder_map(
    db: AsyncSession,
    texte_uid: str,
    profile_id: int | None = None,
) -> dict:
    """Construit la carte des stakeholders pour un texte législatif."""
    texte = await db.get(Texte, texte_uid)
    if not texte:
        return {"error": "Texte non trouvé"}

    # Récupérer les amendements sur ce texte
    amdt_query = select(Amendement).where(Amendement.texte_ref == texte_uid)
    result = await db.execute(amdt_query)
    amdts = result.scalars().all()

    # Construire la carte par auteur
    actors_map: dict[str, dict] = {}
    for amdt in amdts:
        if not amdt.auteur_ref:
            continue

        if amdt.auteur_ref not in actors_map:
            acteur = await db.get(Acteur, amdt.auteur_ref)
            groupe = await db.get(Organe, amdt.groupe_ref) if amdt.groupe_ref else None
            actors_map[amdt.auteur_ref] = {
                "uid": amdt.auteur_ref,
                "nom": f"{acteur.prenom} {acteur.nom}" if acteur else amdt.auteur_ref,
                "groupe": groupe.libelle_court if groupe else amdt.groupe_nom or "",
                "nb_amendements": 0,
                "amendements_adoptes": 0,
                "amendements_rejetes": 0,
                "est_gouvernement": amdt.auteur_type == "Gouvernement",
                "themes_abordes": [],
            }

        entry = actors_map[amdt.auteur_ref]
        entry["nb_amendements"] += 1
        if amdt.sort == "Adopté":
            entry["amendements_adoptes"] += 1
        elif amdt.sort == "Rejeté":
            entry["amendements_rejetes"] += 1

        if amdt.themes:
            themes = json.loads(amdt.themes) if isinstance(amdt.themes, str) else amdt.themes
            entry["themes_abordes"].extend(themes)

    # Calculer les scores
    for uid, data in actors_map.items():
        total = data["nb_amendements"]
        adoptes = data["amendements_adoptes"]
        data["taux_adoption"] = round(adoptes / total, 2) if total > 0 else 0
        data["themes_abordes"] = list(set(data["themes_abordes"]))
        data["influence_score"] = _compute_influence(data)

    # Trier par influence
    sorted_actors = sorted(
        actors_map.values(),
        key=lambda x: x["influence_score"],
        reverse=True,
    )

    # Regrouper par groupe politique
    groups_map: dict[str, dict] = {}
    for actor in sorted_actors:
        grp = actor["groupe"] or "Sans groupe"
        if grp not in groups_map:
            groups_map[grp] = {
                "groupe": grp,
                "nb_acteurs": 0,
                "nb_amendements": 0,
                "nb_adoptes": 0,
                "position_estimee": "indecis",
                "acteurs_cles": [],
            }
        groups_map[grp]["nb_acteurs"] += 1
        groups_map[grp]["nb_amendements"] += actor["nb_amendements"]
        groups_map[grp]["nb_adoptes"] += actor["amendements_adoptes"]
        if len(groups_map[grp]["acteurs_cles"]) < 3:
            groups_map[grp]["acteurs_cles"].append(actor["nom"])

    for grp_data in groups_map.values():
        total = grp_data["nb_amendements"]
        grp_data["taux_adoption"] = round(grp_data["nb_adoptes"] / total, 2) if total > 0 else 0

    return {
        "texte_uid": texte_uid,
        "texte_titre": texte.titre or texte.titre_court,
        "total_acteurs": len(actors_map),
        "total_amendements": len(amdts),
        "acteurs_cles": sorted_actors[:15],
        "groupes": list(groups_map.values()),
    }


async def find_stakeholders_by_type(
    db: AsyncSession,
    stakeholder_type: str,
    theme: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Recherche des stakeholders par type et optionnellement par thème."""
    query = select(StakeholderProfile).where(
        StakeholderProfile.stakeholder_type == stakeholder_type
    )
    if theme:
        query = query.where(StakeholderProfile.key_themes.ilike(f"%{theme}%"))
    query = query.order_by(StakeholderProfile.influence_score.desc().nullslast())
    query = query.limit(limit)

    result = await db.execute(query)
    stakeholders = result.scalars().all()

    return [
        {
            "id": s.id,
            "type": s.stakeholder_type,
            "nom": f"{s.prenom or ''} {s.nom}".strip(),
            "organisation": s.organisation,
            "titre": s.titre,
            "influence_score": s.influence_score,
            "key_themes": json.loads(s.key_themes) if s.key_themes else [],
            "relationship_status": s.relationship_status,
            "bio_summary": s.bio_summary,
            "email": s.email,
            "twitter": s.twitter,
        }
        for s in stakeholders
    ]


def _compute_influence(actor_data: dict) -> float:
    """Calcule un score d'influence basique pour un acteur sur un dossier."""
    score = 0.0
    # Nombre d'amendements (activité)
    nb = actor_data["nb_amendements"]
    score += min(nb * 5, 30)
    # Taux d'adoption (efficacité)
    score += actor_data["taux_adoption"] * 40
    # Gouvernement (poids institutionnel)
    if actor_data["est_gouvernement"]:
        score += 30
    return round(min(score, 100), 1)


CARTOGRAPHE_TOOLS = [
    {
        "name": "build_stakeholder_map",
        "description": "Construit la carte complète des stakeholders pour un texte législatif : acteurs clés, groupes politiques, positions, scores d'influence.",
        "input_schema": {
            "type": "object",
            "properties": {
                "texte_uid": {"type": "string", "description": "UID du texte législatif"},
            },
            "required": ["texte_uid"],
        },
    },
    {
        "name": "find_stakeholders_by_type",
        "description": "Recherche des stakeholders par type (journaliste, ong, federation, etc.) et optionnellement par thème.",
        "input_schema": {
            "type": "object",
            "properties": {
                "stakeholder_type": {"type": "string", "enum": ["depute", "senateur", "journaliste", "ong", "federation", "collaborateur", "regulateur"]},
                "theme": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["stakeholder_type"],
        },
    },
]


class CartographeAgent(BaseAgent):
    """Agent de cartographie des parties prenantes."""

    name = "cartographe"
    model = "claude-sonnet-4-5-20241022"
    max_turns = 5

    system_prompt = """Tu es un expert en cartographie politique et en mapping des parties prenantes.

Ton rôle est de CONSTRUIRE ET ANALYSER la carte des acteurs sur un dossier réglementaire :
- Qui est pour, qui est contre, qui est indécis
- Quel est le rapport de forces
- Où sont les leviers d'influence
- Qui contacter en priorité et pourquoi

Tu analyses :
- Les amendements déposés (qui amende quoi, dans quel sens)
- Les votes passés des acteurs
- Les positions publiques connues
- Les relations entre groupes et acteurs

Ton analyse doit être ACTIONNABLE :
- Identifier les 3-5 acteurs à contacter en priorité
- Expliquer POURQUOI chacun est important
- Suggérer l'ANGLE d'approche adapté à chaque acteur
- Identifier les coalitions possibles et les oppositions à anticiper
"""

    def get_tools(self) -> list[dict]:
        return CARTOGRAPHE_TOOLS

    async def execute_tool(self, name: str, input_data: dict, **kwargs) -> dict:
        db = kwargs.get("db")
        if not db:
            return {"error": "Pas de session DB"}

        if name == "build_stakeholder_map":
            return await build_stakeholder_map(
                db,
                texte_uid=input_data["texte_uid"],
                profile_id=kwargs.get("profile_id"),
            )
        elif name == "find_stakeholders_by_type":
            return await find_stakeholders_by_type(
                db,
                stakeholder_type=input_data["stakeholder_type"],
                theme=input_data.get("theme"),
                limit=input_data.get("limit", 20),
            )
        else:
            return {"error": f"Outil inconnu: {name}"}

"""ProfilActeurAgent — construction de personas interactives.

Construit des profils enrichis de décideurs (politiques, journalistes, ONG)
en ingérant toutes les données publiques disponibles. Permet de simuler
leurs réactions à des mesures ou arguments.
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
    ScrutinVote,
    StakeholderProfile,
)

logger = logging.getLogger(__name__)


async def build_politician_persona(
    db: AsyncSession,
    acteur_uid: str,
) -> dict:
    """Construit une persona complète pour un parlementaire."""
    acteur = await db.get(Acteur, acteur_uid)
    if not acteur:
        return {"error": "Acteur non trouvé"}

    groupe = await db.get(Organe, acteur.groupe_politique_ref) if acteur.groupe_politique_ref else None

    # Amendements déposés
    amdt_query = select(Amendement).where(Amendement.auteur_ref == acteur_uid)
    result = await db.execute(amdt_query)
    amdts = result.scalars().all()

    # Statistiques par thème
    themes_stats: dict[str, dict] = {}
    for a in amdts:
        if not a.themes:
            continue
        themes = json.loads(a.themes) if isinstance(a.themes, str) else a.themes
        for t in themes:
            if t not in themes_stats:
                themes_stats[t] = {"total": 0, "adoptes": 0}
            themes_stats[t]["total"] += 1
            if a.sort == "Adopté":
                themes_stats[t]["adoptes"] += 1

    for t, s in themes_stats.items():
        s["taux_adoption"] = round(s["adoptes"] / s["total"], 2) if s["total"] > 0 else 0

    # Votes nominatifs
    votes_query = select(ScrutinVote).where(
        ScrutinVote.acteur_uid == acteur_uid
    ).order_by(ScrutinVote.scrutin_date.desc()).limit(50)
    result = await db.execute(votes_query)
    votes = result.scalars().all()

    votes_summary = {
        "pour": sum(1 for v in votes if v.position == "pour"),
        "contre": sum(1 for v in votes if v.position == "contre"),
        "abstention": sum(1 for v in votes if v.position == "abstention"),
        "total": len(votes),
        "derniers_votes": [
            {
                "scrutin": v.scrutin_titre[:100] if v.scrutin_titre else "",
                "position": v.position,
                "date": str(v.scrutin_date) if v.scrutin_date else None,
            }
            for v in votes[:10]
        ],
    }

    # Cosignataires fréquents
    cosign_query = select(
        Amendement.auteur_ref,
        func.count().label("nb"),
    ).where(
        Amendement.texte_ref.in_([a.texte_ref for a in amdts if a.texte_ref]),
        Amendement.auteur_ref != acteur_uid,
        Amendement.auteur_ref.isnot(None),
    ).group_by(Amendement.auteur_ref).order_by(func.count().desc()).limit(10)
    result = await db.execute(cosign_query)
    frequents = result.all()

    frequent_allies = []
    for uid, nb in frequents:
        ally = await db.get(Acteur, uid)
        if ally:
            frequent_allies.append({
                "uid": uid,
                "nom": f"{ally.prenom} {ally.nom}",
                "nb_textes_communs": nb,
            })

    return {
        "uid": acteur_uid,
        "identite": {
            "prenom": acteur.prenom,
            "nom": acteur.nom,
            "groupe": groupe.libelle if groupe else "",
            "profession": acteur.profession,
            "email": acteur.email,
            "twitter": acteur.twitter,
            "collaborateurs": json.loads(acteur.collaborateurs) if acteur.collaborateurs else [],
        },
        "activite_legislative": {
            "nb_amendements": len(amdts),
            "nb_adoptes": sum(1 for a in amdts if a.sort == "Adopté"),
            "taux_adoption_global": round(
                sum(1 for a in amdts if a.sort == "Adopté") / len(amdts), 2
            ) if amdts else 0,
            "themes_principaux": sorted(
                themes_stats.items(),
                key=lambda x: x[1]["total"],
                reverse=True,
            )[:5],
        },
        "votes": votes_summary,
        "reseau": {
            "allies_frequents": frequent_allies,
        },
        "specialites": json.loads(acteur.specialites) if acteur.specialites else [],
        "influence_score": acteur.influence_score,
    }


async def simulate_reaction(
    db: AsyncSession,
    acteur_uid: str,
    measure_description: str,
) -> dict:
    """Simule la réaction d'un acteur à une mesure.

    Retourne les données nécessaires pour que l'IA génère la simulation.
    La simulation elle-même est faite par le LLM dans sa réponse.
    """
    persona = await build_politician_persona(db, acteur_uid)
    if "error" in persona:
        return persona

    return {
        "persona": persona,
        "measure": measure_description,
        "instruction": "Simule la réaction de cet acteur à cette mesure en te basant sur son historique de votes, ses thèmes de prédilection et ses positions passées.",
    }


PROFIL_ACTEUR_TOOLS = [
    {
        "name": "build_politician_persona",
        "description": "Construit la persona complète d'un parlementaire : identité, activité législative, votes, réseau d'alliés, spécialités.",
        "input_schema": {
            "type": "object",
            "properties": {
                "acteur_uid": {"type": "string", "description": "UID du parlementaire"},
            },
            "required": ["acteur_uid"],
        },
    },
    {
        "name": "simulate_reaction",
        "description": "Prépare les données pour simuler la réaction d'un acteur politique à une mesure ou argument donné.",
        "input_schema": {
            "type": "object",
            "properties": {
                "acteur_uid": {"type": "string"},
                "measure_description": {"type": "string", "description": "Description de la mesure ou argument à tester"},
            },
            "required": ["acteur_uid", "measure_description"],
        },
    },
]


class ProfilActeurAgent(BaseAgent):
    """Agent de construction et simulation de personas."""

    name = "profil_acteur"
    model = "claude-sonnet-4-5-20241022"
    max_turns = 5

    system_prompt = """Tu es un expert en intelligence politique et en profiling de décideurs.

Ton rôle est de :
1. CONSTRUIRE des profils détaillés de décideurs (politiques, journalistes, dirigeants ONG)
2. ANALYSER leurs positions, leurs votes, leurs interventions passées
3. SIMULER leurs réactions probables à des mesures ou arguments

Quand tu construis un profil :
- Identifie les thèmes de prédilection (où la personne est active)
- Analyse le pattern de vote (conservateur/progressiste, libéral/interventionniste)
- Identifie les alliés et les adversaires
- Note les contradictions potentielles (votes vs discours)

Quand tu simules une réaction :
- Base-toi UNIQUEMENT sur les données factuelles (votes, amendements, déclarations)
- Indique le niveau de confiance de ta prédiction (élevé/moyen/faible)
- Identifie les arguments qui pourraient faire basculer la position
- Suggère l'angle d'approche le plus efficace

Sois honnête sur les limites de la simulation. Ne fabrique pas de certitudes.
"""

    def get_tools(self) -> list[dict]:
        return PROFIL_ACTEUR_TOOLS

    async def execute_tool(self, name: str, input_data: dict, **kwargs) -> dict:
        db = kwargs.get("db")
        if not db:
            return {"error": "Pas de session DB"}

        if name == "build_politician_persona":
            return await build_politician_persona(db, input_data["acteur_uid"])
        elif name == "simulate_reaction":
            return await simulate_reaction(
                db,
                acteur_uid=input_data["acteur_uid"],
                measure_description=input_data["measure_description"],
            )
        else:
            return {"error": f"Outil inconnu: {name}"}

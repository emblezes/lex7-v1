"""Agent Veilleur — detection brute et resume.

Role : surveiller les nouveaux documents, detecter les textes pertinents,
generer un resume en 3 phrases et identifier les secteurs concernes.
"""

from legix.agents.base import BaseAgent
from legix.agents.chat_tools import (
    TOOL_DEFINITIONS,
    TOOL_FUNCTIONS,
)


VEILLEUR_SYSTEM = """Tu es l'agent VEILLEUR de LegiX, plateforme d'intelligence reglementaire.

TON ROLE :
- Surveiller l'activite parlementaire et reglementaire
- Detecter les textes, amendements et signaux pertinents pour le client
- Produire des resumes clairs en 3 phrases maximum
- Identifier les secteurs concernes et le niveau d'urgence

TES REGLES :
1. Commence TOUJOURS par consulter le profil client (get_client_profile)
   pour connaitre ses secteurs d'interet
2. Utilise les outils de recherche pour trouver les documents pertinents
3. Pour chaque texte pertinent, donne : titre, type, resume en 3 phrases,
   secteurs concernes, niveau d'urgence (critique/eleve/moyen/faible)
4. Reponds en francais, de facon concise et factuelle
5. Cite les references (UIDs des textes/amendements)

FORMAT DE SORTIE pour un briefing :
- TITRE du texte/amendement
- TYPE : PION/PRJL/Amendement
- RESUME : 3 phrases max, langage clair
- SECTEURS : liste des secteurs impactes
- URGENCE : critique/eleve/moyen/faible
- REFERENCE : UID du document
"""


class VeilleurAgent(BaseAgent):
    """Agent de veille reglementaire."""

    name = "veilleur"
    system_prompt = VEILLEUR_SYSTEM
    max_turns = 8

    def get_tools(self) -> list[dict]:
        return TOOL_DEFINITIONS

    async def execute_tool(self, name: str, input_data: dict, **kwargs):
        db = kwargs.get("db")
        if not db:
            return {"error": "Session DB non disponible"}

        func = TOOL_FUNCTIONS.get(name)
        if not func:
            return {"error": f"Outil '{name}' inconnu"}

        return await func(db, **input_data)

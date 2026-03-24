"""Agent Brief — analyse consolidee par texte legislatif.

Produit un dossier complet sur un texte pour un client :
resume executif, cartographie des forces, amendements critiques,
contacts cles, plan d'action.
"""

from legix.agents.base import BaseAgent
from legix.agents.chat_tools import TOOL_DEFINITIONS, TOOL_FUNCTIONS


BRIEF_SYSTEM = """Tu es l'agent BRIEF de LegiX. Tu produis des dossiers d'analyse consolidee par texte legislatif pour un client.

TON ROLE :
On te fournit le contexte complet d'un texte : titre, tous les amendements avec auteurs et groupes,
scores d'adoption, signaux faibles, profil detaille du client. Tu dois produire une analyse consolidee.

REGLES CRITIQUES :
1. SPECIFICITE CLIENT : Mentionne toujours les metiers/produits/activites concrets du client impactes
2. AMENDEMENTS CRITIQUES : Selectionne les 3-5 amendements les plus importants parmi :
   - Score adoption le plus eleve
   - Soutien transpartisan (cosignataires de plusieurs groupes)
   - Amendements gouvernementaux
   - Impact financier le plus fort pour le client
3. CARTOGRAPHIE DES FORCES : Pour chaque groupe, analyse sa position PAR RAPPORT AU CLIENT (pas en general)
4. CONTACTS CLES : Les deputes qu'il faut rencontrer — les plus actifs ET les plus susceptibles d'ecouter
5. PLAN D'ACTION : Ordonne par priorite, avec deadlines concretes, adapte au profil du client
6. CHIFFRAGE : Estime toujours un impact financier, meme approximatif

STRUCTURE DE SORTIE (JSON strict, pas de texte avant ou apres) :
{
  "executive_summary": "3-5 phrases markdown sur l'enjeu SPECIFIQUE pour le client",
  "impact_level": "critical|high|medium|low",
  "is_threat": true ou false,
  "exposure_eur": nombre ou null,
  "force_map": [
    {"groupe": "...", "groupe_uid": "...", "nb_amendements": N, "nb_adoptes": N, "position": "pour|contre|mixte", "analyse": "1-2 phrases sur la position de ce groupe vis-a-vis du client"}
  ],
  "critical_amendments": [
    {"uid": "...", "numero": "...", "auteur": "...", "groupe": "...", "resume": "...", "adoption_score": 0.X, "why_critical": "1-2 phrases"}
  ],
  "key_contacts": [
    {"uid": "...", "nom": "...", "groupe": "...", "nb_amendements": N, "taux_adoption": 0.X, "why_relevant": "1-2 phrases sur pourquoi contacter cette personne"}
  ],
  "action_plan": [
    {"priority": 1, "action": "...", "deadline": "...", "who": "qui dans l'entreprise doit agir"}
  ]
}

REPONDS UNIQUEMENT le JSON, sans texte additionnel.
REPONDS EN FRANCAIS.
"""


class BriefAgent(BaseAgent):
    """Agent de production de dossiers texte consolides."""

    name = "brief"
    system_prompt = BRIEF_SYSTEM
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

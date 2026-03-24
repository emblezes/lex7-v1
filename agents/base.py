"""BaseAgent — pattern Claude tool use pour les agents LegiX.

Chaque agent est un wrapper autour de l'API Anthropic avec :
- Un system prompt specialise
- Des outils (fonctions) qu'il peut appeler
- Une boucle de conversation avec tool use
"""

import json
import logging
from typing import Any

import anthropic

from legix.core.config import settings

logger = logging.getLogger(__name__)


class BaseAgent:
    """Agent conversationnel Claude avec tool use."""

    name: str = "agent"
    system_prompt: str = "Tu es un assistant."
    model: str = ""
    max_turns: int = 5  # Nombre max de boucles tool use

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        if not self.model:
            self.model = settings.enrichment_model

    def get_tools(self) -> list[dict]:
        """Retourne les definitions d'outils disponibles pour cet agent."""
        return []

    async def execute_tool(self, name: str, input_data: dict, **kwargs) -> Any:
        """Execute un outil par son nom. A surcharger par sous-classe."""
        raise NotImplementedError(f"Outil {name} non implemente")

    def _build_system_prompt(self, profile: dict | None = None) -> str:
        """Construit le system prompt, enrichi du contexte client si disponible."""
        base = self.system_prompt
        if not profile or "error" in profile:
            return base

        # Données de base
        name = profile.get('name', 'Client')
        sectors = ', '.join(profile.get('sectors', []))
        context_note = profile.get('context_note', '')
        description = profile.get('description', '')

        # Données métier (générées à l'onboarding par Claude)
        business_lines = ', '.join(profile.get('business_lines', []))
        products = ', '.join(profile.get('products', []))
        regulatory_focus = ', '.join(profile.get('regulatory_focus', []))
        monitoring = profile.get('monitoring_explanation', '')
        key_risks = profile.get('key_risks', [])
        key_opportunities = profile.get('key_opportunities', [])

        # Données publiques (API SIRENE)
        siren = profile.get('siren', '')
        code_naf = profile.get('code_naf', '')
        categorie = profile.get('categorie_entreprise', '')
        ca = profile.get('chiffre_affaires')
        effectifs = profile.get('effectifs', '')
        siege = profile.get('siege_social', '')

        # Construire le bloc financier si disponible
        financial_block = ""
        if ca:
            ca_fmt = f"{ca:,.0f}".replace(",", " ")
            financial_block = f"\nChiffre d'affaires : {ca_fmt} EUR"
        if effectifs:
            financial_block += f"\nEffectifs : {effectifs}"

        context = f"""

--- PROFIL CLIENT COMPLET ---
Entreprise : {name}
{f"Description : {description}" if description else ""}
{f"Note strategique : {context_note}" if context_note else ""}

ACTIVITE :
- Secteurs surveilles : {sectors}
{f"- Divisions / lignes metiers : {business_lines}" if business_lines else ""}
{f"- Produits et services cles : {products}" if products else ""}
{f"- Enjeux reglementaires prioritaires : {regulatory_focus}" if regulatory_focus else ""}

DONNEES ENTREPRISE :
{f"- SIREN : {siren}" if siren else ""}{f" | NAF : {code_naf}" if code_naf else ""}{f" | Categorie : {categorie}" if categorie else ""}{financial_block}{f"  | Siege : {siege}" if siege else ""}

{f"PERIMETRE DE VEILLE : {monitoring}" if monitoring else ""}

{f"RISQUES REGLEMENTAIRES IDENTIFIES :" if key_risks else ""}
{chr(10).join(f"- {r}" for r in key_risks) if key_risks else ""}

{f"OPPORTUNITES REGLEMENTAIRES :" if key_opportunities else ""}
{chr(10).join(f"- {o}" for o in key_opportunities) if key_opportunities else ""}

REGLE ABSOLUE : Toute analyse DOIT etre specifique a {name}.
- Cite les divisions ({business_lines or 'non renseignees'}) et produits ({products or 'non renseignes'}) concernes
- Evalue l'impact par rapport aux enjeux reglementaires ({regulatory_focus or 'non renseignes'})
- Ne produis JAMAIS d'analyse generique qui pourrait s'appliquer a n'importe quelle entreprise

TU AS ACCES A LA MEMOIRE LEGISLATIVE :
- analyze_depute : historique complet d'un acteur (taux adoption, themes, cosignataires)
- analyze_groupe : comportement d'un groupe politique (adoption par theme)
- analyze_texte_dynamics : qui amende un texte, quels groupes, tendances
- get_amendement_network : reseau de soutien d'un amendement

QUAND TU RAISONNES SUR UN DOCUMENT :
1. Identifie les acteurs impliques — appelle analyze_depute pour connaitre leur historique
2. Verifie le groupe — appelle analyze_groupe pour savoir si le groupe soutient ce type de texte
3. Regarde les cosignataires — appelle get_amendement_network pour detecter convergences
4. Evalue la probabilite d'adoption avec ces elements
5. Determine menace ou opportunite pour {name} en fonction de ses enjeux specifiques
6. Recommande des actions concretes (qui contacter, pourquoi)

NE SUIS PAS UN CHEMIN FIXE. Raisonne. Adapte ton analyse a ce que tu decouvres.
"""
        return base + context

    async def run(self, user_message: str, **kwargs) -> str:
        """Boucle de conversation complete avec tool use.

        Args:
            user_message: Message de l'utilisateur.
            **kwargs: db (AsyncSession), profile_id (int), profile (dict).

        Returns:
            La reponse finale de l'agent (texte).
        """
        # Charger le profil client si profile_id fourni
        profile = kwargs.get("profile")
        if not profile and (profile_id := kwargs.get("profile_id")):
            db = kwargs.get("db")
            if db:
                from legix.agents.chat_tools import get_client_profile
                profile = await get_client_profile(db, profile_id=profile_id)

        system = self._build_system_prompt(profile)

        messages = [{"role": "user", "content": user_message}]
        tools = self.get_tools()

        for turn in range(self.max_turns):
            # Appel Claude
            create_kwargs = {
                "model": self.model,
                "max_tokens": 4096,
                "system": system,
                "messages": messages,
            }
            if tools:
                create_kwargs["tools"] = tools

            response = self.client.messages.create(**create_kwargs)

            # Si pas de tool use, on a la reponse finale
            if response.stop_reason == "end_turn" or response.stop_reason != "tool_use":
                # Extraire le texte de la reponse
                text_parts = [
                    block.text for block in response.content if block.type == "text"
                ]
                return "\n".join(text_parts) if text_parts else ""

            # Traiter les tool uses
            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            tool_results = []
            for block in assistant_content:
                if block.type == "tool_use":
                    logger.info(
                        "[%s] Tool call: %s(%s)",
                        self.name,
                        block.name,
                        json.dumps(block.input, ensure_ascii=False)[:200],
                    )
                    try:
                        result = await self.execute_tool(
                            block.name, block.input, **kwargs
                        )
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": json.dumps(result, ensure_ascii=False, default=str),
                            }
                        )
                    except Exception as e:
                        logger.error("[%s] Tool error %s: %s", self.name, block.name, e)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": json.dumps({"error": str(e)}),
                                "is_error": True,
                            }
                        )

            messages.append({"role": "user", "content": tool_results})

        # Limite de tours atteinte
        return "Je n'ai pas pu terminer l'analyse dans le nombre de tours imparti."

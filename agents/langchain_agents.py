"""Agents LangChain/LangGraph — 9 agents specialises pour affaires publiques.

Tout est trace dans LangSmith automatiquement.
Usage :
    from legix.agents.langchain_agents import veilleur, analyste, stratege, anticipateur

    # Chat avec le veilleur
    result = veilleur.invoke({"messages": [("user", "Quels textes sur l'energie cette semaine ?")]})
    print(result["messages"][-1].content)

    # Chat avec l'anticipateur
    result = anticipateur.invoke({"messages": [("user", "Quels rapports de think tanks cette semaine ?")]})
"""

import os

from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent

from legix.agents.langchain_tools import (
    ANALYSTE_TOOLS,
    ANTICIPATEUR_TOOLS,
    CARTOGRAPHE_TOOLS,
    PLANIFICATEUR_TOOLS,
    PROFIL_ACTEUR_TOOLS,
    RIPOSTE_TOOLS,
    STRATEGE_TOOLS,
    VEILLEUR_TOOLS,
)

# ── Config LangSmith (tracing automatique) ───────────────────────────

os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
os.environ.setdefault("LANGCHAIN_PROJECT", "legix")


# ── System prompts ───────────────────────────────────────────────────

VEILLEUR_PROMPT = """Tu es l'agent VEILLEUR de LegiX, plateforme d'intelligence reglementaire.

TON ROLE :
- Surveiller l'activite parlementaire et reglementaire francaise
- Detecter les textes, amendements et signaux pertinents
- Produire des resumes clairs et factuels
- Identifier les secteurs concernes et le niveau d'urgence

TES REGLES :
1. Utilise tes outils de recherche pour trouver les documents pertinents
2. Pour chaque texte pertinent, donne : titre, type, resume, secteurs, urgence
3. Reponds en francais, de facon concise et factuelle
4. Cite les references (UIDs des textes/amendements)
5. Si on te demande un briefing, commence par consulter le profil client

FORMAT pour un briefing :
- TITRE du texte/amendement
- TYPE : Proposition de loi / Projet de loi / Amendement
- RESUME : 3 phrases max
- SECTEURS impactes
- URGENCE : critique / eleve / moyen / faible
- REFERENCE : UID du document
"""

ANALYSTE_PROMPT = """Tu es l'agent ANALYSTE de LegiX, plateforme d'intelligence reglementaire.

TON ROLE :
- Analyser en profondeur l'impact d'un texte ou amendement sur une entreprise
- Produire des analyses SPECIFIQUES, pas generiques
- Identifier quels metiers, produits et activites sont impactes
- Fournir une vision prospective et des recommandations actionnables

PRINCIPES :
1. SPECIFICITE : cite les divisions/metiers/produits concrets
2. DIFFERENCIATION : un meme texte impacte differemment les metiers d'une entreprise
3. PROSPECTIVE : anticipe l'evolution du texte et ses consequences
4. CHIFFRAGE : estime toujours un impact financier, meme approximatif

METHODE :
1. Consulte le profil client pour connaitre ses enjeux
2. Identifie les metiers/produits concernes
3. Investigue les acteurs cles avec profil_depute et analyser_groupe
4. Evalue la probabilite d'adoption
5. Produis une analyse specifique par metier impacte
6. Recommande des actions concretes

Reponds toujours en francais.
"""

STRATEGE_PROMPT = """Tu es l'agent STRATEGE de LegiX, plateforme d'intelligence reglementaire.

TON ROLE :
- Analyser le paysage politique autour d'un texte ou amendement
- Identifier les allies potentiels et opposants parmi les parlementaires
- Recommander un plan d'action d'affaires publiques concret
- Evaluer le rapport de force politique et la fenetre d'opportunite

METHODE :
1. Consulte le profil client pour connaitre ses enjeux
2. Utilise profil_depute et analyser_groupe pour comprendre les positions
3. Utilise reseau_amendement pour detecter les convergences transpartisanes
4. Identifie les rapporteurs et presidents de commission

FORMAT DE SORTIE :
- DIAGNOSTIC : resume de la situation politique (2-3 phrases)
- RAPPORT DE FORCE : qui soutient, qui s'oppose, qui est indecis
- FENETRE D'ACTION : quand agir et pourquoi maintenant
- PLAN D'ACTION :
  1. Interlocuteurs prioritaires (nom, groupe, pourquoi)
  2. Messages cles a porter
  3. Alliances possibles
  4. Risques a surveiller
- PROBABILITE DE SUCCES : estimation argumentee

Sois SPECIFIQUE (noms, groupes), ACTIONNABLE et HONNETE.
Reponds toujours en francais.
"""


# ── Creation des agents ──────────────────────────────────────────────

def create_veilleur(model: str = "claude-sonnet-4-20250514"):
    """Cree l'agent Veilleur (veille parlementaire)."""
    llm = ChatAnthropic(model=model, max_tokens=4096)
    return create_react_agent(
        llm,
        VEILLEUR_TOOLS,
        prompt=VEILLEUR_PROMPT,
    )


def create_analyste(model: str = "claude-sonnet-4-20250514"):
    """Cree l'agent Analyste (impact reglementaire)."""
    llm = ChatAnthropic(model=model, max_tokens=4096)
    return create_react_agent(
        llm,
        ANALYSTE_TOOLS,
        prompt=ANALYSTE_PROMPT,
    )


def create_stratege(model: str = "claude-opus-4-20250514"):
    """Cree l'agent Stratege (affaires publiques). Utilise Opus par defaut."""
    llm = ChatAnthropic(model=model, max_tokens=4096)
    return create_react_agent(
        llm,
        STRATEGE_TOOLS,
        prompt=STRATEGE_PROMPT,
    )


# ── Agents affaires publiques (6 nouveaux) ────────────────────────

ANTICIPATEUR_PROMPT = """Tu es l'agent ANTICIPATEUR de LegiX, plateforme d'intelligence reglementaire.

TON ROLE — LE PLUS CRITIQUE :
- Detecter les signaux PRE-LEGISLATIFS : rapports de think tanks, inspections generales, etudes
- Mapper le pipeline : Rapport -> Recommandation -> Proposition de loi -> Debat -> Loi
- Alerter le client AVANT que le debat parlementaire ne commence
- Evaluer la probabilite qu'un rapport devienne une loi

METHODE :
1. Recherche les rapports recents (think tanks, Cour des Comptes, IGF, IGAS, France Strategie)
2. Identifie les recommandations concretes qui pourraient devenir des mesures legislatives
3. Evalue la probabilite : auteur influent ? sujet prioritaire du gouvernement ?
4. Estime le timeline : dans 6 mois ? 1-2 ans ?
5. Identifie les acteurs qui pourraient porter ces recommandations
6. Evalue l'impact pour le client : menace ou opportunite ?

Plus l'alerte est precoce (stade rapport), plus le client a de marges de manoeuvre.
Reponds en francais, sois concret et actionnable.
"""

CARTOGRAPHE_PROMPT = """Tu es l'agent CARTOGRAPHE de LegiX, expert en mapping des parties prenantes.

TON ROLE :
- Construire la carte des acteurs sur un dossier reglementaire
- Identifier qui est pour, qui est contre, qui est indecis
- Scorer l'influence et la pertinence de chaque acteur
- Recommander les contacts prioritaires et l'angle d'approche

Sois SPECIFIQUE (noms, fonctions, groupes). Reponds en francais.
"""

PROFIL_ACTEUR_PROMPT = """Tu es l'agent PROFIL ACTEUR de LegiX, expert en intelligence politique.

TON ROLE :
- Construire des profils detailles de decideurs (politiques, journalistes, ONG)
- Analyser positions, votes, interventions passees
- Simuler les reactions probables a des mesures ou arguments

Base-toi UNIQUEMENT sur les donnees factuelles. Indique le niveau de confiance.
Reponds en francais.
"""

RIPOSTE_PROMPT = """Tu es l'agent RIPOSTE de LegiX, expert en communication de crise.

TON ROLE :
- Detecter les articles de presse negatifs ou critiques
- Preparer des reponses adaptees (droit de reponse, communique, elements de langage)
- Ne JAMAIS nier les faits verifiables, recadrer positivement

Pour chaque article negatif : risque (1-5), recommandation (repondre/ne pas repondre), draft si necessaire.
Reponds en francais.
"""

PLANIFICATEUR_PROMPT = """Tu es l'agent PLANIFICATEUR de LegiX, directeur PA experimente.

TON ROLE :
- Planifier la strategie PA du client : dossiers prioritaires, fenetres d'opportunite
- Produire des feuilles de route trimestrielles
- Raisonner en urgence, impact, faisabilite, timing

Sois concret et realiste. Reponds en francais.
"""


def create_anticipateur(model: str = "claude-sonnet-4-20250514"):
    """Cree l'agent Anticipateur (veille pre-legislative)."""
    llm = ChatAnthropic(model=model, max_tokens=4096)
    return create_react_agent(llm, ANTICIPATEUR_TOOLS, prompt=ANTICIPATEUR_PROMPT)


def create_cartographe(model: str = "claude-sonnet-4-20250514"):
    """Cree l'agent Cartographe (mapping parties prenantes)."""
    llm = ChatAnthropic(model=model, max_tokens=4096)
    return create_react_agent(llm, CARTOGRAPHE_TOOLS, prompt=CARTOGRAPHE_PROMPT)


def create_profil_acteur(model: str = "claude-sonnet-4-20250514"):
    """Cree l'agent Profil Acteur (personas + simulation)."""
    llm = ChatAnthropic(model=model, max_tokens=4096)
    return create_react_agent(llm, PROFIL_ACTEUR_TOOLS, prompt=PROFIL_ACTEUR_PROMPT)


def create_riposte(model: str = "claude-sonnet-4-20250514"):
    """Cree l'agent Riposte (communication de crise)."""
    llm = ChatAnthropic(model=model, max_tokens=4096)
    return create_react_agent(llm, RIPOSTE_TOOLS, prompt=RIPOSTE_PROMPT)


def create_planificateur(model: str = "claude-sonnet-4-20250514"):
    """Cree l'agent Planificateur (strategie PA)."""
    llm = ChatAnthropic(model=model, max_tokens=4096)
    return create_react_agent(llm, PLANIFICATEUR_TOOLS, prompt=PLANIFICATEUR_PROMPT)


# ── Instances par defaut ─────────────────────────────────────────────

veilleur = create_veilleur()
analyste = create_analyste()
stratege = create_stratege()
anticipateur = create_anticipateur()
cartographe = create_cartographe()
profil_acteur = create_profil_acteur()
riposte = create_riposte()
planificateur = create_planificateur()


# ── Registre et utilitaires ──────────────────────────────────────────

AGENT_REGISTRY = {
    "veilleur": veilleur,
    "analyste": analyste,
    "stratege": stratege,
    "anticipateur": anticipateur,
    "cartographe": cartographe,
    "profil_acteur": profil_acteur,
    "riposte": riposte,
    "planificateur": planificateur,
}


def chat(agent_name: str, message: str) -> str:
    """Chatter avec un agent par nom.

    Args:
        agent_name: veilleur, analyste, stratege, anticipateur,
                    cartographe, profil_acteur, riposte, planificateur
        message: La question de l'utilisateur
    """
    agent = AGENT_REGISTRY.get(agent_name)
    if not agent:
        return f"Agent inconnu: {agent_name}. Choix: {', '.join(AGENT_REGISTRY.keys())}"

    result = agent.invoke({"messages": [("user", message)]})
    return result["messages"][-1].content


def list_agents() -> list[dict]:
    """Liste tous les agents disponibles."""
    return [
        {"name": "veilleur", "role": "Veille parlementaire et reglementaire"},
        {"name": "analyste", "role": "Analyse d'impact reglementaire"},
        {"name": "stratege", "role": "Strategie d'affaires publiques"},
        {"name": "anticipateur", "role": "Veille pre-legislative (think tanks, inspections)"},
        {"name": "cartographe", "role": "Cartographie des parties prenantes"},
        {"name": "profil_acteur", "role": "Personas politiques et simulation de reactions"},
        {"name": "riposte", "role": "Communication de crise et riposte presse"},
        {"name": "planificateur", "role": "Planification strategique PA"},
    ]

"""LangChain tools — wrappent les fonctions chat_tools existantes.

Chaque tool est une fonction sync qui ouvre une session DB async,
appelle la fonction existante, et retourne le resultat en JSON.
Compatible LangChain + visible dans LangSmith.
"""

import asyncio
import json
from typing import Optional

from langchain_core.tools import tool

from legix.core.database import async_session


def _run_async(coro):
    """Execute une coroutine async depuis un contexte sync."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # On est deja dans une boucle async (FastAPI, etc.)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


async def _call(func_name: str, **kwargs) -> str:
    """Ouvre une session DB, appelle la fonction chat_tools, retourne JSON."""
    from legix.agents.chat_tools import TOOL_FUNCTIONS

    func = TOOL_FUNCTIONS[func_name]
    async with async_session() as db:
        result = await func(db, **kwargs)
    return json.dumps(result, ensure_ascii=False, default=str)


# ── Agent Veilleur : 6 tools ────────────────────────────────────────


@tool
def rechercher_documents(query: str, limit: int = 10) -> str:
    """Recherche full-text sur tous les documents parlementaires
    (textes de loi, amendements, reunions).
    Utilise pour trouver des documents par mots-cles."""
    return _run_async(_call("search_documents", query=query, limit=limit))


@tool
def lister_textes(
    theme: Optional[str] = None,
    type_code: Optional[str] = None,
    limit: int = 10,
) -> str:
    """Recupere des textes legislatifs avec filtres par theme et type.
    type_code: PION (proposition de loi) ou PRJL (projet de loi).
    theme: sante, environnement/climat, fiscalite, etc."""
    kwargs = {"limit": limit}
    if theme:
        kwargs["theme"] = theme
    if type_code:
        kwargs["type_code"] = type_code
    return _run_async(_call("get_textes", **kwargs))


@tool
def lister_amendements(
    groupe: Optional[str] = None,
    theme: Optional[str] = None,
    sort: Optional[str] = None,
    limit: int = 10,
) -> str:
    """Recupere des amendements avec filtres.
    groupe: nom du groupe politique (Renaissance, RN, LFI...).
    sort: Adopte, Rejete, Retire.
    theme: sante, fiscalite, etc."""
    kwargs = {"limit": limit}
    if groupe:
        kwargs["groupe"] = groupe
    if theme:
        kwargs["theme"] = theme
    if sort:
        kwargs["sort"] = sort
    return _run_async(_call("get_amendements", **kwargs))


@tool
def lister_reunions(theme: Optional[str] = None, limit: int = 10) -> str:
    """Recupere les reunions de commissions parlementaires.
    Filtre optionnel par theme."""
    kwargs = {"limit": limit}
    if theme:
        kwargs["theme"] = theme
    return _run_async(_call("get_reunions", **kwargs))


@tool
def statistiques_globales() -> str:
    """Statistiques globales de la base parlementaire :
    nombre de textes, amendements, reunions, acteurs, organes."""
    return _run_async(_call("get_stats"))


@tool
def signaux_faibles(
    theme: Optional[str] = None,
    severity: Optional[str] = None,
    days: int = 7,
) -> str:
    """Signaux faibles recents : convergences transpartisanes,
    pics d'amendements, themes emergents, accelerations gouvernementales.
    severity: medium, high, critical."""
    kwargs = {"days": days}
    if theme:
        kwargs["theme"] = theme
    if severity:
        kwargs["severity"] = severity
    return _run_async(_call("get_signals", **kwargs))


@tool
def contexte_strategique(sector: str, days: int = 30) -> str:
    """Vue 360 d'un secteur : textes actifs, acteurs cles,
    taux d'adoption, signaux faibles. Ideal pour un briefing sectoriel."""
    return _run_async(_call("get_strategic_context", sector=sector, days=days))


# ── Agent Analyste : 5 tools ────────────────────────────────────────


@tool
def profil_depute(uid_or_name: str) -> str:
    """Intelligence complete d'un depute : identite, groupe, taux d'adoption
    global et par theme, cosignataires frequents, activite recente (30j).
    Accepte un UID (ex: PA721900) ou un nom (ex: 'Dupont')."""
    return _run_async(_call("analyze_depute", uid_or_name=uid_or_name))


@tool
def analyser_groupe(uid_or_name: str, theme: Optional[str] = None) -> str:
    """Intelligence d'un groupe politique : taux d'adoption global ou par theme,
    deputes les plus actifs, themes principaux.
    Accepte un UID (ex: PO730964) ou un nom (ex: 'Renaissance', 'RN', 'LFI')."""
    kwargs = {"uid_or_name": uid_or_name}
    if theme:
        kwargs["theme"] = theme
    return _run_async(_call("analyze_groupe", **kwargs))


@tool
def dynamique_texte(texte_uid: str) -> str:
    """Dynamique legislative autour d'un texte : nombre d'amendements,
    groupes impliques avec taux d'adoption, deputes actifs,
    amendements gouvernementaux, themes. Pour comprendre les forces en jeu."""
    return _run_async(_call("analyze_texte_dynamics", texte_uid=texte_uid))


@tool
def reseau_amendement(amendement_uid: str) -> str:
    """Reseau complet d'un amendement : auteur avec profil intelligence,
    cosignataires, convergence transpartisane, score d'adoption, texte parent.
    Pour evaluer la force et les chances d'un amendement."""
    return _run_async(_call("get_amendement_network", amendement_uid=amendement_uid))


@tool
def profil_client(profile_id: Optional[int] = None) -> str:
    """Profil client actif avec secteurs, metiers, produits,
    enjeux reglementaires, risques et opportunites identifies."""
    kwargs = {}
    if profile_id:
        kwargs["profile_id"] = profile_id
    return _run_async(_call("get_client_profile", **kwargs))


# ── Agent Anticipateur : 4 tools ──────────────────────────────────


@tool
def rechercher_rapports_anticipation(
    theme: Optional[str] = None,
    source_type: Optional[str] = None,
    source_name: Optional[str] = None,
    limit: int = 20,
) -> str:
    """Recherche les rapports d'anticipation (think tanks, inspections, etudes).
    source_type: think_tank, rapport_inspection, academic, consultation.
    Retourne titre, source, resume, recommandations, probabilite legislative."""
    async def _search():
        from legix.agents.anticipateur import search_anticipation_reports
        async with async_session() as db:
            return await search_anticipation_reports(
                db, theme=theme, source_type=source_type,
                source_name=source_name, limit=limit,
            )
    result = _run_async(_search())
    return json.dumps(result, ensure_ascii=False, default=str)


@tool
def pipeline_rapport_loi(theme: str) -> str:
    """Cartographie le pipeline rapport-loi pour un theme :
    montre les rapports par stade (rapport, recommandation, proposition,
    debat, loi) et les textes legislatifs associes."""
    async def _map():
        from legix.agents.anticipateur import map_policy_pipeline
        async with async_session() as db:
            return await map_policy_pipeline(db, theme=theme)
    result = _run_async(_map())
    return json.dumps(result, ensure_ascii=False, default=str)


@tool
def signaux_anticipation(days: int = 30) -> str:
    """Detecte les signaux d'anticipation recents : rapports dont les themes
    correspondent aux secteurs surveilles. Pre-legislatif."""
    async def _detect():
        from legix.agents.anticipateur import detect_early_signals
        async with async_session() as db:
            return await detect_early_signals(db, days=days)
    result = _run_async(_detect())
    return json.dumps(result, ensure_ascii=False, default=str)


# ── Agent Cartographe : 2 tools ──────────────────────────────────


@tool
def cartographie_stakeholders(texte_uid: str) -> str:
    """Construit la carte complete des stakeholders pour un texte legislatif :
    acteurs cles, groupes politiques, positions, scores d'influence, taux d'adoption."""
    async def _map():
        from legix.agents.cartographe import build_stakeholder_map
        async with async_session() as db:
            return await build_stakeholder_map(db, texte_uid=texte_uid)
    result = _run_async(_map())
    return json.dumps(result, ensure_ascii=False, default=str)


@tool
def rechercher_stakeholders(
    stakeholder_type: str,
    theme: Optional[str] = None,
    limit: int = 20,
) -> str:
    """Recherche des stakeholders par type et theme.
    stakeholder_type: depute, senateur, journaliste, ong, federation, collaborateur, regulateur."""
    async def _search():
        from legix.agents.cartographe import find_stakeholders_by_type
        async with async_session() as db:
            return await find_stakeholders_by_type(
                db, stakeholder_type=stakeholder_type, theme=theme, limit=limit,
            )
    result = _run_async(_search())
    return json.dumps(result, ensure_ascii=False, default=str)


# ── Agent ProfilActeur : 2 tools ─────────────────────────────────


@tool
def persona_parlementaire(acteur_uid: str) -> str:
    """Construit la persona complete d'un parlementaire : identite, activite
    legislative, votes nominatifs, reseau d'allies, specialites, taux d'adoption par theme."""
    async def _build():
        from legix.agents.profil_acteur import build_politician_persona
        async with async_session() as db:
            return await build_politician_persona(db, acteur_uid=acteur_uid)
    result = _run_async(_build())
    return json.dumps(result, ensure_ascii=False, default=str)


@tool
def simuler_reaction(acteur_uid: str, measure_description: str) -> str:
    """Prepare les donnees pour simuler la reaction d'un acteur politique
    a une mesure ou argument donne. Retourne le profil complet + contexte de simulation."""
    async def _sim():
        from legix.agents.profil_acteur import simulate_reaction
        async with async_session() as db:
            return await simulate_reaction(
                db, acteur_uid=acteur_uid,
                measure_description=measure_description,
            )
    result = _run_async(_sim())
    return json.dumps(result, ensure_ascii=False, default=str)


# ── Agent Riposte : 2 tools ─────────────────────────────────────


@tool
def mentions_presse(days: int = 7) -> str:
    """Surveille les mentions presse recentes du client.
    Retourne les articles avec sentiment, urgence de reponse et statut."""
    async def _monitor():
        from legix.agents.riposte import monitor_press_mentions
        async with async_session() as db:
            # profile_id sera injecte par le contexte
            return await monitor_press_mentions(db, profile_id=1, days=days)
    result = _run_async(_monitor())
    return json.dumps(result, ensure_ascii=False, default=str)


@tool
def profil_journaliste(journalist_name: str) -> str:
    """Recupere le profil d'un journaliste : themes couverts,
    positions passees, contact, media."""
    async def _profile():
        from legix.agents.riposte import get_journalist_profile
        async with async_session() as db:
            return await get_journalist_profile(db, journalist_name=journalist_name)
    result = _run_async(_profile())
    return json.dumps(result, ensure_ascii=False, default=str)


# ── Agent Planificateur : 3 tools ────────────────────────────────


@tool
def calendrier_legislatif(days: int = 30) -> str:
    """Calendrier legislatif : reunions de commission et seances a venir."""
    async def _cal():
        from legix.agents.planificateur import get_legislative_calendar
        async with async_session() as db:
            return await get_legislative_calendar(db, days=days)
    result = _run_async(_cal())
    return json.dumps(result, ensure_ascii=False, default=str)


@tool
def prioriser_dossiers() -> str:
    """Priorise les dossiers suivis par le client par urgence et impact.
    Retourne un score de priorite pour chaque dossier."""
    async def _prio():
        from legix.agents.planificateur import prioritize_dossiers
        async with async_session() as db:
            return await prioritize_dossiers(db, profile_id=1)
    result = _run_async(_prio())
    return json.dumps(result, ensure_ascii=False, default=str)


@tool
def fenetres_opportunite(days: int = 90) -> str:
    """Identifie les fenetres d'opportunite dans le calendrier legislatif
    et les signaux d'anticipation. Quand et comment agir."""
    async def _windows():
        from legix.agents.planificateur import identify_windows
        async with async_session() as db:
            return await identify_windows(db, profile_id=1, days=days)
    result = _run_async(_windows())
    return json.dumps(result, ensure_ascii=False, default=str)


# ── Import RAG tools ─────────────────────────────────────────────

from legix.knowledge.rag_tool import rechercher_knowledge_base, lister_documents_client


# ── Listes par agent ────────────────────────────────────────────────

VEILLEUR_TOOLS = [
    rechercher_documents,
    lister_textes,
    lister_amendements,
    lister_reunions,
    statistiques_globales,
    signaux_faibles,
    contexte_strategique,
    profil_client,
    signaux_anticipation,  # NOUVEAU : veille anticipation
    rechercher_knowledge_base,  # RAG
    lister_documents_client,  # RAG
]

ANALYSTE_TOOLS = [
    profil_depute,
    analyser_groupe,
    dynamique_texte,
    reseau_amendement,
    profil_client,
    rechercher_documents,
    lister_textes,
    lister_amendements,
    signaux_faibles,
    contexte_strategique,
    rechercher_rapports_anticipation,  # NOUVEAU
    pipeline_rapport_loi,  # NOUVEAU
    rechercher_knowledge_base,  # RAG
]

STRATEGE_TOOLS = [
    profil_depute,
    analyser_groupe,
    dynamique_texte,
    reseau_amendement,
    profil_client,
    rechercher_documents,
    lister_textes,
    lister_amendements,
    lister_reunions,
    signaux_faibles,
    contexte_strategique,
    cartographie_stakeholders,  # NOUVEAU
    rechercher_stakeholders,  # NOUVEAU
    rechercher_knowledge_base,  # RAG
]

ANTICIPATEUR_TOOLS = [
    rechercher_rapports_anticipation,
    pipeline_rapport_loi,
    signaux_anticipation,
    rechercher_documents,
    lister_textes,
    signaux_faibles,
    contexte_strategique,
    profil_client,
]

CARTOGRAPHE_TOOLS = [
    cartographie_stakeholders,
    rechercher_stakeholders,
    profil_depute,
    analyser_groupe,
    dynamique_texte,
    reseau_amendement,
    profil_client,
]

PROFIL_ACTEUR_TOOLS = [
    persona_parlementaire,
    simuler_reaction,
    profil_depute,
    analyser_groupe,
    reseau_amendement,
    profil_client,
]

RIPOSTE_TOOLS = [
    mentions_presse,
    profil_journaliste,
    rechercher_stakeholders,
    profil_client,
    rechercher_documents,
]

PLANIFICATEUR_TOOLS = [
    calendrier_legislatif,
    prioriser_dossiers,
    fenetres_opportunite,
    signaux_anticipation,
    rechercher_rapports_anticipation,
    profil_client,
    lister_reunions,
    contexte_strategique,
]

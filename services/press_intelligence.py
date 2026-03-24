"""Intelligence presse — lie les articles aux textes suivis et aux acteurs.

Quand un article de presse ou une publication de regulateur est enrichi,
ce service verifie s'il est pertinent pour un texte suivi :
1. L'article mentionne un parlementaire actif sur un texte suivi
2. L'article porte sur une thematique d'un texte suivi
3. L'article mentionne une entreprise cliente

Si les deux conditions (entite + thematique) sont remplies,
l'article est rattache au TexteFollowUp via le change_log.
"""

import json
import logging
import re
import unicodedata
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.models import (
    Acteur,
    Amendement,
    ClientProfile,
    Texte,
    TexteBrief,
    TexteFollowUp,
)

logger = logging.getLogger(__name__)


def _normalize(s: str) -> str:
    """Normalise un nom pour comparaison floue."""
    s = unicodedata.normalize("NFKD", s.lower())
    s = s.encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z ]+", "", s).strip()
    return s


def _parse_json_safe(val) -> list | dict:
    if not val:
        return []
    try:
        return json.loads(val) if isinstance(val, str) else val
    except (json.JSONDecodeError, TypeError):
        return []


async def get_watched_context(db: AsyncSession) -> dict:
    """Construit le contexte de surveillance : quels parlementaires et themes on suit.

    Retourne :
    {
        "acteurs_par_texte": {texte_uid: {nom_normalise: acteur_uid}},
        "themes_par_texte": {texte_uid: [themes]},
        "followups": {texte_uid: {profile_id: TexteFollowUp}},
        "clients_par_nom": {nom_normalise: profile_id},
    }
    """
    # Charger tous les followups actifs
    result = await db.execute(
        select(TexteFollowUp).where(TexteFollowUp.status == "watching")
    )
    followups = result.scalars().all()

    if not followups:
        return {"acteurs_par_texte": {}, "themes_par_texte": {}, "followups": {}, "clients_par_nom": {}}

    # Index followups par texte_uid
    fu_index: dict[str, dict[int, TexteFollowUp]] = {}
    for fu in followups:
        fu_index.setdefault(fu.texte_uid, {})[fu.profile_id] = fu

    # Pour chaque texte suivi, trouver les acteurs actifs (auteurs d'amendements)
    acteurs_par_texte: dict[str, dict[str, str]] = {}
    themes_par_texte: dict[str, list[str]] = {}

    for texte_uid in fu_index:
        # Themes du texte
        texte = await db.get(Texte, texte_uid)
        if texte and texte.themes:
            themes_par_texte[texte_uid] = _parse_json_safe(texte.themes)

        # Acteurs actifs sur ce texte (auteurs d'amendements)
        amdt_result = await db.execute(
            select(Amendement.auteur_ref, Amendement.auteur_nom)
            .where(Amendement.texte_ref == texte_uid)
            .distinct()
        )
        acteurs = {}
        for auteur_ref, auteur_nom in amdt_result:
            if auteur_ref:
                acteur = await db.get(Acteur, auteur_ref)
                if acteur:
                    nom_norm = _normalize(f"{acteur.prenom} {acteur.nom}")
                    acteurs[nom_norm] = auteur_ref
                    acteurs[_normalize(acteur.nom)] = auteur_ref
            if auteur_nom:
                acteurs[_normalize(auteur_nom)] = auteur_ref or auteur_nom
        acteurs_par_texte[texte_uid] = acteurs

    # Index clients par nom
    result = await db.execute(
        select(ClientProfile).where(ClientProfile.is_active.is_(True))
    )
    clients = result.scalars().all()
    clients_par_nom = {}
    for c in clients:
        clients_par_nom[_normalize(c.name)] = c.id

    return {
        "acteurs_par_texte": acteurs_par_texte,
        "themes_par_texte": themes_par_texte,
        "followups": fu_index,
        "clients_par_nom": clients_par_nom,
    }


async def match_article_to_followups(
    db: AsyncSession,
    article: Texte,
    context: dict,
) -> list[dict]:
    """Verifie si un article enrichi est pertinent pour des textes suivis.

    Retourne une liste de matches :
    [{"texte_uid": ..., "profile_id": ..., "reason": ..., "entities_matched": [...]}]
    """
    if not article.themes:
        return []

    article_themes = set(_parse_json_safe(article.themes))

    # Entites extraites de l'article (stockees dans auteur_texte pour presse/regulateur)
    entities = {}
    if article.source in ("presse", "regulateur") and article.auteur_texte:
        try:
            parsed = json.loads(article.auteur_texte)
            if isinstance(parsed, dict) and "parlementaires" in parsed:
                entities = parsed
        except (json.JSONDecodeError, TypeError):
            pass

    parlementaires_article = [_normalize(p) for p in entities.get("parlementaires", [])]
    entreprises_article = [_normalize(e) for e in entities.get("entreprises", [])]

    matches = []

    for texte_uid, texte_themes in context["themes_par_texte"].items():
        # Condition 1 : thematique commune entre l'article et le texte suivi
        themes_communs = article_themes & set(texte_themes)
        if not themes_communs:
            continue

        # Condition 2 : l'article mentionne une entite liee au texte
        acteurs_texte = context["acteurs_par_texte"].get(texte_uid, {})
        matched_entities = []

        # Check parlementaires mentionnes dans l'article
        for parl_norm in parlementaires_article:
            for acteur_norm, acteur_uid in acteurs_texte.items():
                if parl_norm in acteur_norm or acteur_norm in parl_norm:
                    matched_entities.append({
                        "type": "parlementaire",
                        "name": parl_norm,
                        "uid": acteur_uid,
                    })
                    break

        # Check entreprises clientes mentionnees
        for ent_norm in entreprises_article:
            for client_norm, profile_id in context["clients_par_nom"].items():
                if ent_norm in client_norm or client_norm in ent_norm:
                    matched_entities.append({
                        "type": "client",
                        "name": ent_norm,
                        "profile_id": profile_id,
                    })
                    break

        if not matched_entities:
            continue

        # Match confirme : thematique + entite
        fu_profiles = context["followups"].get(texte_uid, {})
        for profile_id, fu in fu_profiles.items():
            reason_parts = []
            for ent in matched_entities:
                if ent["type"] == "parlementaire":
                    reason_parts.append(f"mentionne {ent['name']} (actif sur ce texte)")
                elif ent["type"] == "client":
                    reason_parts.append(f"mentionne l'entreprise {ent['name']}")

            matches.append({
                "texte_uid": texte_uid,
                "profile_id": profile_id,
                "followup_id": fu.id,
                "reason": "; ".join(reason_parts),
                "entities_matched": matched_entities,
                "article_uid": article.uid,
                "article_titre": article.titre,
                "article_url": article.url_source,
                "themes_communs": list(themes_communs),
            })

    return matches


async def process_press_articles(db: AsyncSession) -> int:
    """Traite les articles presse/regulateur enrichis recents
    et les rattache aux textes suivis quand pertinent.

    Appele par le pipeline apres l'enrichissement.
    """
    from datetime import timedelta

    # Contexte de surveillance
    context = await get_watched_context(db)
    if not context["followups"]:
        return 0

    # Articles enrichis recents (24h)
    cutoff = datetime.utcnow() - timedelta(hours=24)
    result = await db.execute(
        select(Texte).where(
            Texte.source.in_(["presse", "regulateur"]),
            Texte.themes.isnot(None),
            Texte.created_at >= cutoff,
        )
    )
    articles = result.scalars().all()

    total_matches = 0

    for article in articles:
        matches = await match_article_to_followups(db, article, context)

        for match in matches:
            fu_id = match["followup_id"]
            fu = await db.get(TexteFollowUp, fu_id)
            if not fu:
                continue

            # Ajouter au change_log du followup
            changes = _parse_json_safe(fu.change_log)
            # Eviter les doublons
            already_logged = any(
                c.get("article_uid") == match["article_uid"]
                for c in changes
                if isinstance(c, dict)
            )
            if already_logged:
                continue

            changes.append({
                "date": datetime.utcnow().isoformat(),
                "event": f"Article presse pertinent : {match['article_titre'][:80]}",
                "detail": match["reason"],
                "article_uid": match["article_uid"],
                "article_url": match["article_url"],
                "themes_communs": match["themes_communs"],
            })
            fu.change_log = json.dumps(changes, ensure_ascii=False)
            fu.updated_at = datetime.utcnow()
            total_matches += 1

            logger.info(
                "[press_intel] Article lie a %s: %s — %s",
                match["texte_uid"],
                match["article_titre"][:60],
                match["reason"],
            )

    if total_matches > 0:
        await db.commit()

    return total_matches

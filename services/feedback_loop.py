"""Service de feedback loop — le scoring s'affine avec les retours client.

Quand un client marque une alerte/un document comme pertinent ou non pertinent,
on ajuste sa configuration de veille automatiquement :
- Pertinent → renforcer les mots-clés, sources et thèmes associés
- Non pertinent → ajouter les mots-clés aux exclusions, baisser le score source

Le feedback est stocké et utilisé pour :
1. Ajuster les watch_keywords (ajouter/exclure)
2. Pondérer les sources (think tanks, médias, etc.)
3. Affiner le matching (boost/penalty par pattern)
4. Générer des recommandations de reconfiguration
"""

import json
import logging
from datetime import datetime
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.models import ClientProfile

logger = logging.getLogger(__name__)


# --- Modèle de feedback (ajouté directement ici, pas un ORM séparé) ---
# Le feedback est stocké dans un champ JSON du ClientProfile.
# Format : [{"doc_type": "texte", "doc_id": "...", "relevant": true/false,
#            "themes": [...], "source": "...", "timestamp": "..."}]


async def record_feedback(
    db: AsyncSession,
    profile_id: int,
    doc_type: str,  # texte / anticipation / press_article / signal
    doc_id: str,  # UID ou ID du document
    relevant: bool,  # True = pertinent, False = pas pertinent
    themes: list[str] | None = None,
    source_name: str | None = None,
    keywords_in_title: list[str] | None = None,
) -> dict:
    """Enregistre un feedback client et ajuste la configuration de veille.

    Args:
        profile_id: ID du client
        doc_type: Type de document
        doc_id: Identifiant du document
        relevant: Le client a trouvé ce document pertinent ou non
        themes: Thèmes du document
        source_name: Source du document
        keywords_in_title: Mots-clés trouvés dans le titre
    """
    profile = await db.get(ClientProfile, profile_id)
    if not profile:
        return {"error": "Profil non trouvé"}

    # Charger l'historique de feedback existant
    feedback_history = _load_feedback_history(profile)

    # Ajouter le nouveau feedback
    entry = {
        "doc_type": doc_type,
        "doc_id": doc_id,
        "relevant": relevant,
        "themes": themes or [],
        "source": source_name,
        "keywords": keywords_in_title or [],
        "timestamp": datetime.utcnow().isoformat(),
    }
    feedback_history.append(entry)

    # Sauvegarder (garder les 500 derniers feedbacks)
    feedback_history = feedback_history[-500:]
    profile.context_note = _save_feedback_in_context(profile.context_note, feedback_history)

    # Appliquer les ajustements
    adjustments = await _apply_feedback_adjustments(db, profile, feedback_history)

    await db.commit()

    return {
        "status": "recorded",
        "relevant": relevant,
        "adjustments": adjustments,
    }


async def _apply_feedback_adjustments(
    db: AsyncSession,
    profile: ClientProfile,
    feedback_history: list[dict],
) -> dict:
    """Analyse l'historique de feedback et ajuste la config de veille."""
    adjustments = {}

    # Séparer les feedbacks positifs et négatifs
    positive = [f for f in feedback_history if f["relevant"]]
    negative = [f for f in feedback_history if not f["relevant"]]

    # --- 1. Ajustement des mots-clés ---
    # Mots-clés des documents pertinents → potentiels nouveaux keywords
    positive_keywords = Counter()
    for f in positive:
        for kw in f.get("keywords", []):
            positive_keywords[kw] += 1

    # Mots-clés des documents non pertinents → potentielles exclusions
    negative_keywords = Counter()
    for f in negative:
        for kw in f.get("keywords", []):
            negative_keywords[kw] += 1

    # Si un mot-clé apparaît 3+ fois dans les négatifs et 0 dans les positifs → exclure
    current_excludes = json.loads(profile.watch_keywords_exclude) if profile.watch_keywords_exclude else []
    new_excludes = []
    for kw, count in negative_keywords.items():
        if count >= 3 and positive_keywords.get(kw, 0) == 0 and kw not in current_excludes:
            new_excludes.append(kw)

    if new_excludes:
        current_excludes.extend(new_excludes)
        profile.watch_keywords_exclude = json.dumps(current_excludes, ensure_ascii=False)
        adjustments["keywords_excluded"] = new_excludes

    # Si un mot-clé apparaît 3+ fois dans les positifs → ajouter aux keywords
    current_keywords = json.loads(profile.watch_keywords) if profile.watch_keywords else []
    new_keywords = []
    for kw, count in positive_keywords.items():
        if count >= 3 and kw not in current_keywords and kw not in current_excludes:
            new_keywords.append(kw)

    if new_keywords:
        current_keywords.extend(new_keywords)
        profile.watch_keywords = json.dumps(current_keywords, ensure_ascii=False)
        adjustments["keywords_added"] = new_keywords

    # --- 2. Ajustement des thèmes ---
    positive_themes = Counter()
    negative_themes = Counter()
    for f in positive:
        for t in f.get("themes", []):
            positive_themes[t] += 1
    for f in negative:
        for t in f.get("themes", []):
            negative_themes[t] += 1

    # Thèmes systématiquement non pertinents → suggestion de retrait
    theme_suggestions = []
    for theme, neg_count in negative_themes.items():
        pos_count = positive_themes.get(theme, 0)
        if neg_count >= 3 and pos_count == 0:
            theme_suggestions.append({
                "theme": theme,
                "action": "consider_removing",
                "negative_count": neg_count,
            })

    if theme_suggestions:
        adjustments["theme_suggestions"] = theme_suggestions

    # --- 3. Score de fiabilité des sources ---
    source_scores: dict[str, dict] = {}
    for f in feedback_history:
        src = f.get("source")
        if not src:
            continue
        if src not in source_scores:
            source_scores[src] = {"positive": 0, "negative": 0}
        if f["relevant"]:
            source_scores[src]["positive"] += 1
        else:
            source_scores[src]["negative"] += 1

    # Sources avec un taux de faux positifs > 70% sur 5+ feedbacks
    unreliable_sources = []
    reliable_sources = []
    for src, counts in source_scores.items():
        total = counts["positive"] + counts["negative"]
        if total >= 5:
            false_positive_rate = counts["negative"] / total
            if false_positive_rate > 0.7:
                unreliable_sources.append({
                    "source": src,
                    "false_positive_rate": round(false_positive_rate, 2),
                    "total_feedbacks": total,
                })
            elif false_positive_rate < 0.3:
                reliable_sources.append({
                    "source": src,
                    "relevance_rate": round(1 - false_positive_rate, 2),
                    "total_feedbacks": total,
                })

    if unreliable_sources:
        adjustments["unreliable_sources"] = unreliable_sources
    if reliable_sources:
        adjustments["reliable_sources"] = reliable_sources

    await db.flush()
    return adjustments


async def get_feedback_stats(
    db: AsyncSession,
    profile_id: int,
) -> dict:
    """Retourne les statistiques de feedback pour un client."""
    profile = await db.get(ClientProfile, profile_id)
    if not profile:
        return {"error": "Profil non trouvé"}

    feedback_history = _load_feedback_history(profile)

    if not feedback_history:
        return {
            "total_feedbacks": 0,
            "message": "Aucun feedback enregistré. Marquez des documents comme pertinents/non pertinents pour affiner votre veille.",
        }

    positive = sum(1 for f in feedback_history if f["relevant"])
    negative = sum(1 for f in feedback_history if not f["relevant"])

    # Thèmes les plus pertinents
    theme_counter = Counter()
    for f in feedback_history:
        if f["relevant"]:
            for t in f.get("themes", []):
                theme_counter[t] += 1

    # Sources les plus fiables
    source_stats: dict[str, dict] = {}
    for f in feedback_history:
        src = f.get("source")
        if not src:
            continue
        if src not in source_stats:
            source_stats[src] = {"pos": 0, "neg": 0}
        if f["relevant"]:
            source_stats[src]["pos"] += 1
        else:
            source_stats[src]["neg"] += 1

    return {
        "total_feedbacks": len(feedback_history),
        "positive": positive,
        "negative": negative,
        "precision": round(positive / len(feedback_history), 2) if feedback_history else 0,
        "top_themes": theme_counter.most_common(5),
        "source_reliability": {
            src: round(s["pos"] / (s["pos"] + s["neg"]), 2)
            for src, s in source_stats.items()
            if s["pos"] + s["neg"] >= 3
        },
        "excluded_keywords": json.loads(profile.watch_keywords_exclude) if profile.watch_keywords_exclude else [],
    }


def _load_feedback_history(profile: ClientProfile) -> list[dict]:
    """Charge l'historique de feedback depuis le context_note du profil."""
    if not profile.context_note:
        return []
    # Le feedback est stocké dans un bloc spécial du context_note
    try:
        if "<!-- FEEDBACK_DATA:" in profile.context_note:
            parts = profile.context_note.split("<!-- FEEDBACK_DATA:")
            json_part = parts[1].split("-->")[0].strip()
            return json.loads(json_part)
    except (IndexError, json.JSONDecodeError):
        pass
    return []


def _save_feedback_in_context(context_note: str | None, feedback_history: list[dict]) -> str:
    """Sauvegarde l'historique de feedback dans le context_note."""
    # Retirer l'ancien bloc feedback s'il existe
    base = context_note or ""
    if "<!-- FEEDBACK_DATA:" in base:
        base = base.split("<!-- FEEDBACK_DATA:")[0].strip()

    # Ajouter le nouveau bloc
    feedback_json = json.dumps(feedback_history, ensure_ascii=False)
    return f"{base}\n<!-- FEEDBACK_DATA:{feedback_json}-->"

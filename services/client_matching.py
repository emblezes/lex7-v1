"""Service de matching client — personnalisation de la veille par profil.

Chaque client a un périmètre de veille unique. Ce service détermine
la pertinence d'un document (rapport, article, texte) pour chaque client
en se basant sur sa configuration de veille.

Exemples :
- Danone : veille santé/alimentation, ONG UFC-Que Choisir, régulateur DGCCRF/ANSES
- Vinci : veille environnement/BTP, ONG WWF/FNE, régulateur ADEME/CRE
- Sanofi : veille santé/pharma, think tanks type LEEM, régulateur ANSM/HAS

Le matching se fait sur plusieurs axes :
1. Thèmes (sectors + regulatory_focus)
2. Mots-clés (watch_keywords)
3. Sources (think tanks, ONG, régulateurs, médias)
4. Acteurs (politiques, journalistes)
5. Concurrents (mentions dans la presse)
"""

import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.models import ClientProfile

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """Résultat du matching d'un document avec un profil client."""
    profile_id: int
    profile_name: str
    relevance_score: float  # 0-100
    match_reasons: list[str]  # Raisons du match
    is_direct: bool  # Match direct (thème/mot-clé) vs indirect

    @property
    def is_relevant(self) -> bool:
        return self.relevance_score >= 20

    @property
    def priority(self) -> str:
        if self.relevance_score >= 80:
            return "critical"
        elif self.relevance_score >= 60:
            return "high"
        elif self.relevance_score >= 40:
            return "medium"
        return "low"


def _load_json_list(value: str | None) -> list[str]:
    """Parse un champ JSON list en toute sécurité."""
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(x).lower().strip() for x in parsed if x]
        return []
    except (json.JSONDecodeError, TypeError):
        return []


def _load_json_list_raw(value: str | None) -> list:
    """Parse un champ JSON list sans lowercase."""
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


class ClientMatcher:
    """Moteur de matching documents → clients."""

    def __init__(self, profile: ClientProfile):
        self.profile = profile
        self.profile_id = profile.id
        self.profile_name = profile.name

        # Charger toutes les listes de veille
        self.sectors = _load_json_list(profile.sectors)
        self.regulatory_focus = _load_json_list(profile.regulatory_focus)
        self.keywords = _load_json_list(profile.watch_keywords)
        self.keywords_exclude = _load_json_list(profile.watch_keywords_exclude)
        self.competitors = _load_json_list(profile.competitors)
        self.watched_think_tanks = _load_json_list(profile.watched_think_tanks)
        self.watched_inspections = _load_json_list(profile.watched_inspections)
        self.watched_ngos = _load_json_list(profile.watched_ngos)
        self.watched_federations = _load_json_list(profile.watched_federations)
        self.watched_media = _load_json_list(profile.watched_media)
        self.watched_regulators = _load_json_list(profile.watched_regulators)
        self.watched_politicians = _load_json_list(profile.watched_politicians)
        self.eu_keywords = _load_json_list(profile.eu_watch_keywords)
        self.pa_priorities = _load_json_list(profile.pa_priorities)

        # Journalistes (format plus riche)
        self.watched_journalists = _load_json_list_raw(profile.watched_journalists)

    def match_document(
        self,
        themes: list[str] | None = None,
        title: str | None = None,
        content: str | None = None,
        source_name: str | None = None,
        source_type: str | None = None,
        author: str | None = None,
        mentioned_entities: dict | None = None,
    ) -> MatchResult:
        """Évalue la pertinence d'un document pour ce client.

        Args:
            themes: Thèmes classifiés du document (17 thèmes standard)
            title: Titre du document
            content: Texte/résumé du document
            source_name: Nom de la source ("Cour des Comptes", "Le Monde", etc.)
            source_type: Type de source ("think_tank", "presse", etc.)
            author: Auteur/journaliste
            mentioned_entities: Entités mentionnées {"companies": [], "politicians": []}

        Returns:
            MatchResult avec score de pertinence et raisons.
        """
        score = 0.0
        reasons: list[str] = []
        text_combined = _combine_text(title, content).lower()

        # --- Vérifier les exclusions d'abord ---
        for kw in self.keywords_exclude:
            if kw in text_combined:
                return MatchResult(
                    profile_id=self.profile_id,
                    profile_name=self.profile_name,
                    relevance_score=0,
                    match_reasons=["Exclu par mot-clé"],
                    is_direct=False,
                )

        # --- 1. Match par thèmes (poids: 30) ---
        if themes:
            themes_lower = [t.lower() for t in themes]
            sector_matches = set(self.sectors) & set(themes_lower)
            if sector_matches:
                score += 30
                reasons.append(f"Thèmes : {', '.join(sector_matches)}")

            focus_matches = [
                f for f in self.regulatory_focus
                if any(f in t for t in themes_lower)
            ]
            if focus_matches:
                score += 15
                reasons.append(f"Focus réglementaire : {', '.join(focus_matches)}")

        # --- 2. Match par mots-clés (poids: 25) ---
        keyword_hits = [kw for kw in self.keywords if kw in text_combined]
        if keyword_hits:
            score += min(len(keyword_hits) * 10, 25)
            reasons.append(f"Mots-clés : {', '.join(keyword_hits[:5])}")

        # Mots-clés EU
        eu_hits = [kw for kw in self.eu_keywords if kw in text_combined]
        if eu_hits:
            score += min(len(eu_hits) * 8, 15)
            reasons.append(f"EU : {', '.join(eu_hits[:3])}")

        # Priorités PA
        priority_hits = [p for p in self.pa_priorities if p in text_combined]
        if priority_hits:
            score += min(len(priority_hits) * 12, 20)
            reasons.append(f"Priorité PA : {', '.join(priority_hits[:3])}")

        # --- 3. Match par source (poids: 20) ---
        source_lower = (source_name or "").lower()

        if source_lower and self.watched_think_tanks:
            if any(tt in source_lower for tt in self.watched_think_tanks):
                score += 20
                reasons.append(f"Think tank surveillé : {source_name}")

        if source_lower and self.watched_inspections:
            if any(insp in source_lower for insp in self.watched_inspections):
                score += 20
                reasons.append(f"Corps d'inspection surveillé : {source_name}")

        if source_lower and self.watched_media:
            if any(m in source_lower for m in self.watched_media):
                score += 15
                reasons.append(f"Média surveillé : {source_name}")

        if source_lower and self.watched_regulators:
            if any(reg in source_lower for reg in self.watched_regulators):
                score += 20
                reasons.append(f"Régulateur surveillé : {source_name}")

        # --- 4. Match par entités mentionnées (poids: 20) ---
        if mentioned_entities:
            # Mention du client lui-même
            companies = [c.lower() for c in mentioned_entities.get("companies", [])]
            if self.profile_name.lower() in " ".join(companies):
                score += 30
                reasons.append("Mention directe du client")

            # Mention d'un concurrent
            competitor_mentions = [
                c for c in self.competitors
                if any(c in comp for comp in companies)
            ]
            if competitor_mentions:
                score += 15
                reasons.append(f"Concurrent mentionné : {', '.join(competitor_mentions[:3])}")

            # Mention d'un politique suivi
            politicians = [p.lower() for p in mentioned_entities.get("politicians", [])]
            pol_matches = [
                p for p in self.watched_politicians
                if any(p in pol for pol in politicians)
            ]
            if pol_matches:
                score += 10
                reasons.append(f"Politique suivi mentionné")

        # Mention du client dans le texte
        if self.profile_name.lower() in text_combined:
            score += 25
            if "Mention directe du client" not in reasons:
                reasons.append("Mention directe du client dans le texte")

        # --- 5. Match par auteur/journaliste (poids: 10) ---
        if author:
            author_lower = author.lower()
            for j in self.watched_journalists:
                j_name = j.get("nom", "") if isinstance(j, dict) else str(j)
                if j_name.lower() in author_lower:
                    score += 10
                    reasons.append(f"Journaliste surveillé : {j_name}")
                    break

        # Plafonner à 100
        score = min(score, 100)

        return MatchResult(
            profile_id=self.profile_id,
            profile_name=self.profile_name,
            relevance_score=round(score, 1),
            match_reasons=reasons,
            is_direct=score >= 40,
        )


def _combine_text(*parts: str | None) -> str:
    """Combine plusieurs textes en un seul pour la recherche."""
    return " ".join(p for p in parts if p)


async def match_document_to_clients(
    db: AsyncSession,
    themes: list[str] | None = None,
    title: str | None = None,
    content: str | None = None,
    source_name: str | None = None,
    source_type: str | None = None,
    author: str | None = None,
    mentioned_entities: dict | None = None,
    min_score: float = 20,
) -> list[MatchResult]:
    """Évalue la pertinence d'un document pour TOUS les clients actifs.

    Retourne la liste des clients pour qui le document est pertinent,
    triée par score décroissant.
    """
    result = await db.execute(
        select(ClientProfile).where(ClientProfile.is_active == True)
    )
    profiles = result.scalars().all()

    matches: list[MatchResult] = []
    for profile in profiles:
        matcher = ClientMatcher(profile)
        match = matcher.match_document(
            themes=themes,
            title=title,
            content=content,
            source_name=source_name,
            source_type=source_type,
            author=author,
            mentioned_entities=mentioned_entities,
        )
        if match.relevance_score >= min_score:
            matches.append(match)

    matches.sort(key=lambda m: m.relevance_score, reverse=True)
    return matches


async def get_client_watch_config(
    db: AsyncSession,
    profile_id: int,
) -> dict:
    """Retourne la configuration de veille complète d'un client.

    Utile pour l'affichage frontend et la configuration.
    """
    profile = await db.get(ClientProfile, profile_id)
    if not profile:
        return {"error": "Profil non trouvé"}

    return {
        "profile_id": profile.id,
        "name": profile.name,
        "veille": {
            "sectors": _load_json_list_raw(profile.sectors),
            "regulatory_focus": _load_json_list_raw(profile.regulatory_focus),
            "watch_keywords": _load_json_list_raw(profile.watch_keywords),
            "watch_keywords_exclude": _load_json_list_raw(profile.watch_keywords_exclude),
            "competitors": _load_json_list_raw(profile.competitors),
            "pa_priorities": _load_json_list_raw(profile.pa_priorities),
        },
        "sources": {
            "think_tanks": _load_json_list_raw(profile.watched_think_tanks),
            "inspections": _load_json_list_raw(profile.watched_inspections),
            "ngos": _load_json_list_raw(profile.watched_ngos),
            "federations": _load_json_list_raw(profile.watched_federations),
            "media": _load_json_list_raw(profile.watched_media),
            "regulators": _load_json_list_raw(profile.watched_regulators),
        },
        "acteurs": {
            "politicians": _load_json_list_raw(profile.watched_politicians),
            "journalists": _load_json_list_raw(profile.watched_journalists),
        },
        "eu": {
            "keywords": _load_json_list_raw(profile.eu_watch_keywords),
            "committees": _load_json_list_raw(profile.eu_watched_committees),
        },
        "strategie": {
            "pa_strategy": profile.pa_strategy,
            "pa_priorities": _load_json_list_raw(profile.pa_priorities),
        },
    }

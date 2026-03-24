"""Tests pour le matching client (ClientMatcher)."""

import json
from unittest.mock import MagicMock

from legix.services.client_matching import ClientMatcher


def _make_profile(**overrides):
    """Cree un faux profil client."""
    profile = MagicMock()
    profile.id = overrides.get("id", 1)
    profile.name = overrides.get("name", "TestCorp")
    profile.sectors = json.dumps(overrides.get("sectors", ["energie"]))
    profile.business_lines = json.dumps(overrides.get("business_lines", ["production"]))
    profile.products = json.dumps(overrides.get("products", []))
    profile.regulatory_focus = json.dumps(overrides.get("regulatory_focus", ["code de l'energie"]))
    profile.watch_keywords = json.dumps(overrides.get("watch_keywords", ["nucleaire", "renouvelable"]))
    profile.watch_excluded_keywords = json.dumps(overrides.get("watch_excluded_keywords", []))
    profile.watch_actors = json.dumps(overrides.get("watch_actors", []))
    profile.watch_ong = json.dumps(overrides.get("watch_ong", []))
    profile.watch_regulators = json.dumps(overrides.get("watch_regulators", []))
    profile.watch_eu_committees = json.dumps(overrides.get("watch_eu_committees", []))
    return profile


def test_matcher_high_relevance():
    """Un texte sur l'energie nucleaire = haute pertinence pour un client energie."""
    profile = _make_profile(
        sectors=["energie"],
        watch_keywords=["nucleaire", "renouvelable", "EPR"],
    )
    matcher = ClientMatcher(profile)

    result = matcher.match_document(
        title="Proposition de loi sur le nucleaire",
        themes=["energie"],
        content="Texte relatif au deploiement de nouveaux EPR.",
    )
    assert result.relevance_score >= 40, f"Score trop bas: {result.relevance_score}"
    assert result.is_direct


def test_matcher_low_relevance():
    """Un texte sur l'agriculture = faible pertinence pour un client energie."""
    profile = _make_profile(
        sectors=["energie"],
        watch_keywords=["nucleaire"],
    )
    matcher = ClientMatcher(profile)

    result = matcher.match_document(
        title="Proposition de loi sur les pesticides",
        themes=["agriculture"],
        content="Interdiction de certains pesticides neonicotinoides.",
    )
    assert result.relevance_score < 30, f"Score trop haut: {result.relevance_score}"


def test_matcher_keyword_boost():
    """Les mots-cles client boostent le score."""
    profile = _make_profile(
        sectors=["industrie"],
        watch_keywords=["PFAS", "polluants eternels"],
    )
    matcher = ClientMatcher(profile)

    result_with = matcher.match_document(
        title="Rapport sur les PFAS dans l'industrie",
        themes=["environnement/climat"],
        content="Les polluants eternels PFAS sont au coeur des preoccupations.",
    )
    result_without = matcher.match_document(
        title="Rapport sur la biodiversite",
        themes=["environnement/climat"],
        content="La biodiversite est en danger en France.",
    )
    assert result_with.relevance_score > result_without.relevance_score, (
        f"Keyword boost absent: {result_with.relevance_score} vs {result_without.relevance_score}"
    )


def test_matcher_exclusion():
    """Les mots-cles exclus reduisent le score."""
    profile = _make_profile(
        sectors=["energie"],
        watch_keywords=["nucleaire"],
        watch_excluded_keywords=["militaire", "defense"],
    )
    matcher = ClientMatcher(profile)

    result = matcher.match_document(
        title="Le nucleaire militaire en France",
        themes=["defense"],
        content="Texte sur la dissuasion nucleaire et la defense.",
    )
    assert result.relevance_score < 20, f"Exclusion non effective: {result.relevance_score}"

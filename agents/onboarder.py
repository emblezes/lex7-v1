"""OnboarderAgent — onboarding automatisé d'un nouveau client.

Pipeline complet :
1. Enrichissement entreprise (SIRENE, site web, BODACC, Claude)
2. Configuration de veille automatique (sources, ONG, régulateurs, keywords)
3. Scan du backlog législatif (textes existants pertinents)
4. Génération du rapport d'intégration

L'objectif : le client donne son nom et son secteur, et en 2 minutes
il a un dashboard personnalisé avec les dossiers en cours qui le concernent.
"""

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.models import (
    AnticipationReport,
    ClientProfile,
    Texte,
    TexteFollowUp,
)

logger = logging.getLogger(__name__)


async def run_full_onboarding(
    db: AsyncSession,
    profile_id: int,
) -> dict:
    """Pipeline d'onboarding complet pour un nouveau client.

    1. Enrichir le profil entreprise (SIRENE + site web + Claude)
    2. Configurer la veille automatiquement
    3. Scanner le backlog législatif
    4. Créer les TexteFollowUp pour les dossiers pertinents
    5. Détecter les signaux d'anticipation pertinents
    """
    profile = await db.get(ClientProfile, profile_id)
    if not profile:
        return {"error": "Profil non trouvé"}

    results = {
        "profile_id": profile_id,
        "steps": {},
    }

    # --- Étape 1 : Enrichissement entreprise ---
    try:
        enrichment = await _enrich_company(db, profile)
        results["steps"]["enrichment"] = enrichment
    except Exception as e:
        logger.warning("Enrichissement échoué pour %s: %s", profile.name, e)
        results["steps"]["enrichment"] = {"status": "failed", "error": str(e)}

    # Recharger le profil après enrichissement
    await db.refresh(profile)

    # --- Étape 2 : Configuration veille automatique ---
    try:
        watch_config = await _auto_configure_watch(db, profile)
        results["steps"]["watch_config"] = watch_config
    except Exception as e:
        logger.warning("Config veille échouée pour %s: %s", profile.name, e)
        results["steps"]["watch_config"] = {"status": "failed", "error": str(e)}

    # --- Étape 3 : Scan du backlog législatif ---
    try:
        backlog = await _scan_legislative_backlog(db, profile)
        results["steps"]["backlog_scan"] = backlog
    except Exception as e:
        logger.warning("Scan backlog échoué pour %s: %s", profile.name, e)
        results["steps"]["backlog_scan"] = {"status": "failed", "error": str(e)}

    # --- Étape 4 : Signaux d'anticipation ---
    try:
        anticipation = await _scan_anticipation(db, profile)
        results["steps"]["anticipation"] = anticipation
    except Exception as e:
        logger.warning("Scan anticipation échoué pour %s: %s", profile.name, e)
        results["steps"]["anticipation"] = {"status": "failed", "error": str(e)}

    await db.commit()

    logger.info(
        "Onboarding complet pour %s : %d followups, %d anticipations",
        profile.name,
        results["steps"].get("backlog_scan", {}).get("followups_created", 0),
        results["steps"].get("anticipation", {}).get("signals_found", 0),
    )

    return results


async def _enrich_company(db: AsyncSession, profile: ClientProfile) -> dict:
    """Étape 1 : Enrichissement via APIs publiques + Claude."""
    # Ne pas ré-enrichir si déjà fait
    if profile.description and profile.siren:
        return {"status": "already_enriched"}

    from legix.services.company_enrichment import enrich_and_build_profile

    sectors = json.loads(profile.sectors) if profile.sectors else []
    enriched = await enrich_and_build_profile(
        company_name=profile.name,
        email=profile.email or "",
        sectors=sectors,
        website_url=profile.site_web,
    )

    # Appliquer les données enrichies au profil
    for key, value in enriched.items():
        if value and hasattr(profile, key):
            current = getattr(profile, key)
            # Ne pas écraser les données existantes non vides
            if not current or current in ("", "[]", "null"):
                setattr(profile, key, value)

    await db.flush()

    return {
        "status": "enriched",
        "siren": enriched.get("siren"),
        "has_description": bool(enriched.get("description")),
        "business_lines": json.loads(enriched.get("business_lines", "[]")),
        "regulatory_focus": json.loads(enriched.get("regulatory_focus", "[]")),
    }


async def _auto_configure_watch(db: AsyncSession, profile: ClientProfile) -> dict:
    """Étape 2 : Configurer la veille automatiquement basée sur le secteur."""
    # Ne pas écraser une config existante
    if profile.watch_keywords:
        return {"status": "already_configured"}

    from legix.api.routes.watch_config import _build_suggestions

    sectors = json.loads(profile.sectors) if profile.sectors else []
    regulatory_focus = json.loads(profile.regulatory_focus) if profile.regulatory_focus else []

    suggestions = _build_suggestions(sectors, regulatory_focus, profile.name)

    # Appliquer les suggestions comme configuration par défaut
    config_applied = {}

    if suggestions.get("keywords") and not profile.watch_keywords:
        # Combiner les keywords sectoriels + regulatory_focus
        all_keywords = list(set(suggestions["keywords"] + regulatory_focus))
        profile.watch_keywords = json.dumps(all_keywords, ensure_ascii=False)
        config_applied["watch_keywords"] = all_keywords

    if suggestions.get("regulators") and not profile.watched_regulators:
        profile.watched_regulators = json.dumps(suggestions["regulators"], ensure_ascii=False)
        config_applied["regulators"] = suggestions["regulators"]

    if suggestions.get("ngos") and not profile.watched_ngos:
        profile.watched_ngos = json.dumps(suggestions["ngos"], ensure_ascii=False)
        config_applied["ngos"] = suggestions["ngos"]

    if suggestions.get("federations") and not profile.watched_federations:
        profile.watched_federations = json.dumps(suggestions["federations"], ensure_ascii=False)
        config_applied["federations"] = suggestions["federations"]

    if suggestions.get("think_tanks") and not profile.watched_think_tanks:
        profile.watched_think_tanks = json.dumps(suggestions["think_tanks"], ensure_ascii=False)
        config_applied["think_tanks"] = suggestions["think_tanks"]

    if suggestions.get("media") and not profile.watched_media:
        profile.watched_media = json.dumps(suggestions["media"], ensure_ascii=False)
        config_applied["media"] = suggestions["media"]

    if suggestions.get("eu_keywords") and not profile.eu_watch_keywords:
        profile.eu_watch_keywords = json.dumps(suggestions["eu_keywords"], ensure_ascii=False)
        config_applied["eu_keywords"] = suggestions["eu_keywords"]

    if suggestions.get("eu_committees") and not profile.eu_watched_committees:
        profile.eu_watched_committees = json.dumps(suggestions["eu_committees"], ensure_ascii=False)
        config_applied["eu_committees"] = suggestions["eu_committees"]

    # Ajouter le nom de l'entreprise dans les keywords (pour capter les mentions)
    current_kw = json.loads(profile.watch_keywords) if profile.watch_keywords else []
    if profile.name.lower() not in [k.lower() for k in current_kw]:
        current_kw.append(profile.name)
        profile.watch_keywords = json.dumps(current_kw, ensure_ascii=False)

    await db.flush()

    return {
        "status": "configured",
        "fields_set": list(config_applied.keys()),
        "config": config_applied,
    }


async def _scan_legislative_backlog(db: AsyncSession, profile: ClientProfile) -> dict:
    """Étape 3 : Scanner les textes existants et créer des followups."""
    from legix.services.client_matching import ClientMatcher

    matcher = ClientMatcher(profile)

    # Récupérer les textes récents (6 derniers mois)
    cutoff = datetime.utcnow() - timedelta(days=180)
    result = await db.execute(
        select(Texte).where(
            Texte.date_depot >= cutoff,
            Texte.themes.isnot(None),
        ).order_by(Texte.date_depot.desc()).limit(200)
    )
    textes = result.scalars().all()

    followups_created = 0
    matched_textes = []

    for texte in textes:
        themes = json.loads(texte.themes) if texte.themes else []
        match = matcher.match_document(
            themes=themes,
            title=texte.titre or texte.titre_court,
            content=texte.resume_ia,
        )

        if not match.is_relevant:
            continue

        # Vérifier qu'il n'existe pas déjà un followup
        existing = await db.execute(
            select(TexteFollowUp).where(
                TexteFollowUp.profile_id == profile.id,
                TexteFollowUp.texte_uid == texte.uid,
            )
        )
        if existing.scalar_one_or_none():
            continue

        # Déterminer la priorité basée sur le score de matching
        priority = match.priority

        followup = TexteFollowUp(
            profile_id=profile.id,
            texte_uid=texte.uid,
            status="watching",
            priority=priority,
            change_log=json.dumps([{
                "date": datetime.utcnow().isoformat(),
                "event": "Détecté lors de l'onboarding",
                "relevance_score": match.relevance_score,
                "reasons": match.match_reasons,
            }], ensure_ascii=False),
            next_check_at=datetime.utcnow() + timedelta(days=3),
        )
        db.add(followup)
        followups_created += 1
        matched_textes.append({
            "uid": texte.uid,
            "titre": (texte.titre or texte.titre_court or "")[:100],
            "score": match.relevance_score,
            "priority": priority,
            "reasons": match.match_reasons[:3],
        })

    await db.flush()

    return {
        "status": "scanned",
        "textes_analyzed": len(textes),
        "followups_created": followups_created,
        "top_dossiers": sorted(
            matched_textes, key=lambda x: x["score"], reverse=True
        )[:10],
    }


async def _scan_anticipation(db: AsyncSession, profile: ClientProfile) -> dict:
    """Étape 4 : Scanner les rapports d'anticipation pertinents."""
    from legix.services.client_matching import ClientMatcher

    matcher = ClientMatcher(profile)

    result = await db.execute(
        select(AnticipationReport).order_by(
            AnticipationReport.publication_date.desc()
        ).limit(100)
    )
    reports = result.scalars().all()

    signals = []
    for report in reports:
        themes = json.loads(report.themes) if report.themes else []
        match = matcher.match_document(
            themes=themes,
            title=report.title,
            content=report.resume_ia,
            source_name=report.source_name,
        )

        if match.is_relevant:
            # Marquer le rapport comme pertinent pour ce client
            matched_ids = json.loads(report.matched_profile_ids) if report.matched_profile_ids else []
            if profile.id not in matched_ids:
                matched_ids.append(profile.id)
                report.matched_profile_ids = json.dumps(matched_ids)

            signals.append({
                "report_id": report.id,
                "title": report.title,
                "source": report.source_name,
                "score": match.relevance_score,
                "reasons": match.match_reasons[:3],
            })

    await db.flush()

    return {
        "status": "scanned",
        "reports_analyzed": len(reports),
        "signals_found": len(signals),
        "top_signals": sorted(
            signals, key=lambda x: x["score"], reverse=True
        )[:10],
    }

"""Trigger agentique — suivi par texte, pas par amendement.

Quand un nouveau texte ou amendement enrichi arrive :
- Si le texte matche les secteurs d'un client → creer un TexteFollowUp + TexteBrief
- Generer une ImpactAlert pour chaque match pertinent
- Appeler le CoordinateurAgent pour les alertes critical/high
- Les alertes individuelles exceptionnelles (ex: amendement gouvernemental)
  declenchent des notifications instantanees
"""

import asyncio
import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.config import settings
from legix.core.models import (
    Amendement,
    ClientProfile,
    Evenement,
    ImpactAlert,
    NotificationQueue,
    TexteBrief,
    TexteFollowUp,
    Texte,
)

logger = logging.getLogger(__name__)


async def get_active_profiles(db: AsyncSession) -> list[ClientProfile]:
    """Retourne tous les profils clients actifs."""
    result = await db.execute(
        select(ClientProfile).where(ClientProfile.is_active.is_(True))
    )
    return list(result.scalars().all())


def parse_themes(themes_json: str | None) -> list[str]:
    """Parse les themes JSON d'un document."""
    if not themes_json:
        return []
    try:
        return json.loads(themes_json)
    except (json.JSONDecodeError, TypeError):
        return []


def _matching_profiles(
    doc_themes: list[str],
    profiles: list[ClientProfile],
    title: str | None = None,
    content: str | None = None,
    source_name: str | None = None,
) -> list[tuple[ClientProfile, float]]:
    """Retourne les profils pertinents avec score, en utilisant le matching personnalisé.

    Chaque client a sa propre configuration de veille (keywords, sources, ONG, etc.)
    Le matching ne se fait pas juste sur les thèmes mais sur tout le périmètre.

    Returns:
        Liste de tuples (profile, relevance_score) triée par score décroissant.
    """
    from legix.services.client_matching import ClientMatcher

    matched: list[tuple[ClientProfile, float]] = []
    for profile in profiles:
        matcher = ClientMatcher(profile)
        result = matcher.match_document(
            themes=doc_themes,
            title=title,
            content=content,
            source_name=source_name,
        )
        if result.is_relevant:
            matched.append((profile, result.relevance_score))

    # Fallback : si le nouveau matching ne donne rien, revenir au match par thèmes
    # (pour les clients qui n'ont pas encore configuré leur veille personnalisée)
    if not matched:
        for profile in profiles:
            client_sectors = json.loads(profile.sectors) if profile.sectors else []
            if set(doc_themes) & set(client_sectors):
                matched.append((profile, 30.0))  # Score par défaut

    matched.sort(key=lambda x: x[1], reverse=True)
    return matched


async def _get_or_create_followup(
    db: AsyncSession, texte_uid: str, profile: ClientProfile
) -> tuple[TexteFollowUp, bool]:
    """Retourne le followup existant ou en cree un nouveau. Returns (followup, created)."""
    result = await db.execute(
        select(TexteFollowUp).where(
            TexteFollowUp.profile_id == profile.id,
            TexteFollowUp.texte_uid == texte_uid,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing, False

    followup = TexteFollowUp(
        profile_id=profile.id,
        texte_uid=texte_uid,
        status="watching",
        priority="medium",
        change_log=json.dumps([{
            "date": datetime.utcnow().isoformat(),
            "event": "Texte detecte comme pertinent — suivi automatique active",
        }]),
        next_check_at=datetime.utcnow() + timedelta(hours=12),
    )
    db.add(followup)
    await db.flush()
    return followup, True


async def _get_existing_brief(
    db: AsyncSession, texte_uid: str, profile_id: int
) -> TexteBrief | None:
    """Retourne le brief existant si present."""
    result = await db.execute(
        select(TexteBrief).where(
            TexteBrief.profile_id == profile_id,
            TexteBrief.texte_uid == texte_uid,
        )
    )
    return result.scalar_one_or_none()


async def on_new_texte(
    db: AsyncSession, texte: Texte, profiles: list[ClientProfile] | None = None
) -> dict:
    """Quand un nouveau texte arrive : creer followup + brief pour chaque client concerne."""
    if profiles is None:
        profiles = await get_active_profiles(db)

    doc_themes = parse_themes(texte.themes)
    if not doc_themes:
        return {"followups_created": 0, "briefs_created": 0}

    matched = _matching_profiles(
        doc_themes, profiles,
        title=texte.titre or texte.titre_court,
        content=texte.resume_ia,
    )
    if not matched:
        return {"followups_created": 0, "briefs_created": 0}

    followups_created = 0
    briefs_created = 0

    for profile, score in matched:
        followup, created = await _get_or_create_followup(db, texte.uid, profile)
        if created:
            followups_created += 1
            logger.info(
                "TexteFollowUp cree pour %s / %s",
                profile.name, texte.uid,
            )

        # Generer le brief seulement si le texte a des amendements
        from sqlalchemy import func
        amdt_count = (await db.execute(
            select(func.count(Amendement.uid)).where(
                Amendement.texte_ref == texte.uid
            )
        )).scalar() or 0

        if amdt_count > 0 and not await _get_existing_brief(db, texte.uid, profile.id):
            try:
                from legix.services.texte_brief import generate_texte_brief
                await generate_texte_brief(db, texte.uid, profile, followup)
                briefs_created += 1
            except Exception as e:
                logger.warning(
                    "Brief echoue pour %s / %s: %s",
                    profile.name, texte.uid, e,
                )

    await db.commit()
    return {"followups_created": followups_created, "briefs_created": briefs_created}


async def on_new_amendments_for_texte(
    db: AsyncSession,
    texte_uid: str,
    new_amendments: list[Amendement],
    profiles: list[ClientProfile] | None = None,
) -> dict:
    """Quand de nouveaux amendements arrivent sur un texte.

    - Si le texte est deja suivi → log les changements, marquer brief perime
    - Sinon, si les themes matchent → creer followup + brief
    """
    if profiles is None:
        profiles = await get_active_profiles(db)

    # Themes du texte parent
    texte = await db.get(Texte, texte_uid)
    if not texte:
        return {"followups_created": 0, "briefs_updated": 0}

    # Combiner themes du texte + themes des amendements
    all_themes = set(parse_themes(texte.themes))
    for amdt in new_amendments:
        all_themes.update(parse_themes(amdt.themes))

    matched = _matching_profiles(
        list(all_themes), profiles,
        title=texte.titre or texte.titre_court,
        content=texte.resume_ia,
    )
    if not matched:
        return {"followups_created": 0, "briefs_updated": 0}

    followups_created = 0
    briefs_updated = 0

    # Creer des evenements pour les amendements significatifs
    for amdt in new_amendments:
        severity = "info"
        if amdt.sort and "adopt" in amdt.sort.lower():
            severity = "warning"
        elif amdt.auteur_type and amdt.auteur_type.lower() == "gouvernement":
            severity = "critical"

        db.add(Evenement(
            texte_uid=texte_uid,
            event_type="amendement",
            title=f"Amendement {amdt.numero or amdt.uid}",
            description=(
                f"par {amdt.auteur_nom or 'Inconnu'}"
                + (f" ({amdt.groupe_nom})" if amdt.groupe_nom else "")
                + (f" — {amdt.sort}" if amdt.sort else "")
            ),
            severity=severity,
            source_ref=amdt.uid,
            source_url=amdt.url_source,
        ))

    for profile, score in matched:
        followup, created = await _get_or_create_followup(db, texte_uid, profile)

        if created:
            followups_created += 1
            logger.info(
                "TexteFollowUp cree (via amendement) pour %s / %s (score: %.0f)",
                profile.name, texte_uid, score,
            )
            # Generer un brief initial
            try:
                from legix.services.texte_brief import generate_texte_brief
                await generate_texte_brief(db, texte_uid, profile, followup)
                briefs_updated += 1
            except Exception as e:
                logger.warning("Brief initial echoue pour %s / %s: %s", profile.name, texte_uid, e)
        else:
            # Texte deja suivi — log les nouveaux amendements dans le change_log
            changes = json.loads(followup.change_log or "[]")
            amdt_nums = [a.numero or a.uid for a in new_amendments]
            changes.append({
                "date": datetime.utcnow().isoformat(),
                "event": f"{len(new_amendments)} nouveaux amendements detectes",
                "detail": f"Amendements: {', '.join(amdt_nums[:10])}",
            })
            followup.change_log = json.dumps(changes, ensure_ascii=False)
            followup.updated_at = datetime.utcnow()

            # Regenerer le brief avec les nouvelles donnees
            existing_brief = await _get_existing_brief(db, texte_uid, profile.id)
            if existing_brief:
                try:
                    from legix.services.texte_brief import generate_texte_brief
                    await generate_texte_brief(db, texte_uid, profile, followup)
                    briefs_updated += 1
                    logger.info(
                        "TexteBrief mis a jour pour %s / %s (+%d amdts)",
                        profile.name, texte_uid, len(new_amendments),
                    )
                except Exception as e:
                    logger.warning("Brief update echoue: %s", e)

    await db.commit()
    return {"followups_created": followups_created, "briefs_updated": briefs_updated}


# --- Compatibilite avec l'ancien pipeline ---

async def on_new_document(
    db: AsyncSession,
    document,
    profiles: list[ClientProfile] | None = None,
) -> list:
    """Point d'entree compatible avec l'ancien pipeline.

    Delegue vers on_new_texte ou on_new_amendments_for_texte selon le type.
    Retourne une liste vide (plus d'alertes individuelles).
    """
    if profiles is None:
        profiles = await get_active_profiles(db)

    if isinstance(document, Texte):
        await on_new_texte(db, document, profiles)
    elif isinstance(document, Amendement) and document.texte_ref:
        await on_new_amendments_for_texte(
            db, document.texte_ref, [document], profiles
        )

    return []  # Plus d'alertes individuelles


# --- Generation d'alertes et orchestration ---


def _clean_html(text: str | None) -> str:
    """Nettoie le HTML basique."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", clean).strip()[:300]


def _build_doc_summary(doc: Texte | Amendement) -> str:
    """Construit un resume compact du document pour le prompt."""
    parts: list[str] = []
    if isinstance(doc, Texte):
        parts.append(f"Type: texte legislatif")
        parts.append(f"Titre: {doc.titre_court or doc.titre or 'N/A'}")
        if doc.type_libelle:
            parts.append(f"Nature: {doc.type_libelle}")
        if doc.resume_ia:
            parts.append(f"Resume: {doc.resume_ia[:300]}")
        if doc.source:
            parts.append(f"Source: {doc.source}")
    elif isinstance(doc, Amendement):
        parts.append(f"Type: amendement")
        parts.append(f"Numero: {doc.numero or doc.uid}")
        if doc.auteur_nom:
            parts.append(f"Auteur: {doc.auteur_nom}")
        if doc.groupe_nom:
            parts.append(f"Groupe: {doc.groupe_nom}")
        if doc.article_vise:
            parts.append(f"Article vise: {doc.article_vise}")
        if doc.sort:
            parts.append(f"Sort: {doc.sort}")
        if doc.resume_ia:
            parts.append(f"Resume: {doc.resume_ia[:300]}")
        elif doc.expose_sommaire:
            parts.append(f"Expose: {_clean_html(doc.expose_sommaire)[:200]}")
    themes = parse_themes(doc.themes) if doc.themes else []
    if themes:
        parts.append(f"Themes: {', '.join(themes)}")
    return "\n".join(parts)


async def _analyze_impact_for_profile(
    profile: ClientProfile,
    documents: list[Texte | Amendement],
) -> list[dict]:
    """Appelle Claude pour scorer l'impact de documents sur un profil client.

    Version legere pour le pipeline continu (pas le scan complet d'onboarding).
    Retourne une liste de dicts {doc_index, impact_level, is_threat, impact_summary, exposure_eur}.
    """
    if not settings.anthropic_api_key or not documents:
        return []

    company = profile.name
    sectors = ", ".join(json.loads(profile.sectors)) if profile.sectors else ""
    reg_focus = ", ".join(json.loads(profile.regulatory_focus)) if profile.regulatory_focus else ""

    docs_text = []
    for i, doc in enumerate(documents):
        docs_text.append(f"--- Document {i} ---\n{_build_doc_summary(doc)}")
    docs_block = "\n\n".join(docs_text)

    prompt = f"""Tu es analyste senior en affaires publiques pour {company}.
Secteurs: {sectors}
Focus reglementaire: {reg_focus}

Analyse chaque document et evalue son impact pour {company}.

FORMAT JSON strict (pas de texte avant/apres) :
[
  {{
    "doc_index": 0,
    "impact_level": "critical|high|medium|low",
    "is_threat": true,
    "impact_summary": "Resume en 2-3 phrases de l'impact pour {company}",
    "exposure_eur": 0
  }}
]

DOCUMENTS :
{docs_block}"""

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = await asyncio.to_thread(
            client.messages.create,
            model=settings.enrichment_model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return json.loads(text)
    except Exception as e:
        logger.warning("Analyse impact echouee pour %s: %s", company, e)
        return []


async def generate_alerts_for_new_documents(
    db: AsyncSession,
    new_texte_uids: list[str],
    new_amendement_uids: list[str],
) -> dict:
    """Genere des ImpactAlert pour les nouveaux documents et orchestre les alertes critiques.

    C'est le maillon manquant entre le trigger (TexteFollowUp) et le coordinateur (notifications).
    Appele a la fin du pipeline, apres la creation des followups.

    Returns:
        {"alerts_created": int, "orchestrated": int}
    """
    profiles = await get_active_profiles(db)
    if not profiles:
        return {"alerts_created": 0, "orchestrated": 0}

    # Charger les nouveaux documents
    new_docs: list[Texte | Amendement] = []
    for uid in new_texte_uids:
        doc = await db.get(Texte, uid)
        if doc and doc.themes:
            new_docs.append(doc)
    for uid in new_amendement_uids:
        doc = await db.get(Amendement, uid)
        if doc and doc.themes:
            new_docs.append(doc)

    if not new_docs:
        return {"alerts_created": 0, "orchestrated": 0}

    alerts_created = 0
    orchestrated = 0

    for profile in profiles:
        # Filtrer les documents pertinents pour ce profil
        relevant_docs: list[Texte | Amendement] = []
        for doc in new_docs:
            doc_themes = parse_themes(doc.themes)
            title = None
            content = None
            if isinstance(doc, Texte):
                title = doc.titre or doc.titre_court
                content = doc.resume_ia
            elif isinstance(doc, Amendement):
                title = f"Amendement {doc.numero or doc.uid}"
                content = doc.resume_ia or _clean_html(doc.expose_sommaire)

            matched = _matching_profiles(
                doc_themes, [profile],
                title=title,
                content=content,
            )
            if matched:
                relevant_docs.append(doc)

        if not relevant_docs:
            continue

        # Appeler Claude pour scorer l'impact (max 10 docs par appel)
        analyses = await _analyze_impact_for_profile(
            profile, relevant_docs[:10]
        )

        if not analyses:
            continue

        # Creer les ImpactAlert
        from legix.agents.coordinateur import CoordinateurAgent
        coordinateur = CoordinateurAgent()

        for analysis in analyses:
            idx = analysis.get("doc_index", -1)
            if idx < 0 or idx >= len(relevant_docs):
                continue

            doc = relevant_docs[idx]
            level = analysis.get("impact_level", "medium")
            if level not in ("critical", "high", "medium", "low"):
                level = "medium"

            # Verifier qu'on n'a pas deja une alerte pour ce doc/profil
            existing_query = select(ImpactAlert).where(
                ImpactAlert.profile_id == profile.id,
            )
            if isinstance(doc, Texte):
                existing_query = existing_query.where(ImpactAlert.texte_uid == doc.uid)
            else:
                existing_query = existing_query.where(ImpactAlert.amendement_uid == doc.uid)

            existing = (await db.execute(existing_query)).scalar_one_or_none()
            if existing:
                continue

            # Themes matches
            doc_themes = parse_themes(doc.themes)
            client_sectors = json.loads(profile.sectors) if profile.sectors else []
            matched_themes = list(set(doc_themes) & set(client_sectors))

            alert = ImpactAlert(
                profile_id=profile.id,
                impact_level=level,
                impact_summary=analysis.get("impact_summary", ""),
                exposure_eur=analysis.get("exposure_eur"),
                matched_themes=json.dumps(matched_themes, ensure_ascii=False),
                is_threat=analysis.get("is_threat", True),
                is_read=False,
            )

            if isinstance(doc, Texte):
                alert.texte_uid = doc.uid
            elif isinstance(doc, Amendement):
                alert.amendement_uid = doc.uid
                if doc.texte_ref:
                    alert.texte_uid = doc.texte_ref

            db.add(alert)
            await db.flush()  # Pour obtenir alert.id
            alerts_created += 1

            logger.info(
                "ImpactAlert creee: %s [%s] pour %s (doc: %s)",
                level, "menace" if alert.is_threat else "opportunite",
                profile.name, doc.uid if hasattr(doc, 'uid') else "?",
            )

            # Orchestrer les alertes critical/high via le Coordinateur
            if level in ("critical", "high"):
                try:
                    await coordinateur.orchestrate(db, alert, profile)
                    orchestrated += 1
                    logger.info(
                        "Orchestration %s terminee pour %s — alert #%d",
                        level, profile.name, alert.id,
                    )
                except Exception as e:
                    logger.warning(
                        "Orchestration echouee pour alert #%d: %s",
                        alert.id, e,
                    )

            # Pour les alertes medium, creer une notification email simple
            elif level == "medium" and profile.email:
                db.add(NotificationQueue(
                    profile_id=profile.id,
                    channel="email",
                    priority="normal",
                    subject=f"[LegiX] Nouveau signal — {profile.name}",
                    body=(alert.impact_summary or "Nouveau signal detecte")[:500],
                    alert_id=alert.id,
                ))

        await db.commit()

    return {"alerts_created": alerts_created, "orchestrated": orchestrated}

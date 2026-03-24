"""Trigger agentique — suivi par texte, pas par amendement.

Quand un nouveau texte ou amendement enrichi arrive :
- Si le texte matche les secteurs d'un client → creer un TexteFollowUp + TexteBrief
- Si un amendement arrive sur un texte deja suivi → marquer le brief comme perime
- Les alertes individuelles ne sont creees que pour des cas exceptionnels
  (ex: amendement gouvernemental sur un texte parlementaire)
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.models import (
    Amendement,
    ClientProfile,
    Evenement,
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

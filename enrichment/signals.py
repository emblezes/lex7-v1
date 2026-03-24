"""Moteur de détection de signaux faibles — 7 détecteurs.

Adapté depuis LegisAPI pour SQLAlchemy async.
"""

import json
import logging
from datetime import datetime, timedelta

import anthropic
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.config import settings
from legix.core.models import Amendement, Organe, Signal, Texte

logger = logging.getLogger(__name__)


def _parse_themes(val: str | None) -> list:
    if not val:
        return []
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return []


def _get_adoption_score(amdt) -> float | None:
    if not amdt.score_impact:
        return None
    try:
        return json.loads(amdt.score_impact).get("adoption_score")
    except (json.JSONDecodeError, TypeError):
        return None


async def _signal_exists(session: AsyncSession, signal_type: str, texte_ref: str | None, hours: int = 48) -> bool:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    stmt = select(Signal).where(
        Signal.signal_type == signal_type,
        Signal.created_at >= cutoff,
    )
    if texte_ref:
        stmt = stmt.where(Signal.texte_ref == texte_ref)
    result = await session.execute(stmt)
    return result.scalars().first() is not None


def _generate_description(title: str, context: str) -> str | None:
    if not settings.anthropic_api_key:
        return None
    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.enrichment_model,
            max_tokens=200,
            system=(
                "Tu es un analyste en affaires publiques. "
                "Décris ce signal faible en 2-3 phrases concises et orientées action. "
                "Explique pourquoi c'est notable et ce que ça pourrait indiquer. "
                "Réponds directement sans préambule."
            ),
            messages=[{"role": "user", "content": f"Signal : {title}\n\nContexte :\n{context}"}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.warning("Erreur génération description signal: %s", e)
        return None


async def detect_convergence_transpartisane(session: AsyncSession) -> list[Signal]:
    """3+ groupes politiques amendant le même texte en 72h."""
    cutoff = datetime.utcnow() - timedelta(hours=72)
    signals = []

    stmt = select(Amendement.texte_ref, Amendement.groupe_ref).where(
        Amendement.date_depot >= cutoff,
        Amendement.texte_ref.isnot(None),
        Amendement.groupe_ref.isnot(None),
    )
    result = await session.execute(stmt)
    rows = result.all()

    texte_groupes: dict[str, set] = {}
    for row in rows:
        texte_groupes.setdefault(row.texte_ref, set()).add(row.groupe_ref)

    for texte_ref, groupes in texte_groupes.items():
        if len(groupes) < 3:
            continue
        if await _signal_exists(session, "convergence", texte_ref):
            continue

        texte_result = await session.execute(select(Texte).where(Texte.uid == texte_ref))
        texte = texte_result.scalars().first()
        titre = (texte.titre_court or texte.titre or texte_ref) if texte else texte_ref

        organes_result = await session.execute(select(Organe).where(Organe.uid.in_(groupes)))
        organes = organes_result.scalars().all()
        noms_groupes = [o.libelle_court or o.libelle for o in organes]

        title = f"Convergence transpartisane sur « {titre[:80]} »"
        context = f"{len(groupes)} groupes ({', '.join(noms_groupes)}) ont amendé ce texte en 72h."
        description = _generate_description(title, context)

        signal = Signal(
            signal_type="convergence", severity="high",
            title=title, description=description or context,
            themes=texte.themes if texte else None, texte_ref=texte_ref,
            data_snapshot=json.dumps({"groupes": noms_groupes, "nb_groupes": len(groupes)}, ensure_ascii=False),
        )
        signals.append(signal)
    return signals


async def detect_pic_amendements(session: AsyncSession) -> list[Signal]:
    """5+ amendements en 24h sur un texte dont la moyenne 7j < 2/jour."""
    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)
    signals = []

    stmt = (
        select(Amendement.texte_ref, func.count(Amendement.uid).label("cnt"))
        .where(Amendement.date_depot >= last_24h, Amendement.texte_ref.isnot(None))
        .group_by(Amendement.texte_ref)
        .having(func.count(Amendement.uid) >= 5)
    )
    result = await session.execute(stmt)

    for row in result.all():
        texte_ref, cnt_24h = row.texte_ref, row.cnt
        if await _signal_exists(session, "pic", texte_ref):
            continue

        stmt7 = select(func.count(Amendement.uid)).where(
            Amendement.texte_ref == texte_ref,
            Amendement.date_depot >= last_7d,
            Amendement.date_depot < last_24h,
        )
        cnt_7d = (await session.execute(stmt7)).scalar() or 0
        avg_7d = cnt_7d / 6
        if avg_7d >= 2:
            continue

        texte_result = await session.execute(select(Texte).where(Texte.uid == texte_ref))
        texte = texte_result.scalars().first()
        titre = (texte.titre_court or texte.titre or texte_ref) if texte else texte_ref

        title = f"Pic d'amendements sur « {titre[:80]} »"
        context = f"{cnt_24h} amendements en 24h (moyenne 7j : {avg_7d:.1f}/jour)."
        description = _generate_description(title, context)

        signal = Signal(
            signal_type="pic", severity="high" if cnt_24h >= 10 else "medium",
            title=title, description=description or context,
            themes=texte.themes if texte else None, texte_ref=texte_ref,
            data_snapshot=json.dumps({"count_24h": cnt_24h, "avg_7d": round(avg_7d, 2)}),
        )
        signals.append(signal)
    return signals


async def detect_reactivation_texte(session: AsyncSession) -> list[Signal]:
    """Texte dormant 30j qui reçoit 3+ amendements en 48h."""
    now = datetime.utcnow()
    last_48h = now - timedelta(hours=48)
    signals = []

    stmt = (
        select(Amendement.texte_ref, func.count(Amendement.uid).label("cnt"))
        .where(Amendement.date_depot >= last_48h, Amendement.texte_ref.isnot(None))
        .group_by(Amendement.texte_ref)
        .having(func.count(Amendement.uid) >= 3)
    )
    result = await session.execute(stmt)

    for row in result.all():
        texte_ref, cnt = row.texte_ref, row.cnt
        if await _signal_exists(session, "reactivation", texte_ref):
            continue

        stmt_prev = select(func.max(Amendement.date_depot)).where(
            Amendement.texte_ref == texte_ref, Amendement.date_depot < last_48h,
        )
        prev = (await session.execute(stmt_prev)).scalar()
        if prev is None:
            continue
        days_dormant = (last_48h - prev).days
        if days_dormant < 30:
            continue

        texte_result = await session.execute(select(Texte).where(Texte.uid == texte_ref))
        texte = texte_result.scalars().first()
        titre = (texte.titre_court or texte.titre or texte_ref) if texte else texte_ref

        title = f"Réactivation de « {titre[:80]} »"
        context = f"Texte dormant depuis {days_dormant} jours, {cnt} amendements en 48h."
        description = _generate_description(title, context)

        signal = Signal(
            signal_type="reactivation", severity="high",
            title=title, description=description or context,
            themes=texte.themes if texte else None, texte_ref=texte_ref,
            data_snapshot=json.dumps({"days_dormant": days_dormant, "count_48h": cnt}),
        )
        signals.append(signal)
    return signals


async def detect_theme_emergent(session: AsyncSession) -> list[Signal]:
    """Premier texte sur un thème depuis 6 mois."""
    now = datetime.utcnow()
    last_48h = now - timedelta(hours=48)
    six_months = now - timedelta(days=180)
    signals = []

    stmt = select(Texte).where(Texte.created_at >= last_48h, Texte.themes.isnot(None))
    result = await session.execute(stmt)

    for texte in result.scalars().all():
        themes = _parse_themes(texte.themes)
        for theme in themes:
            if await _signal_exists(session, "theme_emergent", texte.uid):
                continue

            pattern = f'%"{theme}"%'
            stmt_prev = select(Texte).where(
                Texte.themes.ilike(pattern),
                Texte.created_at >= six_months,
                Texte.created_at < last_48h,
            )
            prev = (await session.execute(stmt_prev)).scalars().first()
            if prev is not None:
                continue

            title = f"Thème émergent : {theme}"
            context = f"Premier texte sur « {theme} » depuis 6 mois : {texte.titre_court or texte.titre or texte.uid}"
            description = _generate_description(title, context)

            signal = Signal(
                signal_type="theme_emergent", severity="medium",
                title=title, description=description or context,
                themes=json.dumps([theme]), texte_ref=texte.uid,
                data_snapshot=json.dumps({"theme": theme, "texte_titre": texte.titre_court or texte.titre}, ensure_ascii=False),
            )
            signals.append(signal)
    return signals


async def detect_cluster_adoption(session: AsyncSession) -> list[Signal]:
    """3+ amendements sur un même texte avec adoption_score > 0.7."""
    now = datetime.utcnow()
    last_48h = now - timedelta(hours=48)
    signals = []

    stmt = select(Amendement).where(
        Amendement.created_at >= last_48h,
        Amendement.texte_ref.isnot(None),
        Amendement.score_impact.isnot(None),
    )
    result = await session.execute(stmt)

    texte_high: dict[str, list] = {}
    for a in result.scalars().all():
        score = _get_adoption_score(a)
        if score is not None and score > 0.7:
            texte_high.setdefault(a.texte_ref, []).append(a)

    for texte_ref, amdts in texte_high.items():
        if len(amdts) < 3:
            continue
        if await _signal_exists(session, "cluster_adoption", texte_ref):
            continue

        texte_result = await session.execute(select(Texte).where(Texte.uid == texte_ref))
        texte = texte_result.scalars().first()
        titre = (texte.titre_court or texte.titre or texte_ref) if texte else texte_ref

        title = f"Cluster haute adoption sur « {titre[:80]} »"
        context = f"{len(amdts)} amendements avec score d'adoption > 0.7."
        description = _generate_description(title, context)

        signal = Signal(
            signal_type="cluster_adoption", severity="high",
            title=title, description=description or context,
            themes=texte.themes if texte else None, texte_ref=texte_ref,
            amendement_refs=json.dumps([a.uid for a in amdts]),
            data_snapshot=json.dumps({"nb_amendements": len(amdts)}),
        )
        signals.append(signal)
    return signals


async def detect_acceleration_gouvernementale(session: AsyncSession) -> list[Signal]:
    """Amendement gouvernemental sur un texte jusqu'ici parlementaire."""
    now = datetime.utcnow()
    last_48h = now - timedelta(hours=48)
    signals = []

    stmt = select(Amendement).where(
        Amendement.created_at >= last_48h,
        Amendement.auteur_type == "Gouvernement",
        Amendement.texte_ref.isnot(None),
    )
    result = await session.execute(stmt)

    for a in result.scalars().all():
        if await _signal_exists(session, "acceleration_gouv", a.texte_ref):
            continue

        stmt_prev = select(Amendement).where(
            Amendement.texte_ref == a.texte_ref,
            Amendement.auteur_type == "Gouvernement",
            Amendement.created_at < last_48h,
        )
        prev = (await session.execute(stmt_prev)).scalars().first()
        if prev is not None:
            continue

        texte_result = await session.execute(select(Texte).where(Texte.uid == a.texte_ref))
        texte = texte_result.scalars().first()
        titre = (texte.titre_court or texte.titre or a.texte_ref) if texte else a.texte_ref

        title = f"Accélération gouvernementale sur « {titre[:80]} »"
        context = "Premier amendement du Gouvernement sur un texte jusqu'ici uniquement parlementaire."
        description = _generate_description(title, context)

        signal = Signal(
            signal_type="acceleration_gouv", severity="critical",
            title=title, description=description or context,
            themes=texte.themes if texte else None, texte_ref=a.texte_ref,
            amendement_refs=json.dumps([a.uid]),
            data_snapshot=json.dumps({"amendement_uid": a.uid, "texte_titre": titre}, ensure_ascii=False),
        )
        signals.append(signal)
    return signals


async def detect_echo_chambres(session: AsyncSession) -> list[Signal]:
    """Même thème traité AN + Sénat en 48h."""
    now = datetime.utcnow()
    last_48h = now - timedelta(hours=48)
    signals = []

    stmt = select(Texte).where(Texte.created_at >= last_48h, Texte.themes.isnot(None))
    result = await session.execute(stmt)

    an_themes: dict[str, list] = {}
    senat_themes: dict[str, list] = {}
    for t in result.scalars().all():
        themes = _parse_themes(t.themes)
        bucket = an_themes if t.source == "assemblee" else senat_themes
        for theme in themes:
            bucket.setdefault(theme, []).append(t)

    common = set(an_themes.keys()) & set(senat_themes.keys())
    for theme in common:
        if await _signal_exists(session, "echo_chambres", None, hours=72):
            continue

        an_texte = an_themes[theme][0]
        senat_texte = senat_themes[theme][0]

        title = f"Écho inter-chambres : {theme}"
        context = (
            f"AN : « {an_texte.titre_court or an_texte.titre or an_texte.uid} » / "
            f"Sénat : « {senat_texte.titre_court or senat_texte.titre or senat_texte.uid} »"
        )
        description = _generate_description(title, context)

        signal = Signal(
            signal_type="echo_chambres", severity="medium",
            title=title, description=description or context,
            themes=json.dumps([theme]),
            data_snapshot=json.dumps({"theme": theme, "an_texte": an_texte.uid, "senat_texte": senat_texte.uid}, ensure_ascii=False),
        )
        signals.append(signal)
    return signals


ALL_DETECTORS = [
    detect_convergence_transpartisane,
    detect_pic_amendements,
    detect_reactivation_texte,
    detect_theme_emergent,
    detect_cluster_adoption,
    detect_acceleration_gouvernementale,
    detect_echo_chambres,
]


async def detect_all(session: AsyncSession) -> int:
    """Lance tous les détecteurs et persiste les nouveaux signaux."""
    count = 0
    for detector in ALL_DETECTORS:
        try:
            new_signals = await detector(session)
            for signal in new_signals:
                session.add(signal)
                count += 1
            if new_signals:
                await session.commit()
        except Exception as e:
            await session.rollback()
            logger.exception("Erreur détecteur %s: %s", detector.__name__, e)

    if count:
        logger.info("Signaux faibles : %d nouveaux signaux détectés", count)
    return count

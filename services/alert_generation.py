"""Service de génération d'alertes d'impact réglementaire.

Extrait de legix/scripts/seed_profiles.py pour être réutilisable
depuis l'onboarding (route auth) ET le script de seed.

Usage :
    from legix.services.alert_generation import generate_alerts_for_profile
    asyncio.create_task(generate_alerts_for_profile(profile_id=42, job_id=7))
"""

import asyncio
import json
import logging
import re
from datetime import datetime

import anthropic
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.config import settings
from legix.core.database import async_session
from legix.core.models import (
    Acteur,
    Amendement,
    ClientProfile,
    ImpactAlert,
    OnboardingJob,
    Organe,
    Texte,
)

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────


def _clean_html(text: str | None) -> str:
    """Nettoie le HTML basique (balises) d'un expose/dispositif."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:300]


def _build_doc_context(
    texte: Texte | None = None,
    amendement: Amendement | None = None,
    auteur_name: str | None = None,
    groupe_name: str | None = None,
) -> dict:
    """Construit le contexte d'un document pour le prompt Claude."""
    ctx: dict = {}
    if amendement:
        ctx["type"] = "amendement"
        ctx["uid"] = amendement.uid
        ctx["numero"] = amendement.numero or ""
        ctx["article_vise"] = amendement.article_vise or ""
        ctx["etat"] = amendement.etat or ""
        ctx["sort"] = amendement.sort or ""
        ctx["resume_ia"] = amendement.resume_ia or ""
        ctx["expose_sommaire"] = _clean_html(amendement.expose_sommaire)[:200]
        ctx["themes"] = json.loads(amendement.themes) if amendement.themes else []
        ctx["date_depot"] = amendement.date_depot.isoformat() if amendement.date_depot else ""
        if auteur_name:
            ctx["auteur"] = auteur_name
        if groupe_name:
            ctx["groupe_politique"] = groupe_name
        if amendement.texte_ref:
            ctx["texte_ref"] = amendement.texte_ref
    elif texte:
        ctx["type"] = "texte"
        ctx["uid"] = texte.uid
        ctx["titre"] = texte.titre_court or texte.titre or ""
        ctx["type_libelle"] = texte.type_libelle or texte.type_code or ""
        ctx["resume_ia"] = texte.resume_ia or ""
        ctx["themes"] = json.loads(texte.themes) if texte.themes else []
        ctx["date_depot"] = texte.date_depot.isoformat() if texte.date_depot else ""
        ctx["source"] = texte.source or ""
        if texte.auteur_texte:
            ctx["auteur"] = texte.auteur_texte
    return ctx


def _build_contextual_actions(
    company: str,
    level: str,
    is_threat: bool,
    amendement: Amendement | None = None,
    auteur_name: str | None = None,
) -> list[dict]:
    """Construit une liste d'actions structurees (JSON-serialisable).

    Parametres simplifies par rapport au seed script : on passe
    directement le nom de l'entreprise au lieu du profile_config dict
    afin de decoupler de la structure PROFILES.
    """
    actions: list[dict] = []

    if level == "critical":
        if is_threat:
            actions.append({
                "type": "draft_note",
                "label": "Rediger une note d'impact COMEX sous 48h",
                "agent_prompt": (
                    f"Redige une note d'impact urgente pour le COMEX de {company} "
                    "analysant les risques de ce texte legislatif, les divisions "
                    "concernees et le chiffrage financier."
                ),
            })
            if auteur_name:
                actions.append({
                    "type": "draft_email",
                    "label": f"Contacter {auteur_name} (auteur de l'amendement)",
                    "agent_prompt": (
                        f"Redige un email professionnel a {auteur_name} pour solliciter "
                        f"un echange sur cet amendement au nom de {company}. "
                        "Ton diplomatique et constructif."
                    ),
                })
            actions.append({
                "type": "draft_note",
                "label": "Preparer un scenario de mitigation avec chiffrage",
                "agent_prompt": (
                    f"Redige un plan de mitigation structure pour {company} face a ce "
                    "risque reglementaire, incluant les options juridiques, le "
                    "calendrier et l'estimation des couts."
                ),
            })
            actions.append({
                "type": "monitor",
                "label": "Suivre le texte en commission et en seance",
                "agent_prompt": None,
            })
        else:
            actions.append({
                "type": "draft_note",
                "label": "Rediger une note d'opportunite pour la direction",
                "agent_prompt": (
                    f"Redige une note d'opportunite strategique pour la direction de "
                    f"{company} expliquant comment capitaliser sur ce texte legislatif "
                    "favorable."
                ),
            })
            if auteur_name:
                actions.append({
                    "type": "draft_email",
                    "label": f"Prendre contact avec {auteur_name} pour soutenir l'initiative",
                    "agent_prompt": (
                        f"Redige un email a {auteur_name} au nom de {company} pour "
                        "exprimer un soutien a cette initiative et proposer une "
                        "collaboration."
                    ),
                })
            actions.append({
                "type": "draft_note",
                "label": "Preparer un plan de captation avec calendrier",
                "agent_prompt": (
                    f"Redige un plan d'action pour {company} pour saisir cette "
                    "opportunite reglementaire, incluant les etapes, les "
                    "interlocuteurs et le budget."
                ),
            })
    elif level == "high":
        if is_threat:
            actions.append({
                "type": "draft_note",
                "label": f"Analyse d'impact detaillee pour {company}",
                "agent_prompt": (
                    f"Redige une analyse d'impact detaillee pour {company} evaluant "
                    "les couts de mise en conformite par division et les risques "
                    "juridiques."
                ),
            })
            actions.append({
                "type": "draft_amendment",
                "label": "Preparer un contre-amendement",
                "agent_prompt": (
                    f"Redige une proposition de contre-amendement au nom de {company} "
                    "pour attenuer l'impact negatif de ce texte, avec expose des motifs."
                ),
            })
            if auteur_name:
                actions.append({
                    "type": "monitor",
                    "label": f"Surveiller les interventions de {auteur_name}",
                    "agent_prompt": None,
                })
            actions.append({
                "type": "monitor",
                "label": "Suivre le texte en commission",
                "agent_prompt": None,
            })
        else:
            actions.append({
                "type": "draft_note",
                "label": "Evaluer les benefices potentiels par division",
                "agent_prompt": (
                    f"Redige une analyse des benefices potentiels de ce texte pour "
                    f"chaque division de {company}, avec estimation chiffree."
                ),
            })
            actions.append({
                "type": "draft_email",
                "label": "Identifier et contacter les interlocuteurs parlementaires",
                "agent_prompt": (
                    "Identifie les deputes et senateurs cles sur ce sujet et redige "
                    f"un courrier de prise de contact au nom de {company}."
                ),
            })
    elif level == "medium":
        actions.append({
            "type": "draft_note",
            "label": f"Inclure dans le briefing reglementaire de {company}",
            "agent_prompt": (
                f"Redige un paragraphe de briefing reglementaire pour {company} sur "
                "ce texte legislatif, a inclure dans le prochain rapport hebdomadaire."
            ),
        })
        actions.append({
            "type": "monitor",
            "label": "Suivre l'evolution du texte en commission",
            "agent_prompt": None,
        })
        if is_threat:
            actions.append({
                "type": "draft_note",
                "label": "Documenter l'impact potentiel",
                "agent_prompt": (
                    f"Redige une fiche de veille documentant l'impact potentiel de "
                    f"ce texte sur {company} pour le registre de suivi reglementaire."
                ),
            })
    else:  # low
        actions.append({
            "type": "monitor",
            "label": "Veille passive — remonter si le texte avance",
            "agent_prompt": None,
        })

    return actions


def _generate_batch_analyses(
    client: anthropic.Anthropic,
    profile: ClientProfile,
    documents: list[dict],
) -> list[dict]:
    """Appelle Claude pour generer des analyses d'impact pour un batch de documents.

    Contrairement a la version seed_profiles.py qui utilise un dict profile_config,
    celle-ci travaille directement depuis le modele ClientProfile et intègre le
    chiffre d'affaires pour calibrer les estimations d'exposition financiere.
    """
    company = profile.name
    description = profile.description or ""
    sectors = ", ".join(json.loads(profile.sectors)) if profile.sectors else ""
    divisions = ", ".join(json.loads(profile.business_lines)) if profile.business_lines else ""
    products = ", ".join(json.loads(profile.products)) if profile.products else ""
    context = profile.context_note or ""
    reg_focus = ", ".join(json.loads(profile.regulatory_focus)) if profile.regulatory_focus else ""
    risks = ", ".join(json.loads(profile.key_risks)) if profile.key_risks else ""
    opportunities = ", ".join(json.loads(profile.key_opportunities)) if profile.key_opportunities else ""

    # Calibration financiere basee sur le chiffre d'affaires
    ca = profile.chiffre_affaires
    if ca:
        ca_formatted = f"{ca:,.0f}".replace(",", " ")
        financial_calibration = (
            f"\nCALIBRATION FINANCIERE :\n"
            f"- Chiffre d'affaires annuel : {ca_formatted} EUR\n"
            f"- Les estimations d'exposure_eur doivent etre realistes par rapport a ce CA.\n"
            f"  Ex: pour un CA de {ca_formatted} EUR, une exposition critique pourrait aller "
            f"  de {ca * 0.001:,.0f} EUR a {ca * 0.05:,.0f} EUR.\n"
            f"- Adapte les fourchettes au niveau d'impact : critical > high > medium > low."
        )
    else:
        financial_calibration = (
            "\nCALIBRATION FINANCIERE :\n"
            "- Le chiffre d'affaires exact n'est pas disponible.\n"
            "- Estime l'exposure_eur en te basant sur le contexte strategique de "
            "l'entreprise, son secteur et la taille presumee.\n"
            "- Si le contexte mentionne un CA approximatif, utilise-le comme reference."
        )

    docs_json = json.dumps(documents, ensure_ascii=False, indent=2)

    prompt = f"""Tu es analyste senior en affaires publiques pour {company}.

CONTEXTE CLIENT :
- Entreprise : {company}
{f"- Description : {description}" if description else ""}
- Secteurs surveilles : {sectors}
- Divisions : {divisions}
- Produits cles : {products}
- Focus reglementaire : {reg_focus}
{f"- Risques reglementaires identifies : {risks}" if risks else ""}
{f"- Opportunites reglementaires : {opportunities}" if opportunities else ""}
- Note strategique : {context}
{financial_calibration}

MISSION : Pour chaque document legislatif ci-dessous, produis une analyse d'impact precise et professionnelle en francais impeccable.

REGLES D'ECRITURE :
- Francais soutenu, phrases completes et grammaticalement correctes
- Cite les divisions et produits specifiques de {company} concernes
- Sois factuel : mentionne l'auteur, le groupe politique, l'article vise quand disponibles
- Evalue l'urgence : le texte est-il en commission ? Adopte ? En examen ?
- Chiffre l'exposition financiere de maniere realiste (voir CALIBRATION FINANCIERE)

FORMAT DE REPONSE — un tableau JSON strict :
[
  {{
    "doc_index": 0,
    "impact_level": "critical|high|medium|low",
    "is_threat": true/false,
    "impact_summary": "• Premiere ligne = conclusion directe\\n• Deuxieme ligne = explication du contenu du texte\\n• Troisieme ligne = impact concret pour {company}\\n• Quatrieme ligne = ou en est le texte et urgence",
    "exposure_eur": 5000000
  }},
  ...
]

IMPORTANT :
- impact_summary utilise des bullet points separes par \\n, chaque ligne prefixee par •
- La premiere ligne est la conclusion (ex: "• Menace majeure pour la division Pharma Innovante")
- Les lignes suivantes expliquent (quoi, qui, impact, statut)
- exposure_eur est un entier en euros, calibre selon le CA de l'entreprise
- Reponds UNIQUEMENT avec le JSON, sans texte avant ni apres

DOCUMENTS A ANALYSER :
{docs_json}"""

    try:
        response = client.messages.create(
            model=settings.enrichment_model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        # Extraire le JSON meme si entoure de ```json
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return json.loads(text)
    except Exception as e:
        logger.error("Erreur API Claude pour batch: %s", e)
        return []


# ── Helpers DB ─────────────────────────────────────────────────────


async def _get_auteur_name(db: AsyncSession, auteur_ref: str | None) -> str | None:
    """Recupere le nom complet d'un acteur."""
    if not auteur_ref:
        return None
    acteur = await db.get(Acteur, auteur_ref)
    if acteur:
        return f"{acteur.prenom} {acteur.nom}"
    return None


async def _collect_documents(
    db: AsyncSession,
    profile: ClientProfile,
) -> list[dict]:
    """Collecte tous les documents correspondant au profil client.

    Cherche par :
    - sectors (thèmes principaux)
    - regulatory_focus (enjeux réglementaires spécifiques)
    - products (produits/services dans le texte brut)
    """
    sectors = json.loads(profile.sectors) if profile.sectors else []
    reg_focus = json.loads(profile.regulatory_focus) if profile.regulatory_focus else []
    products = json.loads(profile.products) if profile.products else []
    key_risks = json.loads(profile.key_risks) if profile.key_risks else []

    all_docs: list[dict] = []
    seen_uids: set[str] = set()  # Éviter les doublons

    # Construire les termes de recherche par catégorie
    # sectors → match sur themes JSON (format: '"secteur"')
    # regulatory_focus + products + key_risks → match sur resume_ia et texte brut (ILIKE)
    theme_patterns = [f'%"{s}"%' for s in sectors]
    text_keywords = reg_focus + products + key_risks

    # --- 1. Textes par thèmes (sectors) ---
    for pattern in theme_patterns:
        result = await db.execute(
            select(Texte)
            .where(Texte.themes.ilike(pattern))
            .order_by(func.random())
            .limit(8)
        )
        for texte in result.scalars().all():
            if texte.uid in seen_uids:
                continue
            seen_uids.add(texte.uid)
            ctx = _build_doc_context(texte=texte)
            all_docs.append({
                "doc_ctx": ctx,
                "texte": texte,
                "amendement": None,
                "sector": sectors[0] if sectors else "",
            })

    # --- 2. Textes par mots-clés métier (regulatory_focus + products) ---
    for keyword in text_keywords:
        kw_pattern = f"%{keyword}%"
        result = await db.execute(
            select(Texte)
            .where(
                Texte.resume_ia.ilike(kw_pattern)
                | Texte.titre.ilike(kw_pattern)
            )
            .order_by(func.random())
            .limit(5)
        )
        for texte in result.scalars().all():
            if texte.uid in seen_uids:
                continue
            seen_uids.add(texte.uid)
            ctx = _build_doc_context(texte=texte)
            all_docs.append({
                "doc_ctx": ctx,
                "texte": texte,
                "amendement": None,
                "sector": keyword,
            })

    # --- 3. Amendements par thèmes ---
    for pattern in theme_patterns:
        result = await db.execute(
            select(Amendement)
            .where(
                Amendement.themes.ilike(pattern),
                Amendement.resume_ia.isnot(None),
            )
            .order_by(func.random())
            .limit(20)
        )
        for amdt in result.scalars().all():
            if amdt.uid in seen_uids:
                continue
            seen_uids.add(amdt.uid)
            auteur_name = await _get_auteur_name(db, amdt.auteur_ref)
            if not auteur_name and amdt.auteur_nom:
                auteur_name = amdt.auteur_nom
            groupe_name = None
            if amdt.groupe_ref:
                g = await db.get(Organe, amdt.groupe_ref)
                if g:
                    groupe_name = g.libelle_court or g.libelle
            elif amdt.groupe_nom:
                groupe_name = amdt.groupe_nom
            ctx = _build_doc_context(
                amendement=amdt,
                auteur_name=auteur_name,
                groupe_name=groupe_name,
            )
            all_docs.append({
                "doc_ctx": ctx,
                "texte": None,
                "amendement": amdt,
                "sector": sectors[0] if sectors else "",
                "auteur_name": auteur_name,
            })

    # --- 4. Amendements par mots-clés métier ---
    for keyword in text_keywords:
        kw_pattern = f"%{keyword}%"
        result = await db.execute(
            select(Amendement)
            .where(
                Amendement.resume_ia.ilike(kw_pattern)
                | Amendement.expose_sommaire.ilike(kw_pattern),
                Amendement.resume_ia.isnot(None),
            )
            .order_by(func.random())
            .limit(10)
        )
        for amdt in result.scalars().all():
            if amdt.uid in seen_uids:
                continue
            seen_uids.add(amdt.uid)
            auteur_name = await _get_auteur_name(db, amdt.auteur_ref)
            if not auteur_name and amdt.auteur_nom:
                auteur_name = amdt.auteur_nom
            groupe_name = None
            if amdt.groupe_ref:
                g = await db.get(Organe, amdt.groupe_ref)
                if g:
                    groupe_name = g.libelle_court or g.libelle
            elif amdt.groupe_nom:
                groupe_name = amdt.groupe_nom
            ctx = _build_doc_context(
                amendement=amdt,
                auteur_name=auteur_name,
                groupe_name=groupe_name,
            )
            all_docs.append({
                "doc_ctx": ctx,
                "texte": None,
                "amendement": amdt,
                "sector": keyword,
                "auteur_name": auteur_name,
            })

    return all_docs


async def _update_job(
    db: AsyncSession,
    job_id: int,
    *,
    status: str | None = None,
    progress_current: int | None = None,
    progress_total: int | None = None,
    alerts_count: int | None = None,
    error_message: str | None = None,
    completed_at: datetime | None = None,
) -> None:
    """Met a jour l'OnboardingJob en base."""
    job = await db.get(OnboardingJob, job_id)
    if not job:
        return
    if status is not None:
        job.status = status
    if progress_current is not None:
        job.progress_current = progress_current
    if progress_total is not None:
        job.progress_total = progress_total
    if alerts_count is not None:
        job.alerts_count = alerts_count
    if error_message is not None:
        job.error_message = error_message
    if completed_at is not None:
        job.completed_at = completed_at
    await db.commit()


# ── Point d'entree principal ───────────────────────────────────────


async def generate_alerts_for_profile(profile_id: int, job_id: int) -> int:
    """Genere des alertes personnalisees pour un profil.

    Appele en background apres l'onboarding.
    Retourne le nombre d'alertes creees.
    """
    async with async_session() as db:
        try:
            # 1. Charger le profil
            profile = await db.get(ClientProfile, profile_id)
            if not profile:
                logger.error("Profil %d introuvable", profile_id)
                await _update_job(
                    db, job_id,
                    status="failed",
                    error_message=f"Profil {profile_id} introuvable",
                )
                return 0

            # 2. Verifier la cle API
            if not settings.anthropic_api_key:
                logger.error("ANTHROPIC_API_KEY non configuree")
                await _update_job(
                    db, job_id,
                    status="failed",
                    error_message="ANTHROPIC_API_KEY non configuree",
                )
                return 0

            claude_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

            # 3. Mettre a jour le job : statut generating
            await _update_job(db, job_id, status="generating")

            # 4. Collecter les documents matchants
            logger.info("Collecte documents pour %s (profil %d)...", profile.name, profile_id)
            all_docs = await _collect_documents(db, profile)

            if not all_docs:
                logger.warning("Aucun document trouve pour %s", profile.name)
                await _update_job(
                    db, job_id,
                    status="completed",
                    progress_current=0,
                    progress_total=0,
                    alerts_count=0,
                    completed_at=datetime.utcnow(),
                )
                return 0

            # 5. Traiter par batch de 10
            BATCH_SIZE = 10
            total_batches = (len(all_docs) + BATCH_SIZE - 1) // BATCH_SIZE
            count = 0

            await _update_job(
                db, job_id,
                progress_current=0,
                progress_total=total_batches,
            )

            for batch_idx in range(0, len(all_docs), BATCH_SIZE):
                batch = all_docs[batch_idx:batch_idx + BATCH_SIZE]
                batch_num = batch_idx // BATCH_SIZE + 1
                logger.info(
                    "  [%s] Batch %d/%d (%d docs)...",
                    profile.name, batch_num, total_batches, len(batch),
                )

                # Preparer les contextes pour Claude
                doc_contexts = []
                for i, item in enumerate(batch):
                    ctx = item["doc_ctx"].copy()
                    ctx["doc_index"] = i
                    doc_contexts.append(ctx)

                # Appel Claude (synchrone, dans un thread)
                analyses = await asyncio.to_thread(
                    _generate_batch_analyses, claude_client, profile, doc_contexts
                )

                if not analyses:
                    logger.warning("  Batch %d: pas de reponse Claude, skip", batch_num)
                    await _update_job(db, job_id, progress_current=batch_num)
                    continue

                # Creer les alertes
                for analysis in analyses:
                    idx = analysis.get("doc_index", -1)
                    if idx < 0 or idx >= len(batch):
                        continue
                    item = batch[idx]

                    level = analysis.get("impact_level", "medium")
                    if level not in ("critical", "high", "medium", "low"):
                        level = "medium"
                    is_threat = analysis.get("is_threat", True)
                    summary = analysis.get("impact_summary", "")
                    exposure = analysis.get("exposure_eur", 0)

                    # Actions structurees
                    auteur_name = item.get("auteur_name")
                    actions = _build_contextual_actions(
                        profile.name, level, is_threat,
                        amendement=item["amendement"],
                        auteur_name=auteur_name,
                    )

                    # Themes matches (sectors + regulatory_focus)
                    doc = item["texte"] or item["amendement"]
                    doc_themes: list[str] = []
                    if doc and doc.themes:
                        try:
                            doc_themes = json.loads(doc.themes)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    client_sectors = json.loads(profile.sectors) if profile.sectors else []
                    client_reg_focus = json.loads(profile.regulatory_focus) if profile.regulatory_focus else []
                    client_key_risks = json.loads(profile.key_risks) if profile.key_risks else []
                    client_terms = set(client_sectors + client_reg_focus + client_key_risks)
                    matched = list(set(doc_themes) & client_terms)
                    # Aussi matcher par mots-clés dans le résumé IA
                    doc_resume = (doc.resume_ia or "").lower() if doc else ""
                    for term in client_reg_focus + client_key_risks:
                        if term.lower() in doc_resume and term not in matched:
                            matched.append(term)

                    alert = ImpactAlert(
                        profile_id=profile.id,
                        impact_level=level,
                        impact_summary=summary,
                        exposure_eur=exposure,
                        matched_themes=json.dumps(matched, ensure_ascii=False),
                        action_required=json.dumps(actions, ensure_ascii=False),
                        is_threat=is_threat,
                        is_read=False,
                    )

                    if item["texte"]:
                        alert.texte_uid = item["texte"].uid
                    if item["amendement"]:
                        alert.amendement_uid = item["amendement"].uid
                        if item["amendement"].texte_ref:
                            alert.texte_uid = item["amendement"].texte_ref

                    db.add(alert)
                    count += 1

                await db.commit()

                # Mettre a jour la progression
                await _update_job(
                    db, job_id,
                    progress_current=batch_num,
                    alerts_count=count,
                )

                # Rate limiting
                await asyncio.sleep(0.3)

            # 6. Marquer le job comme termine
            await _update_job(
                db, job_id,
                status="completed",
                progress_current=total_batches,
                alerts_count=count,
                completed_at=datetime.utcnow(),
            )

            logger.info(
                "Generation terminee pour %s : %d alertes creees",
                profile.name, count,
            )
            return count

        except Exception as exc:
            logger.exception("Erreur generation alertes profil %d: %s", profile_id, exc)
            try:
                await _update_job(
                    db, job_id,
                    status="failed",
                    error_message=str(exc)[:500],
                )
            except Exception:
                logger.exception("Impossible de mettre a jour le job en erreur")
            return 0

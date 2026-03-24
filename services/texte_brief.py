"""Service TexteBrief — generation et mise a jour de dossiers texte consolides.

Quand un texte concerne un client, ce service genere un dossier complet :
cartographie des forces, amendements critiques, contacts cles, plan d'action.
"""

import json
import logging
import re
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from legix.core.models import (
    Acteur,
    Amendement,
    ClientProfile,
    Organe,
    TexteBrief,
    TexteFollowUp,
    Texte,
    amendement_cosignataires,
)
from legix.enrichment.scoring import _adoption_rate, compute_adoption_score

logger = logging.getLogger(__name__)


# --- Collecte du contexte complet ---


async def get_texte_full_context(
    db: AsyncSession, texte_uid: str, profile: ClientProfile
) -> dict:
    """Rassemble TOUTES les donnees necessaires pour generer un TexteBrief.

    Retourne un dict avec : texte, amendements (avec auteurs/groupes/scores),
    aggregats par groupe, aggregats par depute, profil client.
    """
    # Texte
    texte = await db.get(Texte, texte_uid)
    if not texte:
        return {"error": f"Texte {texte_uid} non trouve"}

    # Amendements avec relations
    result = await db.execute(
        select(Amendement)
        .options(joinedload(Amendement.auteur), joinedload(Amendement.groupe))
        .where(Amendement.texte_ref == texte_uid)
        .order_by(Amendement.numero)
    )
    amdts = result.unique().scalars().all()

    # Scores adoption (top 50 par pertinence)
    amdt_data = []
    for a in amdts:
        score = 0.5
        try:
            score = await compute_adoption_score(db, a)
        except Exception:
            pass

        auteur_nom = None
        if a.auteur:
            auteur_nom = f"{a.auteur.prenom or ''} {a.auteur.nom or ''}".strip()

        groupe_nom = None
        groupe_uid = None
        if a.groupe:
            groupe_nom = a.groupe.libelle_court or a.groupe.libelle
            groupe_uid = a.groupe.uid

        # Cosignataires
        cosig_result = await db.execute(
            select(func.count()).where(
                amendement_cosignataires.c.amendement_uid == a.uid
            )
        )
        nb_cosig = cosig_result.scalar() or 0

        amdt_data.append({
            "uid": a.uid,
            "numero": a.numero,
            "article_vise": a.article_vise,
            "etat": a.etat,
            "sort": a.sort,
            "auteur_uid": a.auteur_ref,
            "auteur_nom": auteur_nom or a.auteur_nom,
            "auteur_type": a.auteur_type,
            "groupe_uid": groupe_uid or a.groupe_ref,
            "groupe_nom": groupe_nom or a.groupe_nom,
            "themes": json.loads(a.themes) if a.themes else [],
            "resume_ia": a.resume_ia,
            "dispositif_extrait": (a.dispositif or "")[:300],
            "adoption_score": round(score, 3),
            "nb_cosignataires": nb_cosig,
        })

    # Aggregats par groupe
    groupe_agg = {}
    for ad in amdt_data:
        gnom = ad["groupe_nom"] or "Inconnu"
        if gnom not in groupe_agg:
            groupe_agg[gnom] = {
                "groupe_uid": ad["groupe_uid"],
                "nb_amendements": 0,
                "nb_adoptes": 0,
                "deputes": set(),
            }
        groupe_agg[gnom]["nb_amendements"] += 1
        if ad["sort"] and "adopt" in ad["sort"].lower():
            groupe_agg[gnom]["nb_adoptes"] += 1
        if ad["auteur_nom"]:
            groupe_agg[gnom]["deputes"].add(ad["auteur_nom"])

    groupes_summary = [
        {
            "groupe": g,
            "groupe_uid": s["groupe_uid"],
            "nb_amendements": s["nb_amendements"],
            "nb_adoptes": s["nb_adoptes"],
            "nb_deputes": len(s["deputes"]),
            "deputes": list(s["deputes"]),
        }
        for g, s in sorted(groupe_agg.items(), key=lambda x: -x[1]["nb_amendements"])
    ]

    # Aggregats par depute
    depute_agg = {}
    for ad in amdt_data:
        nom = ad["auteur_nom"] or "Inconnu"
        if nom not in depute_agg:
            depute_agg[nom] = {
                "uid": ad["auteur_uid"],
                "groupe": ad["groupe_nom"],
                "nb_amendements": 0,
                "nb_adoptes": 0,
            }
        depute_agg[nom]["nb_amendements"] += 1
        if ad["sort"] and "adopt" in ad["sort"].lower():
            depute_agg[nom]["nb_adoptes"] += 1

    deputes_summary = [
        {
            "nom": n,
            "uid": s["uid"],
            "groupe": s["groupe"],
            "nb_amendements": s["nb_amendements"],
            "taux_adoption": round(
                _adoption_rate(s["nb_adoptes"], s["nb_amendements"]), 3
            ),
        }
        for n, s in sorted(depute_agg.items(), key=lambda x: -x[1]["nb_amendements"])
    ]

    # Profil client
    def _parse(val):
        if not val:
            return []
        try:
            return json.loads(val) if isinstance(val, str) else val
        except (json.JSONDecodeError, TypeError):
            return []

    client_ctx = {
        "name": profile.name,
        "sectors": _parse(profile.sectors),
        "business_lines": _parse(profile.business_lines),
        "products": _parse(profile.products),
        "regulatory_focus": _parse(profile.regulatory_focus),
        "context_note": profile.context_note,
        "description": profile.description,
        "chiffre_affaires": profile.chiffre_affaires,
        "effectifs": profile.effectifs,
        "key_risks": _parse(profile.key_risks),
    }

    return {
        "texte": {
            "uid": texte.uid,
            "titre": texte.titre_court or texte.titre,
            "type_code": texte.type_code,
            "date_depot": str(texte.date_depot) if texte.date_depot else None,
            "themes": json.loads(texte.themes) if texte.themes else [],
            "resume_ia": texte.resume_ia,
        },
        "amendements": amdt_data,
        "nb_amendements": len(amdt_data),
        "groupes": groupes_summary,
        "nb_groupes": len(groupes_summary),
        "deputes": deputes_summary,
        "nb_deputes": len(deputes_summary),
        "client": client_ctx,
    }


# --- Generation du brief ---


def _build_brief_task(context: dict) -> str:
    """Construit le message tache pour le BriefAgent a partir du contexte complet."""
    texte = context["texte"]
    client = context["client"]

    # Trier amendements par score adoption desc, prendre top 20
    amdts_sorted = sorted(
        context["amendements"],
        key=lambda a: a["adoption_score"],
        reverse=True,
    )[:20]

    lines = [
        f"TEXTE A ANALYSER POUR {client['name']}",
        f"",
        f"=== TEXTE ===",
        f"UID: {texte['uid']}",
        f"Titre: {texte['titre']}",
        f"Type: {texte['type_code']}",
        f"Date depot: {texte['date_depot']}",
        f"Themes: {', '.join(texte['themes'])}",
        f"Resume: {texte['resume_ia'] or 'Non disponible'}",
        f"",
        f"=== STATISTIQUES ===",
        f"Total amendements: {context['nb_amendements']}",
        f"Groupes impliques: {context['nb_groupes']}",
        f"Deputes actifs: {context['nb_deputes']}",
        f"",
        f"=== GROUPES PARLEMENTAIRES ===",
    ]

    for g in context["groupes"]:
        lines.append(
            f"  {g['groupe']}: {g['nb_amendements']} amendements "
            f"({g['nb_adoptes']} adoptes), {g['nb_deputes']} deputes "
            f"({', '.join(g['deputes'][:3])})"
        )

    lines.append("")
    lines.append("=== DEPUTES LES PLUS ACTIFS ===")
    for d in context["deputes"][:8]:
        lines.append(
            f"  {d['nom']} ({d['groupe']}): {d['nb_amendements']} amendements, "
            f"taux adoption {d['taux_adoption']}"
        )

    lines.append("")
    lines.append("=== TOP 20 AMENDEMENTS (par score adoption) ===")
    for a in amdts_sorted:
        lines.append(
            f"  {a['numero']} | score={a['adoption_score']} | "
            f"auteur={a['auteur_nom']} ({a['groupe_nom']}) | "
            f"etat={a['etat'] or a['sort']} | cosig={a['nb_cosignataires']} | "
            f"resume={a['resume_ia'] or a['dispositif_extrait'][:100]}"
        )

    lines.append("")
    lines.append(f"=== PROFIL CLIENT : {client['name']} ===")
    lines.append(f"Secteurs: {', '.join(client['sectors'])}")
    lines.append(f"Lignes de metier: {', '.join(client['business_lines'])}")
    lines.append(f"Produits: {', '.join(client['products'])}")
    lines.append(f"Enjeux reglementaires: {', '.join(client['regulatory_focus'])}")
    if client["context_note"]:
        lines.append(f"Contexte: {client['context_note']}")
    if client["description"]:
        lines.append(f"Description: {client['description'][:300]}")
    if client["chiffre_affaires"]:
        lines.append(f"CA: {client['chiffre_affaires']} EUR")
    if client["effectifs"]:
        lines.append(f"Effectifs: {client['effectifs']}")

    lines.append("")
    lines.append("MISSION : Produis le JSON d'analyse consolidee de ce texte pour ce client.")

    return "\n".join(lines)


def _parse_brief_response(raw: str) -> dict:
    """Parse la reponse JSON du BriefAgent."""
    # Extraire le JSON de la reponse (peut etre entoure de ```json ... ```)
    json_match = re.search(r'```json\s*(.*?)\s*```', raw, re.DOTALL)
    if json_match:
        candidate = json_match.group(1)
    else:
        # Tenter de trouver le premier { ... } valide (en comptant les accolades)
        start = raw.find('{')
        if start >= 0:
            depth = 0
            end = start
            for i in range(start, len(raw)):
                if raw[i] == '{':
                    depth += 1
                elif raw[i] == '}':
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            candidate = raw[start:end + 1]
        else:
            candidate = raw

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        logger.warning("Impossible de parser la reponse JSON du BriefAgent, tentative nettoyage")
        # Nettoyer les caracteres de controle et retenter
        cleaned = re.sub(r'[\x00-\x1f]+', ' ', candidate)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Echec definitif du parsing — fallback texte brut")
            return {
                "executive_summary": raw[:500],
                "impact_level": "medium",
                "is_threat": True,
                "exposure_eur": None,
                "force_map": [],
                "critical_amendments": [],
                "key_contacts": [],
                "action_plan": [],
            }


async def generate_texte_brief(
    db: AsyncSession,
    texte_uid: str,
    profile: ClientProfile,
    followup: TexteFollowUp | None = None,
) -> TexteBrief:
    """Genere ou met a jour un TexteBrief pour un texte + profil client.

    1. Collecte le contexte complet (texte, amendements, groupes, deputes, client)
    2. Appelle le BriefAgent pour l'analyse consolidee
    3. Cree ou met a jour le TexteBrief en DB
    """
    from legix.agents.brief import BriefAgent

    # Verifier si un brief existe deja
    result = await db.execute(
        select(TexteBrief).where(
            TexteBrief.profile_id == profile.id,
            TexteBrief.texte_uid == texte_uid,
        )
    )
    existing = result.scalar_one_or_none()

    # Collecter le contexte
    context = await get_texte_full_context(db, texte_uid, profile)
    if "error" in context:
        logger.error("Contexte texte en erreur: %s", context["error"])
        raise ValueError(context["error"])

    # Pas d'amendements = pas de brief
    if context["nb_amendements"] == 0:
        logger.info("Texte %s sans amendements — skip brief", texte_uid)
        raise ValueError(f"Texte {texte_uid} n'a pas d'amendements")

    # Construire la tache et lancer l'agent
    task = _build_brief_task(context)

    # Profil pour le system prompt enrichi
    profile_dict = {
        "name": profile.name,
        "sectors": context["client"]["sectors"],
        "business_lines": context["client"]["business_lines"],
    }

    agent = BriefAgent()
    raw_response = await agent.run(task, db=db, profile=profile_dict)

    # Parser la reponse
    parsed = _parse_brief_response(raw_response)

    if existing:
        # Mise a jour
        existing.executive_summary = parsed.get("executive_summary")
        existing.force_map = json.dumps(parsed.get("force_map", []), ensure_ascii=False)
        existing.critical_amendments = json.dumps(parsed.get("critical_amendments", []), ensure_ascii=False)
        existing.key_contacts = json.dumps(parsed.get("key_contacts", []), ensure_ascii=False)
        existing.action_plan = json.dumps(parsed.get("action_plan", []), ensure_ascii=False)
        existing.exposure_eur = parsed.get("exposure_eur")
        existing.impact_level = parsed.get("impact_level", "medium")
        existing.is_threat = parsed.get("is_threat", True)
        existing.nb_amendements_analyzed = context["nb_amendements"]
        existing.nb_groupes = context["nb_groupes"]
        existing.nb_deputes = context["nb_deputes"]
        existing.version = (existing.version or 0) + 1
        existing.raw_agent_response = raw_response
        existing.updated_at = datetime.utcnow()
        if followup:
            existing.followup_id = followup.id
        await db.commit()
        await db.refresh(existing)
        logger.info(
            "TexteBrief mis a jour (v%d) pour %s / %s — %s",
            existing.version, profile.name, texte_uid, existing.impact_level,
        )
        return existing
    else:
        # Creation
        brief = TexteBrief(
            profile_id=profile.id,
            texte_uid=texte_uid,
            followup_id=followup.id if followup else None,
            executive_summary=parsed.get("executive_summary"),
            force_map=json.dumps(parsed.get("force_map", []), ensure_ascii=False),
            critical_amendments=json.dumps(parsed.get("critical_amendments", []), ensure_ascii=False),
            key_contacts=json.dumps(parsed.get("key_contacts", []), ensure_ascii=False),
            action_plan=json.dumps(parsed.get("action_plan", []), ensure_ascii=False),
            exposure_eur=parsed.get("exposure_eur"),
            impact_level=parsed.get("impact_level", "medium"),
            is_threat=parsed.get("is_threat", True),
            nb_amendements_analyzed=context["nb_amendements"],
            nb_groupes=context["nb_groupes"],
            nb_deputes=context["nb_deputes"],
            version=1,
            raw_agent_response=raw_response,
        )
        db.add(brief)
        await db.commit()
        await db.refresh(brief)
        logger.info(
            "TexteBrief cree pour %s / %s — %s (%d amdts, %d groupes, %d deputes)",
            profile.name, texte_uid, brief.impact_level,
            brief.nb_amendements_analyzed, brief.nb_groupes, brief.nb_deputes,
        )
        return brief

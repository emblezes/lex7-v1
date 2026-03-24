"""Routes livrables streaming — generation SSE en temps reel."""

import json
import logging
from datetime import datetime

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.api.deps import get_current_profile, get_db
from legix.core.config import settings
from legix.core.models import (
    ActionTask,
    ClientProfile,
    ImpactAlert,
    Livrable,
    TexteBrief,
)

logger = logging.getLogger(__name__)
router = APIRouter()


LIVRABLE_PROMPTS = {
    "note_comex": (
        "Redige une NOTE D'IMPACT COMEX professionnelle.\n"
        "Format structure : Contexte / Analyse d'impact / Divisions concernees / "
        "Chiffrage / Recommandations.\n"
        "Ton : professionnel, factuel, oriente decision. Longueur : 1-2 pages."
    ),
    "email": (
        "Redige un EMAIL PARLEMENTAIRE professionnel.\n"
        "Format : salutation formelle / contexte / position de l'entreprise / "
        "proposition de rencontre.\n"
        "Ton : diplomatique, constructif, respectueux. Longueur : 10-15 lignes."
    ),
    "amendement": (
        "Redige un CONTRE-AMENDEMENT.\n"
        "Format : article vise / dispositif propose / expose des motifs.\n"
        "Ton : juridique, precis, argumente."
    ),
    "fiche_position": (
        "Redige une FICHE DE POSITION.\n"
        "Format : Contexte / Position / Arguments / Propositions alternatives.\n"
        "Ton : synthetique, argumente, operationnel. Longueur : 1 page."
    ),
}

LIVRABLE_TITLES = {
    "note_comex": "Note d'impact COMEX",
    "email": "Email parlementaire",
    "amendement": "Contre-amendement",
    "fiche_position": "Fiche de position",
}


class StreamLivrableRequest(BaseModel):
    type: str  # note_comex / email / amendement / fiche_position


async def _build_livrable_prompt(
    db: AsyncSession,
    task: ActionTask,
    livrable_type: str,
    profile: ClientProfile,
) -> tuple[str, str]:
    """Construit le prompt et le system prompt pour la generation streamee."""
    # System prompt avec contexte client
    from legix.agents.chat_tools import get_client_profile
    profile_dict = await get_client_profile(db, profile_id=profile.id)

    from legix.agents.redacteur import REDACTEUR_SYSTEM
    from legix.agents.base import BaseAgent
    dummy = BaseAgent()
    dummy.system_prompt = REDACTEUR_SYSTEM
    system = dummy._build_system_prompt(profile_dict)

    # User prompt
    prompt_parts = []
    template = LIVRABLE_PROMPTS.get(livrable_type, LIVRABLE_PROMPTS["note_comex"])
    prompt_parts.append(template)
    prompt_parts.append("")
    prompt_parts.append(f"ACTION : {task.label}")
    if task.rationale:
        prompt_parts.append(f"JUSTIFICATION : {task.rationale}")

    if task.texte_uid:
        result = await db.execute(
            select(TexteBrief).where(
                TexteBrief.profile_id == task.profile_id,
                TexteBrief.texte_uid == task.texte_uid,
            )
        )
        brief = result.scalar_one_or_none()
        if brief:
            prompt_parts.append(f"\nDOSSIER : {task.texte_uid}")
            prompt_parts.append(f"IMPACT : {brief.impact_level}")
            if brief.executive_summary:
                prompt_parts.append(f"RESUME : {brief.executive_summary[:500]}")
            if brief.exposure_eur:
                prompt_parts.append(f"EXPOSITION : {brief.exposure_eur:,.0f} EUR")

            # Amendements critiques
            try:
                crit_amdts = json.loads(brief.critical_amendments or "[]")
                if crit_amdts:
                    prompt_parts.append("\nAMENDEMENTS CRITIQUES :")
                    for ca in crit_amdts[:5]:
                        prompt_parts.append(
                            f"  - {ca.get('numero', '?')} par {ca.get('auteur', '?')} "
                            f"({ca.get('groupe', '?')}): {ca.get('resume', '')[:100]}"
                        )
            except (json.JSONDecodeError, TypeError):
                pass

            # Contacts cles
            try:
                contacts = json.loads(brief.key_contacts or "[]")
                if contacts:
                    prompt_parts.append("\nCONTACTS CLES :")
                    for c in contacts[:5]:
                        prompt_parts.append(
                            f"  - {c.get('nom', '?')} ({c.get('groupe', '?')}): "
                            f"{c.get('why_relevant', '')[:80]}"
                        )
            except (json.JSONDecodeError, TypeError):
                pass

    if task.alert_id:
        alert = await db.get(ImpactAlert, task.alert_id)
        if alert:
            prompt_parts.append(f"\nALERTE : {alert.impact_summary or ''}")

    if task.target_acteur_uids:
        try:
            uids = json.loads(task.target_acteur_uids)
            if uids:
                # Charger les noms des acteurs
                from legix.core.models import Acteur
                names = []
                for uid in uids[:5]:
                    acteur = await db.get(Acteur, uid)
                    if acteur:
                        names.append(f"{acteur.prenom or ''} {acteur.nom or ''}".strip())
                if names:
                    prompt_parts.append(f"DESTINATAIRES / ACTEURS CIBLES : {', '.join(names)}")
        except (json.JSONDecodeError, TypeError):
            pass

    prompt_parts.append(f"\nCLIENT : {profile.name}")
    prompt_parts.append("\nProduis le document complet en markdown, pret a l'emploi.")

    return system, "\n".join(prompt_parts)


@router.post("/actions/{action_id}/generate-livrable/stream")
async def stream_generate_livrable(
    action_id: int,
    body: StreamLivrableRequest,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Genere un livrable en streaming SSE — le texte arrive token par token."""
    task = await db.get(ActionTask, action_id)
    if not task or task.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Action introuvable")

    system_prompt, user_prompt = await _build_livrable_prompt(
        db, task, body.type, profile,
    )

    # Pre-creer le livrable en DB (status: generating)
    title = LIVRABLE_TITLES.get(body.type, body.type)
    if task.label:
        title = f"{title} — {task.label[:60]}"

    livrable = Livrable(
        action_id=action_id,
        profile_id=profile.id,
        type=body.type,
        title=title,
        content="",
        format="markdown",
        status="generating",
    )
    db.add(livrable)
    await db.commit()
    await db.refresh(livrable)

    livrable_id = livrable.id

    async def event_stream():
        """Generateur SSE qui streame la reponse Claude."""
        import time
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        full_content = ""

        # Envoyer l'event d'init avec l'ID du livrable
        yield f"data: {json.dumps({'type': 'init', 'livrable_id': livrable_id, 'title': title})}\n\n"

        # Retry avec backoff pour les erreurs 529 (overloaded)
        max_retries = 3
        last_error = None
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    wait = 2 ** attempt
                    yield f"data: {json.dumps({'type': 'status', 'message': f'API surchargee, nouvelle tentative dans {wait}s...'})}\n\n"
                    time.sleep(wait)

                with client.messages.stream(
                    model=settings.enrichment_model,
                    max_tokens=4096,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                ) as stream:
                    for text in stream.text_stream:
                        full_content += text
                        yield f"data: {json.dumps({'type': 'delta', 'text': text})}\n\n"

                last_error = None
                break  # Succes — sortir de la boucle retry
            except anthropic.APIStatusError as e:
                last_error = e
                if e.status_code == 529 and attempt < max_retries - 1:
                    continue  # Retry
                # Autre erreur ou dernier retry — on sort

        if last_error:
            logger.error("Erreur streaming livrable apres %d tentatives: %s", max_retries, last_error)
            from legix.core.database import async_session
            async with async_session() as save_db:
                saved = await save_db.get(Livrable, livrable_id)
                if saved:
                    saved.status = "failed"
                    saved.content = full_content or f"Erreur: {str(last_error)}"
                    await save_db.commit()
            yield f"data: {json.dumps({'type': 'error', 'message': str(last_error)})}\n\n"
            return

        # Sauvegarder le contenu complet en DB
        try:
            from legix.core.database import async_session
            async with async_session() as save_db:
                saved = await save_db.get(Livrable, livrable_id)
                if saved:
                    saved.content = full_content
                    saved.status = "draft"
                    saved.updated_at = datetime.utcnow()
                    await save_db.commit()
        except Exception as e:
            logger.error("Erreur sauvegarde livrable: %s", e)

        yield f"data: {json.dumps({'type': 'done', 'livrable_id': livrable_id, 'content_length': len(full_content)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class SendEmailRequest(BaseModel):
    to: str  # adresse email
    subject: str | None = None
    attach_pdf: bool = True


@router.post("/livrables/{livrable_id}/send-email")
async def send_livrable_email(
    livrable_id: int,
    body: SendEmailRequest,
    profile: ClientProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Pre-redige et prepare l'envoi d'un email avec le livrable en PJ.

    Retourne le mailto: link ou les donnees pour un client email.
    Pour un vrai envoi SMTP, il faudra configurer les credentials.
    """
    livrable = await db.get(Livrable, livrable_id)
    if not livrable or livrable.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Livrable introuvable")

    if not livrable.content:
        raise HTTPException(status_code=400, detail="Aucun contenu a envoyer")

    # Generer le PDF
    from legix.export.pdf import export_impact_note_pdf
    pdf_bytes = export_impact_note_pdf(
        company_name=profile.name or "Client",
        alert_summary=livrable.title or "Livrable",
        impact_level="medium",
        content=livrable.content,
        metadata={"date": str(livrable.created_at), "type": livrable.type},
    )

    # Subject par defaut
    subject = body.subject or livrable.title or "Document LegiX"

    # Extraire les 3 premieres lignes comme corps email
    lines = [l.strip() for l in livrable.content.split("\n") if l.strip() and not l.startswith("#")]
    email_body = "\n".join(lines[:3]) + "\n\n[Document complet en piece jointe]"

    import base64
    pdf_b64 = base64.b64encode(pdf_bytes).decode()

    # Marquer comme envoye
    livrable.status = "sent"
    await db.commit()

    return {
        "status": "prepared",
        "to": body.to,
        "subject": subject,
        "body": email_body,
        "pdf_filename": f"livrable_{livrable_id}.pdf",
        "pdf_base64": pdf_b64,
        "pdf_size_bytes": len(pdf_bytes),
        "mailto_link": (
            f"mailto:{body.to}"
            f"?subject={subject.replace(' ', '%20')}"
            f"&body={email_body[:200].replace(' ', '%20').replace(chr(10), '%0A')}"
        ),
    }

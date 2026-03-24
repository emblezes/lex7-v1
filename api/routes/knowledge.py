"""Routes API knowledge base — upload, liste, recherche documents client."""

import json
import logging
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.database import get_db
from legix.core.models import ClientDocument

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ── Schemas ──────────────────────────────────────────────────────

class DocumentResponse(BaseModel):
    id: int
    profile_id: int
    doc_type: str
    title: str
    summary: str | None
    themes: list[str]
    key_positions: list[dict] | None
    mentioned_stakeholders: list[str]
    file_name: str | None
    created_at: str

    class Config:
        from_attributes = True


class SearchResult(BaseModel):
    document_id: int
    document_title: str
    doc_type: str
    chunk_text: str
    chunk_idx: int
    score: float
    themes: list[str]


class IngestTextRequest(BaseModel):
    title: str
    doc_type: str = "internal_note"
    content: str


# ── Upload fichier ───────────────────────────────────────────────

@router.post("/profiles/{profile_id}/documents/upload", response_model=DocumentResponse)
async def upload_document(
    profile_id: int,
    file: UploadFile = File(...),
    doc_type: str = Form("rapport"),
    title: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Upload un fichier et l'ingere dans la knowledge base.

    Formats acceptes : .pdf, .docx, .txt, .md, .html
    Le document est automatiquement : extrait, enrichi par IA, chunke et indexe.
    """
    # Valider le format
    allowed_extensions = {".pdf", ".docx", ".doc", ".txt", ".md", ".html"}
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Format non supporte: {suffix}. Formats: {', '.join(allowed_extensions)}",
        )

    # Sauvegarder dans un fichier temporaire
    upload_dir = Path("data/uploads") / str(profile_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / file.filename
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Titre par defaut = nom du fichier
    if not title:
        title = Path(file.filename).stem.replace("_", " ").replace("-", " ").title()

    # Ingerer
    from legix.knowledge.document_ingestion import ingest_document

    try:
        doc = await ingest_document(
            db,
            profile_id=profile_id,
            doc_type=doc_type,
            title=title,
            file_path=str(file_path),
            file_name=file.filename,
        )
    except Exception as e:
        logger.error("Erreur ingestion: %s", e)
        raise HTTPException(status_code=500, detail=f"Erreur d'ingestion: {str(e)}")

    return _doc_to_response(doc)


# ── Ingestion texte brut ─────────────────────────────────────────

@router.post("/profiles/{profile_id}/documents/text", response_model=DocumentResponse)
async def ingest_text(
    profile_id: int,
    request: IngestTextRequest,
    db: AsyncSession = Depends(get_db),
):
    """Ingere du texte brut dans la knowledge base (pas besoin de fichier).

    Utile pour : emails, notes de reunion, position papers copiés-collés.
    """
    from legix.knowledge.document_ingestion import ingest_document

    try:
        doc = await ingest_document(
            db,
            profile_id=profile_id,
            doc_type=request.doc_type,
            title=request.title,
            content=request.content,
        )
    except Exception as e:
        logger.error("Erreur ingestion texte: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    return _doc_to_response(doc)


# ── Liste des documents ──────────────────────────────────────────

@router.get("/profiles/{profile_id}/documents", response_model=list[DocumentResponse])
async def list_documents(
    profile_id: int,
    doc_type: str | None = None,
    theme: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Liste les documents de la knowledge base d'un client."""
    stmt = select(ClientDocument).where(ClientDocument.profile_id == profile_id)
    if doc_type:
        stmt = stmt.where(ClientDocument.doc_type == doc_type)
    stmt = stmt.order_by(ClientDocument.created_at.desc())

    result = await db.execute(stmt)
    docs = result.scalars().all()

    responses = []
    for doc in docs:
        if theme:
            doc_themes = json.loads(doc.themes) if doc.themes else []
            if theme.lower() not in [t.lower() for t in doc_themes]:
                continue
        responses.append(_doc_to_response(doc))

    return responses


# ── Detail document ──────────────────────────────────────────────

@router.get("/profiles/{profile_id}/documents/{doc_id}")
async def get_document(
    profile_id: int,
    doc_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Detail complet d'un document avec son contenu."""
    doc = await db.get(ClientDocument, doc_id)
    if not doc or doc.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="Document non trouve")

    resp = _doc_to_response(doc)
    return {
        **resp.model_dump(),
        "content": doc.content,
        "file_path": doc.file_path,
    }


# ── Suppression document ────────────────────────────────────────

@router.delete("/profiles/{profile_id}/documents/{doc_id}")
async def delete_document(
    profile_id: int,
    doc_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Supprime un document et ses chunks de la knowledge base."""
    doc = await db.get(ClientDocument, doc_id)
    if not doc or doc.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="Document non trouve")

    # Supprimer les chunks
    from legix.knowledge.models import DocumentChunk
    chunks_result = await db.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == doc_id)
    )
    for chunk in chunks_result.scalars():
        await db.delete(chunk)

    # Supprimer le document
    await db.delete(doc)
    await db.commit()

    return {"status": "deleted", "document_id": doc_id}


# ── Recherche semantique ────────────────────────────────────────

@router.get("/profiles/{profile_id}/search", response_model=list[SearchResult])
async def search_documents(
    profile_id: int,
    q: str = Query(..., min_length=2, description="Terme de recherche"),
    top_k: int = Query(5, ge=1, le=20),
    theme: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Recherche semantique dans la knowledge base du client.

    Trouve les passages les plus pertinents par similarite vectorielle.
    """
    from legix.knowledge.document_ingestion import search_knowledge_base

    results = await search_knowledge_base(
        db, profile_id=profile_id, query=q, top_k=top_k, theme_filter=theme,
    )
    return results


# ── Stats knowledge base ────────────────────────────────────────

@router.get("/profiles/{profile_id}/stats")
async def knowledge_stats(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Statistiques de la knowledge base du client."""
    from sqlalchemy import func
    from legix.knowledge.models import DocumentChunk

    # Nombre de documents par type
    docs_result = await db.execute(
        select(
            ClientDocument.doc_type,
            func.count(ClientDocument.id),
        )
        .where(ClientDocument.profile_id == profile_id)
        .group_by(ClientDocument.doc_type)
    )
    docs_by_type = {row[0]: row[1] for row in docs_result}

    # Nombre total de chunks
    chunks_result = await db.execute(
        select(func.count(DocumentChunk.id))
        .where(DocumentChunk.profile_id == profile_id)
    )
    total_chunks = chunks_result.scalar() or 0

    # Themes couverts
    all_themes = set()
    docs_result = await db.execute(
        select(ClientDocument.themes)
        .where(ClientDocument.profile_id == profile_id)
    )
    for row in docs_result:
        if row[0]:
            all_themes.update(json.loads(row[0]))

    return {
        "profile_id": profile_id,
        "total_documents": sum(docs_by_type.values()),
        "documents_by_type": docs_by_type,
        "total_chunks": total_chunks,
        "themes_covered": sorted(all_themes),
    }


# ── Helpers ──────────────────────────────────────────────────────

def _doc_to_response(doc: ClientDocument) -> DocumentResponse:
    return DocumentResponse(
        id=doc.id,
        profile_id=doc.profile_id,
        doc_type=doc.doc_type,
        title=doc.title,
        summary=doc.summary,
        themes=json.loads(doc.themes) if doc.themes else [],
        key_positions=json.loads(doc.key_positions) if doc.key_positions else None,
        mentioned_stakeholders=json.loads(doc.mentioned_stakeholders) if doc.mentioned_stakeholders else [],
        file_name=doc.file_name,
        created_at=str(doc.created_at) if doc.created_at else "",
    )

"""RAG tool pour les agents LangChain — recherche dans la knowledge base client."""

import asyncio
import json
from typing import Optional

from langchain_core.tools import tool

from legix.core.database import async_session


def _run_async(coro):
    """Execute une coroutine async depuis un contexte sync."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


@tool
def rechercher_knowledge_base(
    query: str,
    top_k: int = 5,
    theme: Optional[str] = None,
) -> str:
    """Recherche dans la base de connaissances du client (documents internes,
    position papers, emails, notes, rapports). Utilise la similarite semantique
    pour trouver les passages les plus pertinents.

    Args:
        query: Question ou sujet a rechercher
        top_k: Nombre de resultats (defaut: 5)
        theme: Filtrer par theme (optionnel)
    """
    async def _search():
        from legix.knowledge.document_ingestion import search_knowledge_base
        async with async_session() as db:
            return await search_knowledge_base(
                db, profile_id=1,  # TODO: injecter via contexte
                query=query, top_k=top_k, theme_filter=theme,
            )

    result = _run_async(_search())
    return json.dumps(result, ensure_ascii=False, default=str)


@tool
def lister_documents_client(
    doc_type: Optional[str] = None,
    theme: Optional[str] = None,
) -> str:
    """Liste les documents internes du client dans la knowledge base.

    Args:
        doc_type: Filtrer par type (position_paper, internal_note, email, etc.)
        theme: Filtrer par theme
    """
    async def _list():
        from sqlalchemy import select
        from legix.core.models import ClientDocument
        async with async_session() as db:
            stmt = select(ClientDocument).where(ClientDocument.profile_id == 1)
            if doc_type:
                stmt = stmt.where(ClientDocument.doc_type == doc_type)
            result = await db.execute(stmt)
            docs = result.scalars().all()

            output = []
            for doc in docs:
                themes = json.loads(doc.themes) if doc.themes else []
                if theme and theme.lower() not in [t.lower() for t in themes]:
                    continue
                output.append({
                    "id": doc.id,
                    "title": doc.title,
                    "doc_type": doc.doc_type,
                    "themes": themes,
                    "summary": doc.summary[:200] if doc.summary else "",
                    "created_at": str(doc.created_at),
                })
            return output

    result = _run_async(_list())
    return json.dumps(result, ensure_ascii=False, default=str)


# Outils RAG disponibles pour tous les agents
RAG_TOOLS = [rechercher_knowledge_base, lister_documents_client]

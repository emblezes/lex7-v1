"""Routes API — Presse et monitoring médiatique.

Articles, mentions client, sentiment, file de riposte.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.database import get_db
from legix.core.models import PressArticle

router = APIRouter(prefix="/presse", tags=["presse"])


@router.get("/articles")
async def list_articles(
    source_name: str | None = None,
    theme: str | None = None,
    sentiment: str | None = None,
    requires_response: bool | None = None,
    profile_id: int | None = None,
    limit: int = Query(default=20, le=100),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Liste les articles de presse avec filtres."""
    query = select(PressArticle).order_by(PressArticle.publication_date.desc())

    if source_name:
        query = query.where(PressArticle.source_name.ilike(f"%{source_name}%"))
    if theme:
        query = query.where(PressArticle.themes.ilike(f"%{theme}%"))
    if sentiment:
        query = query.where(PressArticle.sentiment == sentiment)
    if requires_response is not None:
        query = query.where(PressArticle.requires_response == requires_response)
    if profile_id:
        query = query.where(PressArticle.matched_profile_ids.ilike(f"%{profile_id}%"))

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    result = await db.execute(query.offset(offset).limit(limit))
    articles = result.scalars().all()

    return {
        "items": [_serialize_article(a) for a in articles],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/articles/{article_id}")
async def get_article(article_id: int, db: AsyncSession = Depends(get_db)):
    """Détail d'un article de presse."""
    article = await db.get(PressArticle, article_id)
    if not article:
        raise HTTPException(404, "Article non trouvé")
    return _serialize_article(article, full=True)


@router.get("/mentions")
async def client_mentions(
    profile_id: int,
    days: int = Query(default=7, le=90),
    db: AsyncSession = Depends(get_db),
):
    """Articles mentionnant un client spécifique."""
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(days=days)

    query = select(PressArticle).where(
        PressArticle.matched_profile_ids.ilike(f"%{profile_id}%"),
        PressArticle.publication_date >= cutoff,
    ).order_by(PressArticle.publication_date.desc())

    result = await db.execute(query)
    articles = result.scalars().all()

    return {
        "profile_id": profile_id,
        "period_days": days,
        "total_mentions": len(articles),
        "by_sentiment": {
            "positive": sum(1 for a in articles if a.sentiment == "positive"),
            "negative": sum(1 for a in articles if a.sentiment == "negative"),
            "neutral": sum(1 for a in articles if a.sentiment == "neutral"),
            "mixed": sum(1 for a in articles if a.sentiment == "mixed"),
        },
        "requiring_response": [
            _serialize_article(a) for a in articles if a.requires_response
        ],
        "all_mentions": [_serialize_article(a) for a in articles],
    }


@router.get("/riposte-queue")
async def riposte_queue(
    profile_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """File de riposte : articles nécessitant une réponse."""
    query = select(PressArticle).where(
        PressArticle.requires_response == True,
        PressArticle.response_status.in_(["none", "draft"]),
    ).order_by(
        # Trier par urgence puis date
        PressArticle.response_urgency.desc(),
        PressArticle.publication_date.desc(),
    )

    if profile_id:
        query = query.where(PressArticle.matched_profile_ids.ilike(f"%{profile_id}%"))

    result = await db.execute(query)
    articles = result.scalars().all()

    return {
        "total": len(articles),
        "critical": [_serialize_article(a) for a in articles if a.response_urgency == "critical"],
        "high": [_serialize_article(a) for a in articles if a.response_urgency == "high"],
        "medium": [_serialize_article(a) for a in articles if a.response_urgency == "medium"],
        "low": [_serialize_article(a) for a in articles if a.response_urgency == "low"],
    }


@router.get("/stats")
async def press_stats(
    profile_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Statistiques presse."""
    base = select(PressArticle)
    if profile_id:
        base = base.where(PressArticle.matched_profile_ids.ilike(f"%{profile_id}%"))

    # Par source
    source_query = select(
        PressArticle.source_name,
        func.count().label("nb"),
    ).group_by(PressArticle.source_name)
    if profile_id:
        source_query = source_query.where(PressArticle.matched_profile_ids.ilike(f"%{profile_id}%"))
    result = await db.execute(source_query)
    by_source = {row.source_name: row.nb for row in result}

    # Par sentiment
    sentiment_query = select(
        PressArticle.sentiment,
        func.count().label("nb"),
    ).group_by(PressArticle.sentiment)
    if profile_id:
        sentiment_query = sentiment_query.where(PressArticle.matched_profile_ids.ilike(f"%{profile_id}%"))
    result = await db.execute(sentiment_query)
    by_sentiment = {row.sentiment or "unknown": row.nb for row in result}

    total_query = select(func.count()).select_from(base.subquery())
    total = (await db.execute(total_query)).scalar() or 0

    return {
        "total": total,
        "by_source": by_source,
        "by_sentiment": by_sentiment,
    }


def _serialize_article(a: PressArticle, full: bool = False) -> dict:
    data = {
        "id": a.id,
        "title": a.title,
        "source_name": a.source_name,
        "author": a.author,
        "publication_date": a.publication_date.isoformat() if a.publication_date else None,
        "sentiment": a.sentiment,
        "requires_response": a.requires_response,
        "response_urgency": a.response_urgency,
        "response_status": a.response_status,
        "url": a.url,
    }

    if full:
        data.update({
            "excerpt": a.excerpt,
            "themes": json.loads(a.themes) if a.themes else [],
            "resume_ia": a.resume_ia,
            "mentioned_entities": json.loads(a.mentioned_entities) if a.mentioned_entities else {},
            "matched_profile_ids": json.loads(a.matched_profile_ids) if a.matched_profile_ids else [],
            "linked_texte_uids": json.loads(a.linked_texte_uids) if a.linked_texte_uids else [],
            "created_at": a.created_at.isoformat() if a.created_at else None,
        })

    return data

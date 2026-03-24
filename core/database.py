"""Database engine — supporte SQLite (dev) et PostgreSQL + pgvector (prod)."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from legix.core.config import settings

# Adapter les options selon le backend
_is_postgres = settings.database_url.startswith("postgresql")

engine_kwargs = {"echo": False}
if _is_postgres:
    engine_kwargs.update({
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
    })

engine = create_async_engine(settings.database_url, **engine_kwargs)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    """Dependency FastAPI : fournit une session async."""
    async with async_session() as session:
        yield session


async def init_db():
    """Cree toutes les tables. Active pgvector si PostgreSQL."""
    from legix.core.models import Base  # noqa: F811
    import legix.knowledge.models  # noqa: F401 — enregistre DocumentChunk

    async with engine.begin() as conn:
        # Activer pgvector si PostgreSQL
        if _is_postgres:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

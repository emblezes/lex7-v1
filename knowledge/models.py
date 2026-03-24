"""Modeles DB pour la knowledge base client."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from legix.core.models import Base


class DocumentChunk(Base):
    """Chunk d'un document client avec embedding pour recherche semantique."""

    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("client_documents.id"), nullable=False)
    profile_id = Column(Integer, ForeignKey("client_profiles.id"), nullable=False)

    chunk_idx = Column(Integer, nullable=False)  # Ordre dans le document
    content = Column(Text, nullable=False)  # Texte du chunk
    embedding = Column(Text)  # JSON list[float] pour SQLite, ou pgvector pour PostgreSQL

    start_idx = Column(Integer)  # Position de debut dans le texte source
    end_idx = Column(Integer)  # Position de fin

    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("ClientDocument")

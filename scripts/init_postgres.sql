-- Init PostgreSQL pour LegiX
-- Active l'extension pgvector pour les embeddings

CREATE EXTENSION IF NOT EXISTS vector;

-- Les tables sont creees automatiquement par SQLAlchemy (init_db)
-- Ce script ne fait qu'activer pgvector

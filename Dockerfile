FROM python:3.13-slim

# Dependances systeme pour WeasyPrint (PDF) et lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    libxml2-dev \
    libxslt1-dev \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copier et installer les dependances
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]" \
    asyncpg \
    pgvector \
    python-docx \
    pypdf \
    sentence-transformers \
    langchain-anthropic \
    langgraph \
    python-jose[cryptography] \
    passlib[bcrypt]

# Copier le code
COPY legix/ legix/
COPY scripts/ scripts/
COPY data/ data/

# Creer les repertoires necessaires
RUN mkdir -p data/uploads

# Port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8000/'); assert r.status_code == 200"

# Demarrer
CMD ["uvicorn", "legix.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

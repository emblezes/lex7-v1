from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Base de données
    # SQLite (dev) : sqlite+aiosqlite:///data/legix.db
    # PostgreSQL (prod) : postgresql+asyncpg://user:pass@host/db
    database_url: str = "sqlite+aiosqlite:///data/legix.db"

    # Embeddings (Voyage AI)
    voyage_api_key: str = ""

    # Assemblée nationale
    an_base_url: str = "https://www.assemblee-nationale.fr/dyn/opendata"
    an_publication_url: str = (
        "https://www.assemblee-nationale.fr/dyn/opendata/list-publication"
    )
    an_legislature: int = 17
    an_poll_interval_seconds: int = 60

    # Claude API (enrichissement IA)
    anthropic_api_key: str = ""
    enrichment_model: str = "claude-haiku-4-5-20251001"

    # Journal officiel — API PISTE (DILA)
    piste_client_id: str = ""
    piste_client_secret: str = ""
    piste_token_url: str = "https://oauth.piste.gouv.fr/api/oauth/token"
    piste_api_base: str = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app"
    jorf_api_base: str = "https://api.piste.gouv.fr/dila/legifrance-jorf/lf-engine-app"
    jorf_poll_interval_seconds: int = 900  # 15 min

    # Senat
    senat_base_url: str = "https://www.senat.fr"
    senat_data_url: str = "https://data.senat.fr"
    senat_poll_interval_seconds: int = 300  # 5 min

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_key: str = ""  # Vide = pas d'auth en dev

    # Auth
    jwt_secret: str = "legix-demo-secret-change-in-prod"
    jwt_expiry_hours: int = 72

    # Telegram
    telegram_bot_token: str = ""

    # Email (SMTP)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "legix@example.com"

    # Dashboard URL (pour liens dans les notifications)
    dashboard_url: str = "http://localhost:3000"

    # CORS
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3006,http://127.0.0.1:3006"

    # Paths
    project_root: Path = Path(__file__).parent.parent.parent
    data_dir: Path = project_root / "data"

    model_config = {
        "env_file": [
            ".env",
            str(Path(__file__).parent.parent / ".env"),  # legix/.env
        ],
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()

"""Application FastAPI principale — LegiX API."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from legix.core.config import settings
from legix.core.database import init_db

from legix.api.routes import (
    acteurs,
    actions,
    alertes,
    amendements,
    anticipation,
    auth,
    briefings,
    cartographie,
    chat,
    dashboard,
    dossiers,
    export,
    followups,
    knowledge,
    livrables,
    livrables_stream,
    onboarding,
    onboarding_auto,
    pipeline,
    presse,
    profiles,
    search,
    signaux,
    stakeholders,
    stats,
    watch_config,
    texte_briefs,
    textes,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # Démarrer le scheduler si activé
    scheduler = None
    try:
        from legix.scheduler import LegiXScheduler
        scheduler = LegiXScheduler()
        scheduler.start()
        logger.info("Scheduler LegiX démarré")
    except Exception as e:
        logger.warning("Scheduler non démarré: %s", e)

    yield

    # Arrêter le scheduler
    if scheduler:
        scheduler.stop()
        logger.info("Scheduler LegiX arrêté")


app = FastAPI(
    title="LegiX API",
    description="Intelligence réglementaire active — API REST",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes publiques (données de référence)
app.include_router(textes.router, prefix="/api", tags=["Textes"])
app.include_router(amendements.router, prefix="/api", tags=["Amendements"])
app.include_router(acteurs.router, prefix="/api", tags=["Acteurs"])
app.include_router(signaux.router, prefix="/api", tags=["Signaux"])
app.include_router(stats.router, prefix="/api", tags=["Stats"])
app.include_router(cartographie.router, prefix="/api", tags=["Cartographie"])
app.include_router(search.router, prefix="/api", tags=["Search"])

# Routes authentifiées
app.include_router(auth.router, prefix="/api", tags=["Auth"])
app.include_router(onboarding.router, prefix="/api", tags=["Onboarding"])
app.include_router(dashboard.router, prefix="/api", tags=["Dashboard"])
app.include_router(alertes.router, prefix="/api", tags=["Alertes"])
app.include_router(profiles.router, prefix="/api", tags=["Profiles"])
app.include_router(chat.router, prefix="/api", tags=["Chat"])

# Nouvelles routes proactives
app.include_router(actions.router, prefix="/api", tags=["Actions"])
app.include_router(followups.router, prefix="/api", tags=["Followups"])
app.include_router(briefings.router, prefix="/api", tags=["Briefings"])
app.include_router(pipeline.router, prefix="/api", tags=["Pipeline"])
app.include_router(texte_briefs.router, prefix="/api", tags=["TexteBriefs"])
app.include_router(dossiers.router, prefix="/api", tags=["Dossiers"])
app.include_router(livrables.router, prefix="/api", tags=["Livrables"])
app.include_router(livrables_stream.router, prefix="/api", tags=["Livrables Stream"])

# Routes affaires publiques (anticipation, stakeholders, presse)
app.include_router(anticipation.router, prefix="/api", tags=["Anticipation"])
app.include_router(stakeholders.router, prefix="/api", tags=["Stakeholders"])
app.include_router(presse.router, prefix="/api", tags=["Presse"])
app.include_router(watch_config.router, prefix="/api", tags=["Watch Config"])
app.include_router(onboarding_auto.router, prefix="/api", tags=["Onboarding Auto"])
app.include_router(knowledge.router, prefix="/api", tags=["Knowledge Base"])
app.include_router(export.router, prefix="/api", tags=["Export"])


@app.get("/")
async def root():
    return {"name": "LegiX API", "version": "0.3.0", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "ok"}

"""
SmartLog AI — FastAPI application entry point.

Run from the backend/ directory:
    uvicorn main:app --reload
"""

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI

from config import APP_VERSION, CORS_ORIGINS
from db import init_db
from pipeline import pipeline as pipeline_orchestrator
from routers.anomalies import router as anomalies_router
from routers.classify import router as classify_router
from routers.incidents import router as incidents_router
from routers.metrics import router as metrics_router
from routers.scrape import router as scrape_router
from routers.stream import bind_loop, router as stream_router
from routers.upload import router as upload_router
from schemas import HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Start-up / shutdown hook.

    Models are loaded ONCE here (never per request). Phase 1 has no ML
    artifacts yet, so `models_loaded` only reports DB readiness; Phase 3
    loads Sentence-BERT + LogisticRegression + DBSCAN + PCA into a
    module-level holder placed on `app.state`.
    """
    init_db()  # creates tables on first run; cheap after that
    # Load every ML artifact ONCE here — never per request.
    pipeline_orchestrator.load_models()
    # Ingest pushes run from worker threads; they need the loop to schedule on.
    bind_loop(asyncio.get_running_loop())
    yield


app = FastAPI(
    title="SmartLog AI",
    description="Hybrid AI incident classification for enterprise log monitoring.",
    version=APP_VERSION,
    lifespan=lifespan,
)

# --- CORS: Vite dev server + Lovable preview origin -------------------------
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers -----------------------------------------------------------------
app.include_router(incidents_router)
app.include_router(classify_router)
app.include_router(anomalies_router)
app.include_router(metrics_router)
app.include_router(upload_router)
app.include_router(scrape_router)
app.include_router(stream_router)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness check; `models_loaded` is true once train.py artifacts load."""
    return HealthResponse(
        status="ok",
        models_loaded=pipeline_orchestrator.models_ready(),
        version=APP_VERSION,
    )

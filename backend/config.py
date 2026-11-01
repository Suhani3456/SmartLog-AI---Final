"""
SmartLog AI — application configuration.

Loads secrets and tunables from the backend/.env file (if present).
Never print or commit real secrets; .env.example documents the keys.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Base directory = backend/ (this file's folder)
BASE_DIR = Path(__file__).resolve().parent

# Load backend/.env once at import time. Missing file is fine in dev.
load_dotenv(BASE_DIR / ".env")


def _get(key: str, default: str = "") -> str:
    """Read an env var, falling back to a default when unset or empty."""
    value = os.environ.get(key, "")
    return value if value.strip() != "" else default


# --- LLM fallback -----------------------------------------------------------
ANTHROPIC_API_KEY: str = _get("ANTHROPIC_API_KEY")

# --- Database ---------------------------------------------------------------
# SQLite by default; the file lives next to backend/ source.
DATABASE_URL: str = _get(
    "DATABASE_URL", f"sqlite:///{BASE_DIR / 'smartlog.db'}"
)

# --- CORS -------------------------------------------------------------------
# The Vite dev server (5173) and the Lovable preview origin (8080).
CORS_ORIGINS: list[str] = [
    "http://localhost:5173",
    "http://localhost:8080",
]

# --- ML artifact paths (used from Phase 3) -----------------------------------
DATA_DIR: Path = BASE_DIR / "data"
MODELS_DIR: Path = BASE_DIR / "models"
METRICS_PATH: Path = MODELS_DIR / "metrics.json"
BERT_MODEL_PATH: Path = MODELS_DIR / "bert_logreg.joblib"
CLUSTER_PATH: Path = MODELS_DIR / "dbscan.joblib"
PCA_PATH: Path = MODELS_DIR / "pca.joblib"
EMBED_MODEL_NAME: str = "all-MiniLM-L6-v2"

# --- Pipeline tuning ---------------------------------------------------------
# Minimum LogisticRegression probability required to accept the ML decision.
BERT_CONFIDENCE_THRESHOLD: float = 0.70

# --- Ingest limits ------------------------------------------------------------
# Hard cap on lines accepted per ingest (upload or scrape), shared by both.
MAX_UPLOAD_LINES: int = 5000

# --- Web scrape (POST /api/scrape) --------------------------------------------
# MUST DEFAULT TO TRUE so localhost/frequency demo targets work out of the
# box. Set SCRAPE_ALLOW_PRIVATE=false if this backend is ever deployed on a
# public host — it blocks requests to localhost/127.x and private ranges to
# prevent the backend being used as an SSRF proxy.
SCRAPE_ALLOW_PRIVATE: bool = _get("SCRAPE_ALLOW_PRIVATE", "true").strip().lower() != "false"
SCRAPE_TIMEOUT_S: float = 15.0
SCRAPE_MAX_REDIRECTS: int = 3
SCRAPE_MAX_BODY_BYTES: int = 5 * 1024 * 1024  # 5 MB deep-fetch cap
SCRAPE_USER_AGENT: str = "SmartLogAI-Scraper/1.0"

# Sample log stream replays at a random 1-3 s interval.
STREAM_MIN_INTERVAL_S: float = 1.0
STREAM_MAX_INTERVAL_S: float = 3.0

APP_VERSION: str = "0.1.0"

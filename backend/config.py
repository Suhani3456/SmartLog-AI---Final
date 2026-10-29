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

# Sample log stream replays at a random 1-3 s interval.
STREAM_MIN_INTERVAL_S: float = 1.0
STREAM_MAX_INTERVAL_S: float = 3.0

APP_VERSION: str = "0.1.0"

"""
SmartLog AI pipeline — Stage 3a: sentence embeddings.

Wraps the sentence-transformers `all-MiniLM-L6-v2` model (384-dim). The model
is loaded ONCE by pipeline.load_models() at FastAPI startup — never per
request — and `embed()` encodes cleaned log text into L2-normalized vectors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from config import EMBED_MODEL_NAME, MODELS_DIR

if TYPE_CHECKING:  # only imported for typing; hard import happens in load()
    from sentence_transformers import SentenceTransformer

_EMBEDDER = None


def embed(texts: list[str]):
    """Embed short cleaned strings -> (n, 384) float32 numpy array."""
    if _EMBEDDER is None:
        raise RuntimeError("Embedder not loaded. Call pipeline.load_models() first.")
    return _EMBEDDER.encode(texts, normalize_embeddings=True, show_progress_bar=False)


def is_loaded() -> bool:
    return _EMBEDDER is not None


def load() -> None:
    """Load the SentenceTransformer once (idempotent)."""
    global _EMBEDDER
    if _EMBEDDER is not None:
        return
    # Local cache under backend/models/ keeps the viva demo offline-friendly.
    from sentence_transformers import SentenceTransformer

    _EMBEDDER = SentenceTransformer(
        EMBED_MODEL_NAME,
        cache_folder=str(MODELS_DIR / "hf_cache"),
    )

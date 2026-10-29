"""
SmartLog AI pipeline — Stage 3b: Logistic Regression head over embeddings.

The trained head is a joblib dict {model, labels, trained_at, version}
written by train.py to backend/models/bert_logreg.joblib. Loaded ONCE at
startup. predict() returns (category, max_probability, per_class_probs).
"""

from __future__ import annotations

from typing import Any

from config import BERT_MODEL_PATH

_HEAD: dict[str, Any] | None = None


def load() -> None:
    """Load the LogisticRegression artifact once (idempotent)."""
    global _HEAD
    if _HEAD is not None:
        return
    import joblib

    if not BERT_MODEL_PATH.exists():
        raise RuntimeError(
            f"Missing classifier artifact: {BERT_MODEL_PATH}. Run train.py first."
        )
    _HEAD = joblib.load(BERT_MODEL_PATH)


def is_loaded() -> bool:
    return _HEAD is not None


def predict(embedding) -> tuple[str, float, dict[str, float]]:
    """
    Classify one embedding (1-D, 384) — returns the head's own decision,
    NOT the pipeline decision. The pipeline applies the 0.70 threshold.
    """
    if _HEAD is None:
        raise RuntimeError("Classifier not loaded. Call pipeline.load_models() first.")
    model = _HEAD["model"]
    labels = _HEAD["labels"]
    proba = model.predict_proba([embedding])[0]
    best_idx = int(proba.argmax())
    per_class = {label: round(float(p), 4) for label, p in zip(labels, proba)}
    return labels[best_idx], float(proba[best_idx]), per_class

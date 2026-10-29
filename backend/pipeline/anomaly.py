"""
SmartLog AI pipeline — Stage 4: DBSCAN anomaly detection + 2D PCA view.

train.py fits DBSCAN on the SBERT embeddings of LOW-CONFIDENCE logs
(max LogReg prob < 0.70) and saves two artifacts:
  dbscan.joblib -> {model, train_embeddings, labels}
  pca.joblib    -> fitted 2-component PCA (for the Anomaly Explorer scatter)

At inference, a single log cannot be "fit" with plain DBSCAN, so predict_one
(cluster_of) finds the nearest non-noise fitted point within eps; inside ->
that cluster id, outside -> -1 (noise). Noise points are the unknown
anomalies. Both models load ONCE at startup.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from config import CLUSTER_PATH, PCA_PATH

_DBSCAN_ART: dict[str, Any] | None = None
_PCA = None


def load() -> None:
    """Load DBSCAN + PCA artifacts once (idempotent)."""
    global _DBSCAN_ART, _PCA
    if _DBSCAN_ART is not None:
        return
    import joblib

    if not CLUSTER_PATH.exists():
        raise RuntimeError(f"Missing artifact: {CLUSTER_PATH}. Run train.py first.")
    _DBSCAN_ART = joblib.load(CLUSTER_PATH)
    if PCA_PATH.exists():
        _PCA = joblib.load(PCA_PATH)


def is_loaded() -> bool:
    return _DBSCAN_ART is not None


def cluster_of(embedding) -> int:
    """
    Cluster id (-1 == noise) for one embedding.

    Membership check: distance to the nearest fitted non-noise point within
    eps. (Plain DBSCAN has no transform() for new points; nearest-fitted-
    point is the standard inference approximation and mirrors train.py.)
    """
    if _DBSCAN_ART is None:
        raise RuntimeError("Anomaly model not loaded. Call pipeline.load_models() first.")
    model = _DBSCAN_ART["model"]
    train_emb = np.asarray(_DBSCAN_ART["train_embeddings"])
    labels = np.asarray(_DBSCAN_ART["labels"])

    non_noise = np.flatnonzero(labels != -1)
    if non_noise.size == 0:
        return -1
    points = train_emb[non_noise]
    point_labels = labels[non_noise]

    emb = np.asarray(embedding, dtype=np.float64).reshape(1, -1)
    dists = np.linalg.norm(points - emb, axis=1)
    k = int(dists.argmin())
    return int(point_labels[k]) if float(dists[k]) <= float(model.eps) else -1


def to_2d(embedding):
    """Project one 384-dim embedding into the saved 2D PCA space."""
    if _PCA is None:
        raise RuntimeError("PCA not loaded. Call pipeline.load_models() first.")
    return _PCA.transform(np.asarray(embedding).reshape(1, -1))[0]

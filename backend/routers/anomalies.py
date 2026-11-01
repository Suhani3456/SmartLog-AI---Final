"""
SmartLog AI — anomaly exploration routes.

GET  /api/anomalies/clusters         2D PCA scatter + cluster summaries.
POST /api/anomalies/clusters/{id}/label  human feedback -> TrainingExample.

The scatter is computed ONLY from ingested incidents (the unknown ones are
embedded and mapped into the trained PCA/DBSCAN space). On an empty database
the endpoint returns empty lists — no synthetic placeholder data.
"""

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db import Incident as IncidentRow, TrainingExample, get_db
from pipeline import anomaly as anomaly_stage, embedder
from pipeline import pipeline as pipeline_orchestrator
from schemas import ClusterLabelRequest
from typing import Any, Dict, List, Tuple

# Re-export the point/cluster types used by _status()'s return annotation.
from schemas import AnomalyCluster

# Build AnomalyPoint inline here so the router is self-contained even if
# schemas.AnomalyPoint ever gets renamed.


class AnomalyPoint:
    def __init__(self, **kwargs: Any) -> None:
        self.incident_id: int = kwargs.get("incident_id", 0)
        self.x: float = float(kwargs.get("x", 0.0))
        self.y: float = float(kwargs.get("y", 0.0))
        self.cluster_id: int = kwargs.get("cluster_id", 0)
        self.noise: bool = bool(kwargs.get("noise", False))

router = APIRouter()


def _status(db: Session) -> tuple[list[AnomalyPoint], list[AnomalyCluster]]:
    """Cluster the unknown incidents currently in the DB; empty in -> empty out."""
    unknown = (
        db.query(IncidentRow)
        .filter(IncidentRow.is_known.is_(False))
        .filter(IncidentRow.category != "Unknown")
        .order_by(IncidentRow.id.desc())
        .limit(200)
        .all()
    )
    if not unknown or not pipeline_orchestrator.models_ready():
        return [], []

    try:
        embeddings = embedder.embed([u.cleaned_text or u.raw_text for u in unknown])
        points: list[AnomalyPoint] = []
        cluster_samples: dict[int, list[str]] = defaultdict(list)
        for row, emb in zip(unknown, embeddings):
            cluster_id = anomaly_stage.cluster_of(emb)
            x1, y1 = anomaly_stage.to_2d(emb)
            points.append(
                AnomalyPoint(
                    incident_id=row.id,
                    x=round(float(x1), 4),
                    y=round(float(y1), 4),
                    cluster_id=cluster_id,
                    noise=cluster_id == -1,
                )
            )
            cluster_samples[cluster_id].append(row.raw_text)

        clusters = [
            AnomalyCluster(
                cluster_id=cid,
                size=len(logs),
                is_noise=cid == -1,
                sample_logs=logs[:3],
            )
            for cid, logs in sorted(cluster_samples.items())
        ]
    except Exception:  # noqa: BLE001 — broken models must never 500 the explorer
        return [], []

    # Show saved human labels next to clusters that already have them.
    for example in db.query(TrainingExample).all():
        for cluster in clusters:
            if cluster.cluster_id == example.cluster_id:
                cluster.labeled_category = example.category
    return points, clusters


@router.get("/api/anomalies")
def get_clusters(db: Session = Depends(get_db)) -> dict:
    """Scatter points (PCA 2D) + cluster summaries for the Anomaly Explorer."""
    points, clusters = _status(db)

    # Attach per-incident category/message from the DB where available.
    cat_by_id = {r.id: r.category for r in db.query(IncidentRow).all()}
    msg_by_id = {r.id: r.raw_text for r in db.query(IncidentRow).all()}

    return {
        "points": [
            {
                "x": float(p.x),
                "y": float(p.y),
                "cluster": p.cluster_id,
                "category": cat_by_id.get(p.incident_id, ""),
                "message": msg_by_id.get(p.incident_id, ""),
                "is_noise": bool(p.noise),
            }
            for p in points
        ],
        "clusters": [
            {
                "id": int(c.cluster_id),
                "label": "",
                "count": int(c.size),
                "samples": list(c.sample_logs),
                "labeled_as": c.labeled_category,
                "first_seen": "",
            }
            for c in clusters
        ],
    }


@router.post("/api/anomalies/{cluster_id}/label")
def label_cluster(
    cluster_id: int,
    body: ClusterLabelRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Save a human label for a cluster as a future training example."""
    if cluster_id < -1:
        raise HTTPException(status_code=422, detail="Invalid cluster id")
    example = TrainingExample(
        cluster_id=cluster_id,
        category=body.category,
        notes=body.notes,
        sample_logs="[]",
    )
    db.add(example)
    db.commit()
    db.refresh(example)
    return {
        "id": cluster_id,
        "label": body.category,
        "count": 0,
        "samples": [],
        "labeled_as": body.category,
        "first_seen": "",
    }

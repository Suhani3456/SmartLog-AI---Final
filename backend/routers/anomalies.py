"""
SmartLog AI — anomaly exploration routes.

GET  /api/anomalies/clusters         2D PCA scatter + cluster summaries.
POST /api/anomalies/clusters/{id}/label  human feedback -> TrainingExample.

Phase 1: shapes are final, points come back deterministic stub data. Phase 3
swaps the stub for real DBSCAN + PCA over stored embeddings.
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db import TrainingExample, get_db
from schemas import (
    AnomalyCluster,
    AnomalyPoint,
    ClustersResponse,
    ClusterLabelRequest,
    ClusterLabelResponse,
)

router = APIRouter()


def _status(db: Session) -> tuple[list[AnomalyPoint], list[AnomalyCluster]]:
    """Build the scatter payload. Stub now; DBSCAN wiring lands in Phase 3."""
    # Two small known-style clusters plus a violet-flagged noise cluster,
    # coordinates kept deterministic so the page renders stably.
    points = [
        AnomalyPoint(incident_id=i, x=x, y=y, cluster_id=cluster, noise=False)
        for cluster, coords in {0: [(-1.2, 0.4), (-1.1, 0.6), (-0.9, 0.5), (-1.3, 0.2)],
                                1: [(1.4, -0.8), (1.2, -0.6), (1.5, -1.0)]}.items()
        for i, (x, y) in enumerate(coords, start=cluster * 100 + 1)
    ]
    points += [
        AnomalyPoint(incident_id=900 + i, x=x, y=y, cluster_id=-1, noise=True)
        for i, (x, y) in enumerate([(0.1, 1.8), (0.3, 2.1), (-0.2, 2.0), (0.6, 1.7)])
    ]
    clusters = [
        AnomalyCluster(
            cluster_id=0, size=4, is_noise=False,
            sample_logs=["upstream crm-api timed out after retries exhausted"],
        ),
        AnomalyCluster(
            cluster_id=1, size=3, is_noise=False,
            sample_logs=["orphan temp table still holding two sstables"],
        ),
        AnomalyCluster(
            cluster_id=-1, size=4, is_noise=True,
            sample_logs=[
                "job scheduler wrote an unlabeled task state no rulebook knows",
            ],
        ),
    ]
    # Show saved human labels next to clusters that already have them.
    for example in db.query(TrainingExample).all():
        for cluster in clusters:
            if cluster.cluster_id == example.cluster_id:
                cluster.labeled_category = example.category
    return points, clusters


@router.get("/api/anomalies/clusters", response_model=ClustersResponse)
def get_clusters(db: Session = Depends(get_db)) -> ClustersResponse:
    """Scatter points (PCA 2D) + cluster summaries for the Anomaly Explorer."""
    points, clusters = _status(db)
    return ClustersResponse(points=points, clusters=clusters)


@router.post("/api/anomalies/clusters/{cluster_id}/label",
             response_model=ClusterLabelResponse)
def label_cluster(
    cluster_id: int,
    body: ClusterLabelRequest,
    db: Session = Depends(get_db),
) -> ClusterLabelResponse:
    """Save a human label for a cluster as a future training example."""
    if cluster_id < -1:
        raise HTTPException(status_code=422, detail="Invalid cluster id")
    example = TrainingExample(
        cluster_id=cluster_id,
        category=body.category,
        notes=body.notes,
        sample_logs=json.dumps([]),
    )
    db.add(example)
    db.commit()
    db.refresh(example)
    return ClusterLabelResponse(saved=True, training_example_id=example.id)

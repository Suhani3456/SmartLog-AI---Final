"""
SmartLog AI — classification routes.

POST /api/classify        classify a single log line (demo, not stored).
POST /api/classify/store  classify AND store it (used by the WS streamer).
"""

import json

import json
from datetime import timedelta
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import Incident as IncidentRow, get_db, utcnow
from pipeline import pipeline as pipeline_orchestrator
from schemas import ClassifyRequest

router = APIRouter()

_DEFAULT_REMEDIATION: dict[str, str] = {
    "Database Error": "Check the DB connection pool and slow-query log; kill long transactions.",
    "API Failure": "Check the upstream service health endpoint and recent deploys.",
    "Login Failure": "Verify the auth service; check for lockouts after failed attempts.",
    "Payment Issue": "Confirm gateway status and reconcile the failed transactions.",
    "Security Alert": "Review access logs for the source IP and rotate affected credentials.",
    "Resource Usage": "Right-size the instance or recycle the worker before it hits OOM.",
    "Workflow Error": "Inspect the last failed step and re-run the job with retries reset.",
    "User Action": "No action needed; informational event.",
    "Unknown": "Forward to the on-call engineer for manual triage.",
}


def _remediation_for(category: str, passed_remediation: str) -> str:
    """Use the pipeline's remediation when present, else the per-category hint."""
    return passed_remediation or _DEFAULT_REMEDIATION.get(
        category, _DEFAULT_REMEDIATION["Unknown"]
    )


@router.post("/api/classify")
def classify(body: ClassifyRequest) -> dict:
    """Classify one raw log line; nothing is stored (demo endpoint)."""
    import time

    t0 = time.perf_counter()
    result = pipeline_orchestrator.classify_text(body.text)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    # Normalise the pipeline trace to the exact five stage names the UI expects.
    trace = result["pipeline_trace"]
    wanted = [
        "Preprocessing",
        "Regex Match",
        "BERT Embedding + Logistic Regression",
        "DBSCAN Anomaly Check",
        "LLM Fallback",
    ]
    normalised_trace: list[dict] = []
    for stage in wanted:
        found = next((t for t in trace if t.get("stage") == stage), None)
        if found is not None:
            normalised_trace.append({
                "stage": stage,
                "matched": bool(found.get("matched", False)),
                "skipped": bool(found.get("skipped", False)),
                "score": float(found.get("score", 0.0)),
                "detail": str(found.get("detail", "")),
            })
        else:
            normalised_trace.append({
                "stage": stage,
                "matched": False,
                "skipped": True,
                "score": 0.0,
                "detail": "",
            })

    return {
        "category": result["category"],
        "severity": result["severity"],
        "confidence": float(result["confidence"]),
        "classified_by": result["classified_by"],
        "cleaned_text": result["cleaned_text"],
        "is_known": bool(result["is_known"]),
        "pipeline_trace": normalised_trace,
        "explanation": result["explanation"],
        "remediation": _remediation_for(result["category"], result["remediation"]),
        "latency_ms": round(latency_ms, 2),
    }


@router.post("/api/classify/store")
def classify_and_store(
    body: ClassifyRequest,
    source: str = "Cloud/Server",
    level: str = "INFO",
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Classify one line AND store it as an incident row."""
    import time

    t0 = time.perf_counter()
    result = pipeline_orchestrator.classify_text(body.text, level=level, source=source)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    row = IncidentRow(
        timestamp=utcnow(),
        source=source,
        level=level,
        raw_text=body.text,
        cleaned_text=result["cleaned_text"],
        category=result["category"],
        severity=result["severity"],
        confidence=result["confidence"],
        classified_by=result["classified_by"],
        regex_rule=result.get("regex_rule"),
        is_known=result["is_known"],
        pipeline_trace=json.dumps(result["pipeline_trace"]),
        explanation=result["explanation"],
        remediation=_remediation_for(result["category"], result["remediation"]),
        detection_ms=result.get("detection_ms", latency_ms),
        status="Open",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    d = row.to_dict()
    related = (
        db.query(IncidentRow)
        .filter(
            IncidentRow.category == row.category,
            IncidentRow.source == row.source,
            IncidentRow.timestamp >= row.timestamp - timedelta(hours=1),
            IncidentRow.timestamp <= row.timestamp + timedelta(hours=1),
            IncidentRow.id != row.id,
        )
        .order_by(IncidentRow.timestamp.desc())
        .limit(5)
        .all()
    )
    d["related_logs"] = [
        {
            "id": r.id,
            "timestamp": r.timestamp.isoformat() + "Z",
            "level": r.level,
            "message": r.raw_text,
            "source": r.source,
        }
        for r in related
    ]
    d["normalized"] = True
    return d

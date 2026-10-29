"""
SmartLog AI — classification routes.

POST /api/classify        classify a single log line (demo, not stored).
POST /api/classify/store  classify AND store it (used by the WS streamer).
"""

import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import Incident as IncidentRow, get_db, utcnow
from pipeline import pipeline as pipeline_orchestrator
from schemas import ClassificationResult, ClassifyRequest, Incident

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


@router.post("/api/classify", response_model=ClassificationResult)
def classify(body: ClassifyRequest) -> ClassificationResult:
    """Classify one raw log line; nothing is stored (demo endpoint)."""
    result = pipeline_orchestrator.classify_text(body.text)
    return ClassificationResult(
        category=result["category"],
        severity=result["severity"],
        confidence=result["confidence"],
        classified_by=result["classified_by"],
        cleaned_text=result["cleaned_text"],
        is_known=result["is_known"],
        pipeline_trace=result["pipeline_trace"],
        explanation=result["explanation"],
        remediation=_remediation_for(result["category"], result["remediation"]),
    )


@router.post("/api/classify/store", response_model=Incident)
def classify_and_store(
    body: ClassifyRequest,
    source: str = "Cloud/Server",
    level: str = "INFO",
    db: Session = Depends(get_db),
) -> Incident:
    """Classify one line AND store it as an incident row."""
    result = pipeline_orchestrator.classify_text(body.text, level=level, source=source)
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
        regex_rule=result["regex_rule"],
        is_known=result["is_known"],
        pipeline_trace=json.dumps(result["pipeline_trace"]),
        explanation=result["explanation"],
        remediation=_remediation_for(result["category"], result["remediation"]),
        detection_ms=result["detection_ms"],
        status="Open",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return Incident(**row.to_dict())

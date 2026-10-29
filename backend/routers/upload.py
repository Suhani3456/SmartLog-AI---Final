"""
SmartLog AI — batch upload routes.

POST /api/upload                   accept .log/.txt/.csv, classify in background.
GET  /api/upload/{upload_id}/status poll progress for the progress bar.

The background task parses each line, runs the real pipeline stub and stores
every line as an Incident. Phase 3/4 keeps this code; only the pipeline behind
it gains the ML stages.
"""

import csv
import io
import json
import random
import time
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from db import Incident as IncidentRow, SessionLocal, UploadedFile, get_db, utcnow
from pipeline import pipeline as pipeline_orchestrator
from schemas import Incident, UploadResponse, UploadStatus

router = APIRouter()

ALLOWED_EXTENSIONS = {".log", ".txt", ".csv"}

# Source systems we assign heuristically when the filename/line gives no hint.
_SOURCES = ["CRM", "HRMS", "Billing", "Cloud/Server"]


def _read_lines(upload: UploadFile) -> list[str]:
    """Parse an uploaded .log/.txt/.csv body into raw log lines."""
    name = (upload.filename or "").lower()
    raw = upload.file.read().decode("utf-8", errors="replace")
    if name.endswith(".csv"):
        reader = csv.reader(io.StringIO(raw))
        lines = []
        for row in reader:
            # Last column tends to be the message; join everything but empty cells.
            cells = [c for c in row if c.strip()]
            if cells:
                lines.append(cells[-1] if len(cells) == 1 else " ".join(cells))
        return lines
    return [line for line in raw.splitlines() if line.strip()]


def _guess_source(line: str, filename: str) -> str:
    """Very light source labeling for uploads until richer routing exists."""
    lowered = (line + " " + filename).lower()
    if "crm" in lowered:
        return "CRM"
    if "hrms" in lowered or "employee" in lowered or "payroll" in lowered:
        return "HRMS"
    if "billing" in lowered or "payment" in lowered or "invoice" in lowered:
        return "Billing"
    return "Cloud/Server"


def _process_upload(upload_id: int, lines: list[str], filename: str) -> None:
    """Background task: classify every line, store incidents, update progress."""
    db: Session = SessionLocal()
    try:
        total = len(lines)
        upload = db.get(UploadedFile, upload_id)
        if upload is None:
            return
        upload.total_lines = total

        for i, line in enumerate(lines, start=1):
            source = _guess_source(line, filename)
            level = "ERROR" if "error" in line.lower() else \
                    "WARN" if "warn" in line.lower() else \
                    "INFO"
            result = pipeline_orchestrator.classify_text(line, level=level, source=source)
            db.add(IncidentRow(
                timestamp=utcnow(),
                source=source,
                level=level,
                raw_text=line,
                cleaned_text=result["cleaned_text"],
                category=result["category"],
                severity=result["severity"],
                confidence=result["confidence"],
                classified_by=result["classified_by"],
                regex_rule=result["regex_rule"],
                is_known=result["is_known"],
                pipeline_trace=json.dumps(result["pipeline_trace"]),
                explanation=result["explanation"],
                remediation=result["remediation"],
                detection_ms=result["detection_ms"],
                status="Open",
            ))
            upload.processed = i
            upload.incidents_created += 1
            if i % 25 == 0:  # commit in chunks so the poller sees progress
                db.commit()
        upload.status = "done"
        db.commit()
    except Exception:  # noqa: BLE001 — an upload must never crash the server
        db.rollback()
        failed = db.get(UploadedFile, upload_id)
        if failed is not None:
            failed.status = "failed"
            db.commit()
    finally:
        db.close()


@router.post("/api/upload", response_model=UploadResponse, status_code=202)
def upload_log_file(
    background: BackgroundTasks,
    file: UploadFile,
    db: Session = Depends(get_db),
) -> UploadResponse:
    """Accept a log file and schedule background classification."""
    name = file.filename or "upload.log"
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type {ext!r}; expected one of {sorted(ALLOWED_EXTENSIONS)}",
        )

    lines = _read_lines(file)
    if not lines:
        raise HTTPException(status_code=422, detail="File contains no log lines")
    if len(lines) > 5000:
        raise HTTPException(status_code=413, detail="File too large (max 5000 lines)")

    upload = UploadedFile(
        filename=name, total_lines=len(lines), processed=0,
        incidents_created=0, status="processing", created_at=utcnow(),
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)

    background.add_task(_process_upload, upload.id, lines, name)
    return UploadResponse(upload_id=upload.id, filename=name, total_lines=len(lines))


@router.get("/api/upload/{upload_id}/status", response_model=UploadStatus)
def upload_status(upload_id: int, db: Session = Depends(get_db)) -> UploadStatus:
    """Poll this for the upload progress bar and results summary."""
    upload = db.get(UploadedFile, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    return UploadStatus(
        upload_id=upload.id,
        filename=upload.filename or "",
        status=upload.status or "processing",
        processed=upload.processed or 0,
        total=upload.total_lines or 0,
        incidents_created=upload.incidents_created or 0,
    )

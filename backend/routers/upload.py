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
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from db import Incident as IncidentRow, UploadedFile, get_db, utcnow
from schemas import UploadResponse
from services import run_ingest

router = APIRouter()

ALLOWED_EXTENSIONS = {".log", ".txt", ".csv"}


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

    background.add_task(run_ingest, upload.id, lines, name)

    # Return the upload-accepted contract the UI expects.
    return UploadResponse(
        upload_id=upload.id,
        filename=name,
        total_lines=len(lines),
    )


@router.get("/api/upload/{upload_id}/status")
def upload_status(upload_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Poll this for the upload progress bar and results summary."""
    upload = db.get(UploadedFile, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")

    base: Dict[str, Any] = {
        "upload_id": upload.id,
        "filename": upload.filename or "",
        "status": upload.status or "processing",
        "processed": upload.processed or 0,
        "total": upload.total_lines or 0,
        "incidents_created": upload.incidents_created or 0,
    }

    # Only when finished, attach the results summary the UI expects.
    if upload.status == "done":
        rows = (
            db.query(IncidentRow)
            .filter(IncidentRow.source == upload.filename)
            .order_by(IncidentRow.id)
            .all()
        )
        by_sev: Dict[str, int] = {}
        by_cat: Dict[str, int] = {}
        unknown = 0
        for r in rows:
            by_sev[r.severity] = by_sev.get(r.severity, 0) + 1
            by_cat[r.category] = by_cat.get(r.category, 0) + 1
            if not r.is_known:
                unknown += 1
        base.update({
            "total_lines": upload.total_lines,
            "classified": len(rows),
            "incidents": len(rows),
            "unknown": unknown,
            "by_severity": [{"severity": s, "count": by_sev.get(s, 0)} for s in ("Critical", "High", "Medium", "Low", "Unknown")],
            "by_category": [{"category": c, "count": by_cat.get(c, 0)} for c in ("Database Error", "API Failure", "Login Failure", "Payment Issue", "Security Alert", "Resource Usage", "Workflow Error", "User Action", "Unknown")],
            "duration_ms": 0,
        })

    return base

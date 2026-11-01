"""
SmartLog AI — shared ingest service.

One function owns the "turn raw lines into classified incident rows" path so
/api/upload and /api/scrape behave identically and cannot drift:
ingest + classify + DB insert + upload progress + WebSocket push (≤50 newest).

Both routes only do their source-specific parsing, then hand the lines here.
"""

import json
from typing import Optional

from db import Incident as IncidentRow, SessionLocal, UploadedFile, utcnow
from pipeline import pipeline as pipeline_orchestrator

# Source systems we assign heuristically when the line/label gives no hint.
_SOURCES = {"CRM", "HRMS", "Billing", "Cloud/Server"}


def _guess_source(line: str, label: str) -> str:
    """Very light source labeling until richer routing exists."""
    lowered = (line + " " + label).lower()
    if "crm" in lowered:
        return "CRM"
    if "hrms" in lowered or "employee" in lowered or "payroll" in lowered:
        return "HRMS"
    if "billing" in lowered or "payment" in lowered or "invoice" in lowered:
        return "Billing"
    return "Cloud/Server"


def _derive_level(line: str) -> str:
    """Level heuristic shared by every ingest source. 'error' wins, then 'warn'."""
    lowered = line.lower()
    if "error" in lowered:
        return "ERROR"
    if "warn" in lowered:
        return "WARN"
    return "INFO"


def _classify_one(line: str, level: str, source: str) -> dict:
    """Run the real hybrid pipeline for one line."""
    return pipeline_orchestrator.classify_text(line, level=level, source=source)


def run_ingest(upload_id: int, lines: list[str], label: str) -> None:
    """
    Background task: classify every line, store incidents, update progress and
    broadcast the freshly ingested logs (max 50 most recent) on /ws/stream.

    Mirrors the previous _process_upload behaviour exactly (chunked progress
    commits every 25 lines, failed status on error), plus the WS push.
    """
    db: SessionLocal = SessionLocal()  # type: ignore[assignment]
    rows_created: list[IncidentRow] = []
    try:
        upload = db.get(UploadedFile, upload_id)
        if upload is None:
            return
        total = len(lines)
        upload.total_lines = total

        for i, line in enumerate(lines, start=1):
            source = _guess_source(line, label)
            level = _derive_level(line)
            result = _classify_one(line, level, source)
            row = IncidentRow(
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
            )
            db.add(row)
            rows_created.append(row)
            upload.processed = i
            upload.incidents_created += 1
            if i % 25 == 0:  # commit in chunks so the poller sees progress
                db.commit()
        upload.status = "done"
        db.commit()

        # Real data only: push the newly ingested logs to live clients,
        # capped at the 50 most recent. Each frame uses the frontend's
        # LogEntry shape (no raw_text/pipeline_trace here).
        rows_created.sort(key=lambda r: r.id or 0)
        newest = rows_created[-50:]
        frames: list[dict] = []
        for row in newest:
            d = row.to_dict()
            frames.append({
                "id": d["id"],
                "timestamp": d["timestamp"],
                "source": d["source"],
                "level": d["level"],
                "message": d["raw_text"],
                "category": d["category"],
                "severity": d["severity"],
                "confidence": d["confidence"],
                "classified_by": d["classified_by"],
            })
        try:
            from routers import stream

            stream.push_incident_frames(frames)
        except Exception:  # noqa: BLE001 — the push must never fail an ingest
            pass
    except Exception:  # noqa: BLE001 — an ingest must never crash the server
        db.rollback()
        failed = db.get(UploadedFile, upload_id)
        if failed is not None:
            failed.status = "failed"
            db.commit()
    finally:
        db.close()

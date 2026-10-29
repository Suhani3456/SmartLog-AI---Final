"""
SmartLog AI — live stream route.

WS /ws/stream: replays sample_logs.csv at random 1-3 s intervals, classifies
each through the REAL pipeline, stores it and broadcasts the incident JSON.
"""

import asyncio
import csv
import json
import random
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from config import BASE_DIR, STREAM_MAX_INTERVAL_S, STREAM_MIN_INTERVAL_S
from db import Incident as IncidentRow, SessionLocal, utcnow

router = APIRouter()

SAMPLE_CSV = Path(BASE_DIR) / "data" / "sample_logs.csv"


def _load_samples() -> list[dict[str, str]]:
    samples = []
    if not SAMPLE_CSV.exists():
        # Fallback samples if CSV missing
        return [
            {"level": "ERROR", "source": "CRM", "text": "2026-10-30 09:14:22 crm-app-03 db: connection timeout after 30s, req_id=a41f2c"},
            {"level": "WARN", "source": "Billing", "text": "2026-10-30 09:15:03 billing-api-02 payment: transaction declined, card token reused"},
            {"level": "INFO", "source": "HRMS", "text": "2026-10-30 09:16:41 hrms-web-01 user logged in, user_id=1042"},
        ]
    try:
        with SAMPLE_CSV.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                text = row.get("message") or row.get("text") or row.get("raw") or ""
                if not text and row:
                    # Join all values
                    text = " ".join(str(v) for v in row.values() if v)
                samples.append({
                    "level": (row.get("level") or "INFO").strip().upper(),
                    "source": (row.get("source") or "Cloud/Server").strip(),
                    "text": text.strip(),
                })
    except Exception:
        pass
    # Shuffle for natural variety
    random.shuffle(samples)
    return samples


_SAMPLES = _load_samples()
_SAMPLE_INDEX = 0


@router.websocket("/ws/stream")
async def stream(ws: WebSocket) -> None:
    """Broadcast classified log lines forever until the client disconnects."""
    await ws.accept()
    try:
        await ws.send_json({"type": "hello", "message": "stream connected"})
        while True:
            interval = random.uniform(STREAM_MIN_INTERVAL_S, STREAM_MAX_INTERVAL_S)
            await asyncio.sleep(interval)
            event = _classify_next_sample()
            if event is not None:
                await ws.send_json(event)
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001 — a broken socket must not crash the server
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass


def _classify_next_sample() -> dict | None:
    """Classify one sample line from CSV and store it; return the WS event payload."""
    global _SAMPLE_INDEX
    if not _SAMPLES:
        return None
    sample = _SAMPLES[_SAMPLE_INDEX % len(_SAMPLES)]
    _SAMPLE_INDEX += 1

    from pipeline import pipeline as pipeline_orchestrator

    db = SessionLocal()
    try:
        result = pipeline_orchestrator.classify_text(
            sample["text"], level=sample["level"], source=sample["source"]
        )
        row = IncidentRow(
            timestamp=utcnow(),
            source=sample["source"],
            level=sample["level"],
            raw_text=sample["text"],
            cleaned_text=result["cleaned_text"],
            category=result["category"],
            severity=result["severity"],
            confidence=result["confidence"],
            classified_by=result["classified_by"],
            regex_rule=result.get("regex_rule"),
            is_known=result["is_known"],
            pipeline_trace=json.dumps(result["pipeline_trace"]),
            explanation=result["explanation"],
            remediation=result["remediation"],
            detection_ms=result["detection_ms"],
            status="Open",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"type": "incident", "data": row.to_dict()}
    except Exception:  # noqa: BLE001
        db.rollback()
        return None
    finally:
        db.close()

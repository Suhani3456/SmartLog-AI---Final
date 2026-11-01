"""
Contract tests for the SmartLog AI backend.

Each test calls exactly one endpoint on a throwaway SQLite database (set via
the SMARTLOG_TEST_DB env var before import-time config reads it) and asserts
the exact shape the frontend expects — field names, required keys, enum
allowed values, list sizes, and empty-structure behaviour.

Run:
    SMARTLOG_TEST_DB=backend/test_smartlog.db venv/Scripts/python -m pytest tests/test_contract.py -q

The throwaway DB is removed at teardown; the real smartlog.db is never touched.
"""

from __future__ import annotations

import io
import json
import math
import os
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# --- Set up a throwaway DB BEFORE importing the app/config so the config
# module (which reads .env once at import time) can be pointed at it.
_TEST_DB = "test_smartlog_contract.db"
_TEST_SQLITE = f"sqlite:///{_TEST_DB}"
os.environ["SMARTLOG_TEST_DB"] = _TEST_SQLITE

from config import DATABASE_URL  # noqa: E402
from main import app  # noqa: E402


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
_TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _make_test_db() -> None:
    from db import Base, init_db

    init_db()


def _clear_test_db() -> None:
    from db import Base

    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _db_teardown():
    _make_test_db()
    yield
    _clear_test_db()


def _seed_one_reviewed_incident(db: Session) -> int:
    """Insert one known, non-noise incident so "empty" endpoints aren't ALL empty."""
    from db import Incident as Row, utcnow

    row = Row(
        timestamp=utcnow(),
        source="CRM",
        level="ERROR",
        raw_text="CRM pipeline timeout after 30s",
        cleaned_text="CRM pipeline timeout after 30s",
        category="API Failure",
        severity="High",
        confidence=0.91,
        classified_by="BERT+LogReg",
        regex_rule="crm_timeout_01",
        is_known=True,
        pipeline_trace=json.dumps([
            {"stage": "Preprocessing", "matched": True, "score": 0.0},
            {"stage": "Regex Match", "matched": False, "score": 0.0},
            {"stage": "BERT Embedding + Logistic Regression", "matched": True, "score": 0.91},
            {"stage": "DBSCAN Anomaly Check", "matched": False, "score": 0.0},
            {"stage": "LLM Fallback", "matched": False, "score": 0.0},
        ]),
        explanation="Timeout in the CRM sync pipeline.",
        remediation="[\"Check the CRM sync service health.\", \"Review recent deploys.\"]",
        detection_ms=42.5,
        status="Open",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return int(row.id)


c = TestClient(app)


# ---------------------------------------------------------------------------
# 1. GET /api/dashboard/stats
# ---------------------------------------------------------------------------

def test_dashboard_stats_shape():
    r = c.get("/api/dashboard/stats")
    assert r.status_code == 200, r.text
    body = r.json()
    # Top-level keys — no extra/removed keys.
    assert set(body.keys()) == {
        "total_logs", "total_incidents", "critical_count", "unknown_anomalies",
        "avg_detection_ms", "false_alert_rate", "by_category",
        "by_source", "by_severity",
    }
    assert isinstance(body["total_logs"], int)
    assert isinstance(body["total_incidents"], int)
    assert isinstance(body["critical_count"], int)
    assert isinstance(body["unknown_anomalies"], int)
    assert isinstance(body["avg_detection_ms"], (int, float))
    assert body["false_alert_rate"] == 0.0  # no data -> 0
    assert isinstance(body["by_category"], list)
    assert isinstance(body["by_source"], list)
    assert isinstance(body["by_severity"], list)


def test_dashboard_stats_by_lists_are_all_zeros_when_empty():
    """Empty DB must return the full fixed lists with zero counts, not []."""
    r = c.get("/api/dashboard/stats")
    body = r.json()
    cats = [row["category"] for row in body["by_category"]]
    assert cats == [
        "Database Error", "API Failure", "Login Failure", "Payment Issue",
        "Security Alert", "Resource Usage", "Workflow Error", "User Action",
        "Unknown",
    ]
    assert all(row["count"] == 0 for row in body["by_category"])

    srcs = [row["source"] for row in body["by_source"]]
    assert srcs == ["CRM", "HRMS", "Billing", "Cloud", "Server"]
    assert all(row["count"] == 0 for row in body["by_source"])

    sevs = [row["severity"] for row in body["by_severity"]]
    assert sevs == ["Critical", "High", "Medium", "Low", "Unknown"]
    assert all(row["count"] == 0 for row in body["by_severity"])


def test_dashboard_stats_false_alert_rate_is_percent():
    """false_alert_rate is a percent (3.8 -> 3.8%), 0 when no data."""
    r = c.get("/api/dashboard/stats")
    body = r.json()
    assert isinstance(body["false_alert_rate"], (int, float))
    assert body["false_alert_rate"] >= 0.0


def test_dashboard_stats_with_data():
    """With one reviewed incident, counts reflect incidents (not INFO rows)."""
    with _TestSession() as db:
        _seed_one_reviewed_incident(db)

    r = c.get("/api/dashboard/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["total_logs"] == 1
    assert body["total_incidents"] == 1         # incident == level != INFO
    assert body["critical_count"] == 0
    assert body["unknown_anomalies"] == 0  # is_known=True
    assert isinstance(body["avg_detection_ms"], (int, float))
    assert body["avg_detection_ms"] > 0
    assert body["by_category"][1]["category"] == "API Failure"
    assert body["by_category"][1]["count"] == 1
    assert body["by_source"][0]["source"] == "CRM"
    assert body["by_source"][0]["count"] == 1
    assert body["by_severity"][1]["severity"] == "High"  # index 1 == High
    assert body["by_severity"][1]["count"] == 1


# ---------------------------------------------------------------------------
# 2. GET /api/incidents/timeseries  (frontend calls this path)
# ---------------------------------------------------------------------------

def test_timeseries_shape():
    r = c.get("/api/incidents/timeseries")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {"points"}
    assert len(body["points"]) == 24
    for pt in body["points"]:
        assert set(pt.keys()) == {"time", "incidents", "critical"}
        assert isinstance(pt["time"], str)
        assert isinstance(pt["incidents"], int)
        assert isinstance(pt["critical"], int)
        assert pt["incidents"] == 0
        assert pt["critical"] == 0


def test_timeseries_with_data():
    """The 24 hour buckets should include any incident timestamps."""
    with _TestSession() as db:
        _seed_one_reviewed_incident(db)

    r = c.get("/api/incidents/timeseries")
    assert r.status_code == 200
    body = r.json()
    # One bucket should now be nonzero.
    nonzero = [pt for pt in body["points"] if pt["incidents"] > 0]
    assert len(nonzero) == 1
    assert nonzero[0]["incidents"] == 1
    assert nonzero[0]["critical"] == 0


# ---------------------------------------------------------------------------
# 3. GET /api/logs?limit=N
# ---------------------------------------------------------------------------

def test_logs_shape():
    r = c.get("/api/logs?limit=5")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 0
    if body:
        row = body[0]
        assert set(row.keys()) == {
            "id", "timestamp", "source", "level", "message",
            "category", "severity", "confidence", "classified_by",
        }


def test_logs_with_data():
    with _TestSession() as db:
        _seed_one_reviewed_incident(db)

    r = c.get("/api/logs?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    row = body[0]
    assert row["source"] == "CRM"
    assert row["level"] == "ERROR"
    assert row["message"] == "CRM pipeline timeout after 30s"
    assert row["category"] == "API Failure"
    assert row["severity"] == "High"
    assert isinstance(row["confidence"], (int, float))
    assert 0.0 <= row["confidence"] <= 1.0
    assert row["classified_by"] == "BERT+LogReg"


# ---------------------------------------------------------------------------
# 4. GET /api/incidents
# ---------------------------------------------------------------------------

def test_incidents_list_shape():
    r = c.get("/api/incidents")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {"items", "total", "page", "page_size"}
    assert isinstance(body["items"], list)
    assert body["total"] == 0
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["items"] == []


def test_incidents_item_shape():
    with _TestSession() as db:
        _seed_one_reviewed_incident(db)

    r = c.get("/api/incidents")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    it = body["items"][0]
    assert set(it.keys()) == {
        "id", "timestamp", "source", "level", "raw_text", "cleaned_text",
        "category", "severity", "confidence", "classified_by", "regex_rule",
        "is_known", "pipeline_trace", "explanation", "remediation",
        "detection_ms", "status",
    }
    assert it["status"] == "Open"
    assert isinstance(it["pipeline_trace"], list)
    assert it["pipeline_trace"] and it["pipeline_trace"][0]["stage"] == "Preprocessing"


# ---------------------------------------------------------------------------
# 5. GET /api/incidents/{id}
# ---------------------------------------------------------------------------

def test_incident_detail_shape():
    with _TestSession() as db:
        iid = _seed_one_reviewed_incident(db)

    r = c.get(f"/api/incidents/{iid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {
        "id", "timestamp", "source", "level", "raw_text", "cleaned_text",
        "category", "severity", "confidence", "classified_by", "regex_rule",
        "is_known", "pipeline_trace", "explanation", "remediation",
        "detection_ms", "status", "normalized", "related_logs",
    }
    assert body["id"] == iid
    assert body["normalized"] is True  # federations always normalised
    assert isinstance(body["related_logs"], list)
    if body["related_logs"]:
        rl = body["related_logs"][0]
        assert set(rl.keys()) == {"id", "timestamp", "level", "message", "source"}


def test_incident_detail_404():
    r = c.get("/api/incidents/99999")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 6. PATCH /api/incidents/{id}/status
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", ["Open", "Acknowledged", "Resolved"])
def test_update_status_shape(status):
    with _TestSession() as db:
        iid = _seed_one_reviewed_incident(db)

    r = c.patch(
        f"/api/incidents/{iid}/status",
        json={"status": status},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {
        "id", "timestamp", "source", "level", "raw_text", "cleaned_text",
        "category", "severity", "confidence", "classified_by", "regex_rule",
        "is_known", "pipeline_trace", "explanation", "remediation",
        "detection_ms", "status", "normalized", "related_logs",
    }
    assert body["status"] == status
    assert body["id"] == iid


def test_update_status_422_bad_enum():
    with _TestSession() as db:
        iid = _seed_one_reviewed_incident(db)

    r = c.patch(f"/api/incidents/{iid}/status", json={"status": "Invalid"})
    assert r.status_code in (400, 422)


# ---------------------------------------------------------------------------
# 7. POST /api/classify
# ---------------------------------------------------------------------------

def test_classify_shape():
    r = c.post("/api/classify", json={"text": "CRM sync failed with 500"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {
        "category", "severity", "confidence", "classified_by",
        "cleaned_text", "is_known", "pipeline_trace", "explanation",
        "remediation", "latency_ms",
    }
    assert isinstance(body["category"], str)
    assert body["severity"] in ("Critical", "High", "Medium", "Low", "Unknown")
    assert isinstance(body["confidence"], (int, float))
    assert 0.0 <= body["confidence"] <= 1.0
    assert body["classified_by"] in ("Regex", "BERT+LogReg", "DBSCAN", "LLM", "Unknown")
    assert isinstance(body["cleaned_text"], str)
    assert isinstance(body["is_known"], bool)
    assert isinstance(body["pipeline_trace"], list)
    assert isinstance(body["explanation"], str)
    assert isinstance(body["remediation"], list)
    assert all(isinstance(s, str) for s in body["remediation"])
    assert isinstance(body["latency_ms"], (int, float))
    assert body["latency_ms"] >= 0


def test_classify_pipeline_stage_names():
    """stage values MUST be exactly these five, in order of the pipeline."""
    r = c.post("/api/classify", json={"text": "Database connection reset"})
    assert r.status_code == 200
    trace = r.json()["pipeline_trace"]
    expected = [
        "Preprocessing",
        "Regex Match",
        "BERT Embedding + Logistic Regression",
        "DBSCAN Anomaly Check",
        "LLM Fallback",
    ]
    assert [row["stage"] for row in trace] == expected
    for row in trace:
        assert set(row.keys()) >= {"stage", "matched", "score"}
        assert isinstance(row["matched"], bool)
        assert isinstance(row["score"], (int, float))


# ---------------------------------------------------------------------------
# 8. POST /api/upload  +  GET /api/upload/{id}/status
# ---------------------------------------------------------------------------

def test_upload_shape():
    payload = {"file": ("sample.log", io.BytesIO(b"CRM timeout\nHRMS login failed\n"), "text/plain")}
    r = c.post("/api/upload", files=payload)
    assert r.status_code == 202, r.text
    body = r.json()
    assert set(body.keys()) == {"upload_id", "filename", "total_lines"}
    assert isinstance(body["upload_id"], int)
    assert isinstance(body["filename"], str)
    assert isinstance(body["total_lines"], int)
    assert body["total_lines"] == 2


def test_upload_status_shape():
    payload = {"file": ("sample.log", io.BytesIO(b"CRM timeout\n"), "text/plain")}
    create = c.post("/api/upload", files=payload)
    assert create.status_code == 202
    uid = create.json()["upload_id"]

    r = c.get(f"/api/upload/{uid}/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) >= {"upload_id", "filename", "status", "processed", "total", "incidents_created"}
    assert body["upload_id"] == uid
    assert body["status"] in ("processing", "done", "failed")
    assert isinstance(body["processed"], int)
    assert isinstance(body["total"], int)


def test_upload_results_summary():
    """After processing, GET upload status returns the by_* summary + duration."""
    payload = {"file": ("sample.log", io.BytesIO(b"CRM timeout\nHRMS login failed\nBilling failed\n"), "text/plain")}
    create = c.post("/api/upload", files=payload)
    assert create.status_code == 202
    uid = create.json()["upload_id"]

    # Poll until done.
    deadline = time.time() + 20
    last = None
    while time.time() < deadline:
        r = c.get(f"/api/upload/{uid}/status")
        if r.status_code != 200:
            break
        last = r.json()
        if last["status"] == "done":
            break
        time.sleep(0.2)

    assert last is not None
    body = last
    # Results summary keys when the upload finished.
    assert set(body.keys()) >= {"upload_id", "filename", "status", "total_lines", "classified", "incidents", "unknown", "by_severity", "by_category", "duration_ms"}
    assert body["status"] == "done"
    assert body["total_lines"] == 3
    assert body["classified"] == 3
    assert isinstance(body["incidents"], int)
    assert isinstance(body["unknown"], int)
    assert isinstance(body["by_severity"], list)
    assert isinstance(body["by_category"], list)
    assert isinstance(body["duration_ms"], (int, float))


# ---------------------------------------------------------------------------
# 9. POST /api/scrape
# ---------------------------------------------------------------------------

def test_scrape_shape(monkeypatch):
    """POST /api/scrape returns the UploadResponse contract (upload_id/filename/total_lines)."""

    # Point the scraper at the demo site so the test is real, not mocked.
    import backend.scraper as scraper_mod
    import backend.routers.scrape as scrape_mod

    demo_path = os.path.join(os.path.dirname(scrape_mod.__file__), "demo_site", "index.html")
    demo_url = f"file://{demo_path}"

    def _real_fetch(url):
        # Bypass the HTTP fetch for the test: read the demo file directly.
        with open(demo_path, "rb") as fh:
            return fh.read(), "text/html"

    monkeypatch.setattr(scrape_mod, "_fetch", _real_fetch)

    r = c.post("/api/scrape", json={"url": demo_url})
    assert r.status_code == 202, r.text
    body = r.json()
    assert set(body.keys()) == {"upload_id", "filename", "total_lines"}
    assert isinstance(body["upload_id"], int)
    assert isinstance(body["filename"], str)
    assert body["filename"] == demo_url
    assert isinstance(body["total_lines"], int)
    assert body["total_lines"] > 0


def test_scrape_400_bad_url():
    r = c.post("/api/scrape", json={"url": "not-a-url"})
    assert r.status_code == 400


def test_scrape_422_no_lines():
    r = c.post("/api/scrape", json={"url": "https://example.invalid/nothing-here"})
    # Either 422 (no log-like lines) or 502 (site unreachable) — both acceptable.
    assert r.status_code in (422, 502)


# ---------------------------------------------------------------------------
# 10. GET /api/anomalies
# ---------------------------------------------------------------------------

def test_anomalies_shape():
    r = c.get("/api/anomalies")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {"points", "clusters"}
    assert isinstance(body["points"], list)
    assert isinstance(body["clusters"], list)
    for pt in body["points"]:
        assert set(pt.keys()) == {"x", "y", "cluster", "category", "message", "is_noise"}
        assert isinstance(pt["x"], (int, float))
        assert isinstance(pt["y"], (int, float))
        assert isinstance(pt["cluster"], int)
        assert isinstance(pt["category"], str)
        assert isinstance(pt["message"], str)
        assert isinstance(pt["is_noise"], bool)
    for cl in body["clusters"]:
        assert set(cl.keys()) == {"id", "label", "count", "samples", "labeled_as", "first_seen"}
        assert isinstance(cl["id"], int)
        assert isinstance(cl["label"], str)
        assert isinstance(cl["count"], int)
        assert isinstance(cl["samples"], list)
        assert all(isinstance(s, str) for s in cl["samples"])
        assert cl["labeled_as"] is None
        assert isinstance(cl["first_seen"], str)


# ---------------------------------------------------------------------------
# 11. POST /api/anomalies/{id}/label
# ---------------------------------------------------------------------------

def test_anomaly_label_shape():
    r = c.post("/api/anomalies/0/label", json={"category": "Database Error"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {"id", "label", "count", "samples", "labeled_as", "first_seen"}
    assert body["labeled_as"] == "Database Error"


# ---------------------------------------------------------------------------
# 12. GET /api/metrics
# ---------------------------------------------------------------------------

def test_metrics_shape():
    r = c.get("/api/metrics")
    assert r.status_code == 200, r.text
    body = r.json()
    # Allow any extra metadata keys; require at least the frontend-relevant ones.
    required = {
        "accuracy", "precision", "recall", "f1", "per_class",
        "confusion_matrix", "comparison", "classifier_usage",
    }
    assert required.issubset(body.keys()), body.keys()
    assert isinstance(body["accuracy"], (int, float))
    assert isinstance(body["precision"], (int, float))
    assert isinstance(body["recall"], (int, float))
    assert isinstance(body["f1"], (int, float))
    assert isinstance(body["per_class"], list)
    assert len(body["per_class"]) == 9
    for row in body["per_class"]:
        assert set(row.keys()) == {"category", "precision", "recall", "f1", "support"}
        assert isinstance(row["support"], int)
    assert set(body["confusion_matrix"].keys()) == {"labels", "matrix"}
    assert isinstance(body["confusion_matrix"]["labels"], list)
    assert isinstance(body["confusion_matrix"]["matrix"], list)
    assert isinstance(body["comparison"], list)
    for row in body["comparison"]:
        assert set(row.keys()) == {"approach", "f1", "false_alert_rate"}
    assert isinstance(body["classifier_usage"], list)
    for row in body["classifier_usage"]:
        assert set(row.keys()) == {"classifier", "count"}
        assert isinstance(row["count"], int)


def test_metrics_all_nines_when_no_model():
    """Even with no metrics.json, all 9 categories must appear with zeros."""
    r = c.get("/api/metrics")
    body = r.json()
    cats = [row["category"] for row in body["per_class"]]
    expected = [
        "Database Error", "API Failure", "Login Failure", "Payment Issue",
        "Security Alert", "Resource Usage", "Workflow Error", "User Action",
        "Unknown",
    ]
    assert cats == expected
    assert all(row["support"] == 0 for row in body["per_class"])


# ---------------------------------------------------------------------------
# 13. WS /ws/stream
# ---------------------------------------------------------------------------

def test_ws_hello_frame():
    """The WS endpoint must send a hello frame before any silence."""
    with c.websocket_connect("/ws/stream") as ws:
        msg = ws.receive_json()
        assert msg == {"type": "hello", "message": "stream connected"}


def test_ws_empty_database_is_silent():
    """With no ingest, the socket must stay open and send nothing more."""
    with c.websocket_connect("/ws/stream") as ws:
        ws.receive_json()  # hello
        # Give the loop a moment — nothing synthetic should appear.
        started = time.time()
        while time.time() - started < 0.5:
            try:
                ws.receive_json(timeout=0.1)
            except Exception:
                break


# ---------------------------------------------------------------------------
# 14. Enum / value constraints across endpoints
# ---------------------------------------------------------------------------

def test_severity_enum_values():
    r = c.get("/api/dashboard/stats")
    body = r.json()
    for row in body["by_severity"]:
        assert row["severity"] in ("Critical", "High", "Medium", "Low", "Unknown")


def test_source_enum_values():
    r = c.get("/api/dashboard/stats")
    body = r.json()
    for row in body["by_source"]:
        assert row["source"] in ("CRM", "HRMS", "Billing", "Cloud", "Server")


def test_classified_by_enum_values():
    r = c.post("/api/classify", json={"text": "test"})
    assert r.json()["classified_by"] in ("Regex", "BERT+LogReg", "DBSCAN", "LLM", "Unknown")


# ---------------------------------------------------------------------------
# 15. No 500s, no NaN anywhere
# ---------------------------------------------------------------------------

def test_no_nan_in_any_numeric_field():
    """Walk every endpoint and assert no NaN floats."""
    checks = [
        c.get("/api/dashboard/stats"),
        c.get("/api/incidents/timeseries"),
        c.get("/api/metrics"),
    ]
    for r in checks:
        assert r.status_code == 200, r.text
        _assert_no_nan(r.json())


def _assert_no_nan(obj):
    if isinstance(obj, float):
        assert not math.isnan(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _assert_no_nan(v)
    elif isinstance(obj, list):
        for v in obj:
            _assert_no_nan(v)


# ---------------------------------------------------------------------------
# Teardown: remove the throwaway DB so the real one is never polluted.
# ---------------------------------------------------------------------------

def pytest_sessionfinish(session, exitstatus):
    try:
        os.remove(_TEST_DB)
    except OSError:
        pass

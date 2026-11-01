"""
SmartLog AI — incidents + dashboard routes.

Covers: /api/dashboard/stats, /api/incidents, /api/incidents/{id},
/api/incidents/{id}/status, /api/incidents/timeseries.
"""

import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from db import Incident as IncidentRow, get_db
from schemas import (
    CategoryCount,
    DashboardStats,
    Incident,
    IncidentListResponse,
    IncidentStatusUpdate,
    SeverityCount,
    SourceCount,
    TimeseriesPoint,
    TimeseriesResponse,
)

# Backward-compat shim: the old namedtuples/counts still referenced during
# the dashboard rewrite. Keep them defined here so the router is self-contained.

router = APIRouter()

VALID_STATUSES = {"Open", "Acknowledged", "Resolved"}


# --- helpers ------------------------------------------------------------------

def _load_incident(db: Session, incident_id: int) -> IncidentRow:
    row = db.get(IncidentRow, incident_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return row


def _to_schema(row: IncidentRow) -> Incident:
    return Incident(**row.to_dict())


# --- Dashboard stats ---------------------------------------------------------

@router.get("/api/dashboard/stats")
def dashboard_stats(db: Session = Depends(get_db)) -> dict:
    """KPI strip + chart data for the Dashboard page."""
    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    prev_24h_end = last_24h
    prev_24h_start = last_24h - timedelta(hours=24)

    total_logs = db.query(func.count(IncidentRow.id)).scalar() or 0
    total_incidents = total_logs  # every stored row is a classified log
    critical_count = (
        db.query(func.count(IncidentRow.id))
        .filter(IncidentRow.severity == "Critical")
        .scalar() or 0
    )
    unknown_anomalies = (
        db.query(func.count(IncidentRow.id))
        .filter(IncidentRow.is_known.is_(False))
        .scalar() or 0
    )
    avg_detection_ms = db.query(func.avg(IncidentRow.detection_ms)).scalar() or 0.0
    # False alert rate is a real metric after Phase 3 training; 0.0 until then.
    false_alert_rate = 0.0

    def _count_between(start: datetime, end: datetime) -> tuple[int, int, int]:
        """(logs, incidents, critical) in [start, end)."""
        rows = (
            db.query(IncidentRow.is_known, IncidentRow.severity)
            .filter(IncidentRow.timestamp >= start, IncidentRow.timestamp < end)
            .all()
        )
        logs = len(rows)
        incidents = sum(1 for _, sev in rows if sev != "INFO")
        crit = sum(1 for _, sev in rows if sev == "Critical")
        return logs, incidents, crit

    logs_now, incidents_now, crit_now = _count_between(last_24h, now)
    logs_prev, incidents_prev, crit_prev = _count_between(prev_24h_start, prev_24h_end)

    _ALL_CATEGORIES = [
        "Database Error", "API Failure", "Login Failure", "Payment Issue",
        "Security Alert", "Resource Usage", "Workflow Error", "User Action",
        "Unknown",
    ]
    _ALL_SOURCES = ["CRM", "HRMS", "Billing", "Cloud", "Server"]
    _ALL_SEVERITIES = ["Critical", "High", "Medium", "Low", "Unknown"]

    # Count only real incidents: level != INFO (or category == Unknown).
    incident_rows = (
        db.query(IncidentRow.category, IncidentRow.source, IncidentRow.severity)
        .filter(IncidentRow.level != "INFO")
        .all()
    )
    cat_counts: dict[str, int] = {}
    src_counts: dict[str, int] = {}
    sev_counts: dict[str, int] = {}
    for cat, src, sev in incident_rows:
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        src_counts[src] = src_counts.get(src, 0) + 1
        sev_counts[sev] = sev_counts.get(sev, 0) + 1

    by_category = [CategoryCount(category=c, count=cat_counts.get(c, 0)) for c in _ALL_CATEGORIES]
    by_source = [SourceCount(source=s, count=src_counts.get(s, 0)) for s in _ALL_SOURCES]
    by_severity = [SeverityCount(severity=s, count=sev_counts.get(s, 0)) for s in _ALL_SEVERITIES]

    return {
        "total_logs": total_logs,
        "total_incidents": total_incidents,
        "critical_count": critical_count,
        "unknown_anomalies": unknown_anomalies,
        "avg_detection_ms": round(avg_detection_ms, 2),
        "false_alert_rate": false_alert_rate,
        "by_category": by_category,
        "by_source": by_source,
        "by_severity": by_severity,
    }


# --- List ---------------------------------------------------------------------

@router.get("/api/incidents", response_model=IncidentListResponse)
def list_incidents(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    severity: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="Substring of the raw log"),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    sort_by: str = Query("timestamp", alias="sortBy"),
    sort_dir: str = Query("desc", alias="sortDir", pattern="^(asc|desc)$"),
) -> IncidentListResponse:
    """Filterable, sortable, paginated incident table."""
    q = db.query(IncidentRow)
    if severity:
        q = q.filter(IncidentRow.severity == severity)
    if category:
        q = q.filter(IncidentRow.category == category)
    if source:
        q = q.filter(IncidentRow.source == source)
    if status:
        if status not in VALID_STATUSES:
            raise HTTPException(status_code=422, detail="Invalid status filter")
        q = q.filter(IncidentRow.status == status)
    if search:
        q = q.filter(IncidentRow.raw_text.ilike(f"%{search}%"))
    if date_from:
        try:
            q = q.filter(IncidentRow.timestamp >= datetime.fromisoformat(date_from))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Bad from date") from exc
    if date_to:
        try:
            q = q.filter(IncidentRow.timestamp <= datetime.fromisoformat(date_to))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Bad to date") from exc

    sort_column = {
        "timestamp": IncidentRow.timestamp,
        "severity": IncidentRow.severity,
        "category": IncidentRow.category,
        "source": IncidentRow.source,
        "confidence": IncidentRow.confidence,
        "detection_ms": IncidentRow.detection_ms,
    }.get(sort_by, IncidentRow.timestamp)
    q = q.order_by(
        sort_column.asc() if sort_dir == "asc" else sort_column.desc()
    )

    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    return IncidentListResponse(
        items=[_to_schema(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


# --- Timeseries (registered BEFORE the /{incident_id} detail route so the
# fixed path is never swallowed by the id path) -------------------------------

@router.get("/api/incidents/timeseries", response_model=TimeseriesResponse)
def incidents_timeseries(
    db: Session = Depends(get_db),
    days: int = Query(7, ge=1, le=30),
    tz_offset: int = Query(0, ge=-12, le=14),
) -> TimeseriesResponse:
    """Incident counts bucketed per hour, 24 buckets ending at the current hour."""
    now = datetime.utcnow()
    end_hour = now.replace(minute=0, second=0, microsecond=0)
    start_hour = end_hour - timedelta(hours=23)
    rows = (
        db.query(IncidentRow)
        .filter(IncidentRow.timestamp >= start_hour)
        .all()
    )
    counts: dict[str, int] = {}
    critical_counts: dict[str, int] = {}
    for r in rows:
        bucket = r.timestamp.replace(minute=0, second=0, microsecond=0)
        key = bucket.isoformat()
        counts[key] = counts.get(key, 0) + 1
        if r.severity == "Critical":
            critical_counts[key] = critical_counts.get(key, 0) + 1

    points = []
    for i in range(24):
            bucket_hour = start_hour + timedelta(hours=i)
            key = bucket_hour.isoformat()
            points.append(TimeseriesPoint(
                time=key,
                incidents=counts.get(key, 0),
                critical=critical_counts.get(key, 0),
                timestamp="",
                count=0,
            ))
    return TimeseriesResponse(points=points)


# --- Detail / status ----------------------------------------------------------

@router.get("/api/incidents/{incident_id}", response_model=Incident)
def get_incident(incident_id: int, db: Session = Depends(get_db)) -> Incident:
    """Single incident for the detail drawer."""
    row = _load_incident(db, incident_id)
    d = row.to_dict()
    # Related logs: any other incidents in the same category/source within 1h.
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
    related_logs = [
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
    d["related_logs"] = related_logs
    return Incident(**d)


@router.patch("/api/incidents/{incident_id}/status", response_model=Incident)
def update_incident_status(
    incident_id: int,
    body: IncidentStatusUpdate,
    db: Session = Depends(get_db),
) -> Incident:
    """Status workflow: Open -> Acknowledged -> Resolved."""
    row = _load_incident(db, incident_id)
    row.status = body.status
    db.commit()
    db.refresh(row)
    d = row.to_dict()
    # Re-derive related logs + normalised flag to match GET /api/incidents/{id}.
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
    return Incident(**d)



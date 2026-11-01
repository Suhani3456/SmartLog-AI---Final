"""
SmartLog AI — Pydantic response/request schemas.

These mirror the frontend TypeScript types in `src/types/index.ts` EXACTLY
(same field names, same snake_case casing). Any change here must be mirrored
there and vice versa.
"""

import json
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# --- Shared building blocks ---------------------------------------------------

CategoryName = Literal[
    "Database Error",
    "API Failure",
    "Login Failure",
    "Payment Issue",
    "Security Alert",
    "Resource Usage",
    "Workflow Error",
    "User Action",
    "Unknown",
]

SeverityName = Literal["Critical", "High", "Medium", "Low"]
IncidentStatus = Literal["Open", "Acknowledged", "Resolved"]
ClassifierName = Literal["Regex", "BERT+LogReg", "DBSCAN", "LLM"]


class PipelineStage(BaseModel):
    """One row in the pipeline trace shown by the stepper UI."""

    stage: str            # "Preprocessing" | "Regex Match" | "BERT Embedding + Logistic Regression" | "DBSCAN Anomaly Check" | "LLM Fallback"
    matched: bool = True
    score: float = 0.0          # 0.0-1.0 when applicable, 0.0 when not decisive


class ClassificationResult(BaseModel):
    """Result of running one log line through the full hybrid pipeline."""

    category: CategoryName
    severity: SeverityName
    confidence: float
    classified_by: ClassifierName
    cleaned_text: str
    is_known: bool
    pipeline_trace: list[PipelineStage]
    explanation: str
    remediation: str


class ClassifyRequest(BaseModel):
    """POST /api/classify body."""

    text: str = Field(min_length=1, description="Raw log line to classify")


# --- Incidents ----------------------------------------------------------------

class Incident(BaseModel):
    """One classified log event, exactly as the frontend `Incident` type."""

    id: int
    timestamp: str
    source: str
    level: str
    raw_text: str
    cleaned_text: str
    category: str
    severity: str
    confidence: float
    classified_by: str
    regex_rule: Optional[str] = None
    is_known: bool
    pipeline_trace: list[PipelineStage]
    explanation: str
    remediation: str
    detection_ms: float
    status: IncidentStatus


class IncidentListResponse(BaseModel):
    """GET /api/incidents — paginated list."""

    items: list[Incident]
    total: int
    page: int
    page_size: int


class IncidentStatusUpdate(BaseModel):
    """PATCH /api/incidents/{id}/status body."""

    status: IncidentStatus


# --- Dashboard ----------------------------------------------------------------

class CategoryCount(BaseModel):
    category: str
    count: int


class SourceCount(BaseModel):
    source: str
    count: int


class SeverityCount(BaseModel):
    severity: str
    count: int


class ChangeDelta(BaseModel):
    """Change vs the previous 24 h, used for the tiny deltas on the stat strip."""

    logs: int
    incidents: int
    critical: int


class DashboardStats(BaseModel):
    """GET /api/dashboard/stats — everything the KPI strip and charts need."""

    total_logs: int
    total_incidents: int
    critical_count: int
    unknown_anomalies: int
    avg_detection_ms: float
    false_alert_rate: float          # fraction 0.0-1.0
    change_vs_prev_24h: ChangeDelta
    by_category: list[CategoryCount]
    by_source: list[SourceCount]
    by_severity: list[SeverityCount]


class TimeseriesPoint(BaseModel):
    timestamp: str = ""
    count: int = 0


class TimeseriesResponse(BaseModel):
    """GET /api/incidents/timeseries."""

    points: list[TimeseriesPoint]


# --- Anomalies ----------------------------------------------------------------

class AnomalyPoint(BaseModel):
    """One 2D point for the DBSCAN scatter plot."""

    incident_id: int
    x: float
    y: float
    cluster_id: int                   # -1 == noise
    noise: bool


class AnomalyCluster(BaseModel):
    """A DBSCAN cluster summary (side list + label dialog)."""

    cluster_id: int                   # -1 == noise
    size: int
    is_noise: bool
    sample_logs: list[str]
    labeled_category: Optional[str] = None


class ClustersResponse(BaseModel):
    """GET /api/anomalies/clusters."""

    points: list[AnomalyPoint]
    clusters: list[AnomalyCluster]


class ClusterLabelRequest(BaseModel):
    """POST /api/anomalies/clusters/{id}/label body."""

    category: CategoryName
    notes: str = ""


class ClusterLabelResponse(BaseModel):
    saved: bool
    training_example_id: int


# --- Metrics ------------------------------------------------------------------

class PerClassMetric(BaseModel):
    category: str
    precision: float
    recall: float
    f1: float
    support: int


class BaselineRow(BaseModel):
    approach: str                     # "Rule-based only" | "ML only" | "Hybrid"
    f1: float
    false_alert_rate: float


class ClassifierUsageRow(BaseModel):
    classified_by: str
    share: float


class MetricsResponse(BaseModel):
    """GET /api/metrics — serves the real backend/models/metrics.json shape."""

    accuracy: float
    precision: float
    recall: float
    f1: float
    per_class: list[PerClassMetric]
    confusion_matrix: dict[str, Any]  # {"labels": [...], "matrix": [[...]]}
    comparison: list[BaselineRow]
    classifier_usage: list[ClassifierUsageRow]


# --- Upload -------------------------------------------------------------------

class UploadResponse(BaseModel):
    """POST /api/upload — upload accepted, processing runs in the background."""

    upload_id: int
    filename: str
    total_lines: int


class ScrapeRequest(BaseModel):
    """POST /api/scrape body: the URL to fetch, optionally one CSS selector."""
    url: str
    selector: Optional[str] = None


class UploadStatus(BaseModel):
    """GET /api/upload/{upload_id}/status — poll for the progress bar."""

    upload_id: int
    filename: str
    status: Literal["processing", "done", "failed"]
    processed: int
    total: int
    incidents_created: int


# --- Health / stream ----------------------------------------------------------

class HealthResponse(BaseModel):
    """GET /api/health."""

    status: Literal["ok"]
    models_loaded: bool
    version: str


class StreamEvent(BaseModel):
    """One event broadcast on WS /ws/stream (same shape as an Incident row)."""

    type: Literal["incident"] = "incident"
    data: Incident

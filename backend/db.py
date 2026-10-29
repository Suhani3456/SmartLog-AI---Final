"""
SmartLog AI — SQLAlchemy database layer.

Tables:
  Incident          every classified log event (one row per log).
  UploadedFile      bookkeeping for batch uploads (.log/.txt/.csv) + progress.
  TrainingExample   human feedback from the Anomaly Explorer ("Label cluster")
                    saved as a future training row.
"""

from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import DATABASE_URL

# --- Engine / session factory -------------------------------------------------

# check_same_thread=False: FastAPI may touch the SQLite file from worker threads.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Declarative base for all SmartLog tables."""


def utcnow() -> datetime:
    """Current UTC time (naive, stored as ISO strings client-side)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --- Tables -------------------------------------------------------------------

class Incident(Base):
    """A single classified log event."""

    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # What arrived
    timestamp = Column(DateTime, default=utcnow, index=True)
    source = Column(String(32), index=True)          # CRM | HRMS | Billing | Cloud/Server
    level = Column(String(16), index=True)           # INFO | WARN | ERROR | CRITICAL | DEBUG
    raw_text = Column(Text, nullable=False)           # original log line
    cleaned_text = Column(Text, default="")           # after preprocessing

    # Classification contract
    category = Column(String(32), index=True)
    severity = Column(String(16), index=True)         # Critical | High | Medium | Low
    confidence = Column(Float, default=0.0)
    classified_by = Column(String(32))                # Regex | BERT+LogReg | DBSCAN | LLM
    regex_rule = Column(String(64), nullable=True)    # matched rule id, e.g. db_timeout_01
    is_known = Column(Boolean, default=True)          # False => unknown anomaly
    pipeline_trace = Column(Text, default="[]")       # JSON [{stage, matched, score}]
    explanation = Column(Text, default="")
    remediation = Column(Text, default="")
    detection_ms = Column(Float, default=0.0)

    # Ops workflow
    status = Column(String(16), default="Open", index=True)  # Open | Acknowledged | Resolved

    def to_dict(self) -> dict[str, Any]:
        """Dict matching the frontend `Incident` TypeScript type exactly."""
        import json

        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() + "Z",
            "source": self.source,
            "level": self.level,
            "raw_text": self.raw_text,
            "cleaned_text": self.cleaned_text,
            "category": self.category,
            "severity": self.severity,
            "confidence": round(self.confidence, 4),
            "classified_by": self.classified_by,
            "regex_rule": self.regex_rule,
            "is_known": bool(self.is_known),
            "pipeline_trace": json.loads(self.pipeline_trace or "[]"),
            "explanation": self.explanation,
            "remediation": self.remediation,
            "detection_ms": round(self.detection_ms or 0.0, 2),
            "status": self.status,
        }


class UploadedFile(Base):
    """A batch upload and its background-processing progress."""

    __tablename__ = "uploads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(256))
    total_lines = Column(Integer, default=0)
    processed = Column(Integer, default=0)
    incidents_created = Column(Integer, default=0)
    status = Column(String(16), default="processing")  # processing | done | failed
    created_at = Column(DateTime, default=utcnow)


class TrainingExample(Base):
    """Human label given to an anomaly cluster (feedback loop for retraining)."""

    __tablename__ = "training_examples"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id = Column(Integer, index=True)
    category = Column(String(32))                     # chosen by a human
    notes = Column(Text, default="")
    sample_logs = Column(Text, default="")            # JSON list of representative logs
    created_at = Column(DateTime, default=utcnow)


def init_db() -> None:
    """Create all tables if they do not exist yet (safe to call at startup)."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yield a scoped DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

"""
SmartLog AI — seed database with ~300 classified incidents.

Pre-populates realistic, uneven distributions:
- More Info/Low than Critical
- A couple of busy hours
- One noisy source system (Cloud/Server)
"""

import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from db import Incident as IncidentRow, SessionLocal, init_db, utcnow
from pipeline import pipeline as pipeline_orchestrator


def load_samples():
    samples = []
    csv_path = Path(__file__).parent / "data" / "sample_logs.csv"
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                text = row.get("message") or row.get("text") or ""
                if not text and row:
                    text = " ".join(str(v) for v in row.values() if v)
                samples.append({
                    "level": (row.get("level") or "INFO").strip().upper(),
                    "source": (row.get("source") or "Cloud/Server").strip(),
                    "text": text.strip(),
                    "timestamp": row.get("timestamp"),
                })
    return samples


def main():
    init_db()
    # Load models
    try:
        pipeline_orchestrator.load_models()
    except Exception:
        pass

    samples = load_samples()
    if not samples:
        print("No samples found, exiting")
        return

    db = SessionLocal()
    try:
        # Clear existing incidents for clean seed? The requirement says "pre-populates" - better to be idempotent but add if empty or just add
        count = db.query(IncidentRow).count()
        if count > 50:  # Already has data
            print(f"Already have {count} incidents, skipping seed")
            return

        base = datetime(2026, 10, 30, 0, 0, 0)
        created = 0
        # Bias towards Cloud/Server (noisy source) and certain busy hours (e.g., 9-11 AM, 2-4 PM)
        for i in range(300):
            sample = random.choice(samples)
            # Create timestamps clustered in busy hours
            if random.random() < 0.4:
                hour = random.choice([9, 10, 11, 14, 15, 16])
            else:
                hour = random.randint(0, 23)
            minute = random.randint(0, 59)
            ts = base.replace(hour=hour, minute=minute, second=random.randint(0, 59)) + timedelta(days=random.randint(-2, 0))
            # Weight levels - more INFO/Low
            level = random.choices(['INFO', 'WARN', 'ERROR', 'CRITICAL'], weights=[0.45, 0.35, 0.15, 0.05])[0]
            source = sample['source']
            if random.random() < 0.4:  # Make Cloud/Server noisier
                source = 'Cloud/Server'
            text = sample['text']
            try:
                result = pipeline_orchestrator.classify_text(text, level=level, source=source)
                row = IncidentRow(
                    timestamp=ts,
                    source=source,
                    level=level,
                    raw_text=text,
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
                    status=random.choice(["Open", "Acknowledged", "Resolved"]),
                )
                db.add(row)
                created += 1
                if created % 50 == 0:
                    db.commit()
            except Exception:
                continue
        db.commit()
        print(f"Seeded {created} incidents")
    finally:
        db.close()


if __name__ == "__main__":
    main()

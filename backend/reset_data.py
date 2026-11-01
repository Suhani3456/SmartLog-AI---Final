"""
SmartLog AI — reset to the zero state.

Plain maintenance script (no UI). Deletes every ingested row so the
application returns to the state it has on a fresh start:

  - incidents             (all classified logs -> the Dashboard KPIs/tables)
  - uploads               (bookkeeping for uploaded/scraped batches)
  - training_examples     (human feedback saved from the Anomaly Explorer)

Run from the backend/ directory:
    python reset_data.py --yes
"""

import argparse

from db import (
    Incident as IncidentRow,
    SessionLocal,
    TrainingExample,
    UploadedFile,
    init_db,
)


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        counts = {
            "incidents": db.query(IncidentRow).delete(),
            "uploads": db.query(UploadedFile).delete(),
            "training_examples": db.query(TrainingExample).delete(),
        }
        db.commit()
        print(
            f"Deleted: {counts['incidents']} incidents, "
            f"{counts['uploads']} upload records, "
            f"{counts['training_examples']} training examples. "
            "SmartLog is back to the zero state."
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset the SmartLog database to the zero state.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt.",
    )
    args = parser.parse_args()
    if not args.yes:
        answer = input("This deletes ALL ingested logs and feedback. Type 'yes' to confirm: ")
        if answer.strip().lower() != "yes":
            print("Aborted. The database is untouched.")
            raise SystemExit(1)
    main()

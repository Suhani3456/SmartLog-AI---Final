"""Keep pytest off the developer's real smartlog.db.

config.py reads DATABASE_URL at import time, so this conftest must set the
env var BEFORE any backend module is imported. Every test session therefore
runs against a throwaway SQLite file instead of ingesting into smartlog.db.
"""

import os
import tempfile
from pathlib import Path

_TMP_DIR = tempfile.mkdtemp(prefix="smartlog-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TMP_DIR) / 'test.db'}"

# TestClient requests in these suites do not enter the app lifespan, so the
# tables must exist before any request runs: create them on the throwaway DB.
from db import init_db  # noqa: E402 — must follow the env override above

init_db()

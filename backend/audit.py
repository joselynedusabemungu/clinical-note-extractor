import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone


def _db_path() -> str:
    return os.environ.get("AUDIT_DB", "audit.db")


def init_db() -> None:
    with sqlite3.connect(_db_path()) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS extractions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                note_hash TEXT,
                extraction_json TEXT,
                needs_review INTEGER,
                deidentified INTEGER,
                abstention_reason TEXT
            )""")


def log_extraction(
    note: str,
    extraction_json: str,
    needs_review: bool,
    abstention_reason: str | None,
) -> None:
    note_hash = hashlib.sha256(note.encode("utf-8")).hexdigest()[:16]
    try:
        deid = int(bool(json.loads(extraction_json).get("deidentified", False)))
    except (TypeError, ValueError, AttributeError):
        deid = 0
    init_db()
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            "INSERT INTO extractions (timestamp, note_hash, extraction_json, needs_review, "
            "deidentified, abstention_reason) VALUES (?, ?, ?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(),
                note_hash,
                extraction_json,
                int(needs_review),
                deid,
                abstention_reason,
            ),
        )


init_db()

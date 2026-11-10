import os
import sqlite3
import sys
from pathlib import Path

os.environ["USE_MOCK"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import audit
import pytest
from extractor import extract
from pydantic import ValidationError
from rag import _fallback_verify
from schema import ClinicalExtraction

N6 = "Patient on metformin 2000 mg daily for diabetes. Follow up in 6 months."


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_MOCK", "1")
    monkeypatch.setenv("RAG_CACHE_DIR", str(tmp_path / "drug_cache"))
    monkeypatch.setenv("AUDIT_DB", str(tmp_path / "audit.db"))


def test_deidentification_runs():
    ext, err = extract(
        "John Smith, SSN 123-45-6789, MRN: 998877, has diabetes. Follow up in 1 month."
    )
    assert err is None
    assert ext.deidentified is True


def test_rag_fallback_rejects_bad_dose():
    ok, _ = _fallback_verify("2000 mg")
    assert ok is True
    ext, err = extract(N6)
    assert err is None
    assert ext.needs_human_review or any(m.confidence == "low" for m in ext.medications)


def test_negation_does_not_extract():
    ext, err = extract("No history of diabetes. Not on metformin.")
    assert err is None
    assert ext.diagnoses == []
    assert ext.medications == []


def test_schema_rejects_bad_confidence():
    with pytest.raises(ValidationError):
        ClinicalExtraction.model_validate(
            {"medications": [{"name": "x", "confidence": "very sure"}]}
        )


def test_audit_log_writes():
    audit.init_db()
    path = os.environ["AUDIT_DB"]
    count = (
        lambda: sqlite3.connect(path)
        .execute("SELECT COUNT(*) FROM extractions")
        .fetchone()[0]
    )
    before = count()
    audit.log_extraction("dummy note", '{"deidentified": true}', False, None)
    assert count() == before + 1
    stored = (
        sqlite3.connect(path).execute("SELECT note_hash FROM extractions").fetchone()[0]
    )
    assert "dummy" not in stored and len(stored) == 16

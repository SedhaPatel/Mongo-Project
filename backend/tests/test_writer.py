"""Tests for backend/app/memory/writer.py (PLAN Sections 7.2 and 7.4).

No API server and no live LLM/Voyage: measurements live in mock_db and the
lesson text resolves through the committed offline embedding fixture.
"""

from datetime import datetime
import json
from pathlib import Path

import pytest

from backend.app.memory.writer import ProvenanceError, corroborate, write_lesson
from backend.seed.text_embeddings import lesson_embed_text
from backend.tests.mock_db import MockDatabase

FIXTURES = Path(__file__).resolve().parent.parent / "seed" / "fixtures"
NCR = json.loads((FIXTURES / "ncr_0412_lessons.json").read_text(encoding="utf-8"))


def _measurement(mid: str, gauge: str, value: float = 32.010, verdict: str = "pass") -> dict:
    return {
        "_id": mid,
        "gauge_id": gauge,
        "part_serial": f"SN-{mid}",
        "value_mm": value,
        "nominal_mm": 32.000,
        "tol_lo_mm": 32.000,
        "tol_hi_mm": 32.025,
        "u_mm": 0.002,
        "timestamp": datetime(2026, 9, 14, 9, 0),
        "feature": "Ø32H7 bore",
        "verdict": verdict,
        "current_verdict": verdict,
        "verdict_history": [],
    }


def _seed_measurements(db: MockDatabase, ids=("M1", "M2")) -> None:
    for mid in ids:
        gauge = "BG-07" if mid not in {"M6", "M7", "M8"} else "CMM-02"
        db.measurements.insert_one(_measurement(mid, gauge))


def _lesson_kwargs(**overrides):
    lesson = NCR["lessons"][0]
    kwargs = {
        "type": lesson["kind"],
        "title": lesson["title"],
        "content": lesson["content"],
        "action": lesson["action"],
        "scope": lesson["scope"],
        "measurement_ids": ["M1", "M2"],
        "source": {"ncr_id": "NCR-0412", "author_role": "manufacturing-engineer"},
    }
    kwargs.update(overrides)
    return kwargs


def _failed_attempt_kwargs(**overrides):
    lesson = NCR["lessons"][2]
    kwargs = {
        "type": lesson["kind"],
        "title": lesson["title"],
        "content": lesson["content"],
        "action": lesson["action"],
        "scope": lesson["scope"],
        "measurement_ids": ["M14"],
        "source": {"ncr_id": "NCR-0412", "author_role": "manufacturing-engineer"},
    }
    kwargs.update(overrides)
    return kwargs


def test_write_lesson_refuses_empty_measurement_ids():
    db = MockDatabase()
    with pytest.raises(ProvenanceError):
        write_lesson(db, **_lesson_kwargs(measurement_ids=[]))
    assert db.memories.find({}) == []


def test_write_lesson_refuses_unknown_measurement_id():
    db = MockDatabase()
    _seed_measurements(db)
    with pytest.raises(ProvenanceError) as excinfo:
        write_lesson(db, **_lesson_kwargs(measurement_ids=["M1", "M404"]))
    assert "M404" in str(excinfo.value)
    assert db.memories.find({}) == []


def test_write_lesson_groups_two_instruments_into_two_sets():
    db = MockDatabase()
    _seed_measurements(db, ids=("M1", "M2", "M6", "M7"))

    doc = write_lesson(db, **_lesson_kwargs(measurement_ids=["M1", "M2", "M6", "M7"]))

    assert doc["support_sets"] == [["M1", "M2"], ["M6", "M7"]]
    assert doc["derived_from"] == ["M1", "M2", "M6", "M7"]
    assert doc["validity_state"] == "PROVISIONAL"
    assert doc["type"] == "lesson"
    assert doc["_id"] == "L1"
    assert doc["version"] == 1
    assert doc["mw_success"] == 0 and doc["mw_fail"] == 0
    assert doc["history"][0]["event"] == "created"


def test_write_lesson_sets_30_day_expire_at_and_1024_embedding():
    db = MockDatabase()
    _seed_measurements(db)

    doc = write_lesson(db, **_lesson_kwargs())

    assert isinstance(doc["expire_at"], datetime)
    assert isinstance(doc["created_at"], datetime)
    assert (doc["expire_at"] - doc["created_at"]).days == 30
    assert len(doc["embedding"]) == 1024
    # A document read back from the store is still BSON-date shaped.
    stored = db.memories.find_one({"_id": "L1"})
    assert isinstance(stored["expire_at"], datetime)
    assert len(stored["embedding"]) == 1024


def test_write_lesson_ids_increment_per_prefix():
    db = MockDatabase()
    _seed_measurements(db, ids=("M1", "M2", "M14"))

    first = write_lesson(db, **_lesson_kwargs(measurement_ids=["M1"]))
    second = write_lesson(db, **_failed_attempt_kwargs())
    third = write_lesson(db, **_lesson_kwargs(measurement_ids=["M2"]))

    assert (first["_id"], second["_id"], third["_id"]) == ("L1", "F1", "L2")


def test_write_lesson_embeds_the_documented_text():
    """The fixture vector is keyed by exactly '{title}. {content} Action: {action}'."""
    db = MockDatabase()
    _seed_measurements(db)
    doc = write_lesson(db, **_lesson_kwargs())
    from backend.app.embeddings import get_fixture_embedding

    assert doc["embedding"] == get_fixture_embedding(lesson_embed_text(NCR["lessons"][0]))


def test_corroborate_adds_independent_set_and_promotes():
    db = MockDatabase()
    _seed_measurements(db, ids=("M1", "M2", "M6", "M7"))
    write_lesson(db, **_lesson_kwargs(measurement_ids=["M1", "M2"]))

    updated = corroborate(
        db,
        "L1",
        job_id="NCR-0419",
        measurement_ids=["M6", "M7"],
    )

    assert updated["support_sets"] == [["M1", "M2"], ["M6", "M7"]]
    assert updated["validity_state"] == "ACTIVE"
    assert "expire_at" not in updated
    assert updated["derived_from"] == ["M1", "M2", "M6", "M7"]
    assert updated["version"] == 2
    history = updated["history"][-1]
    assert history["event"] == "corroborated"
    assert "CMM-02" in history["cause"] and "NCR-0419" in history["cause"]
    assert history["note"] == "Two instruments now support this lesson"


def test_corroborate_inserts_provided_measurement_documents():
    db = MockDatabase()
    _seed_measurements(db, ids=("M1",))
    write_lesson(db, **_lesson_kwargs(measurement_ids=["M1"]))

    updated = corroborate(
        db,
        "L1",
        job_id="NCR-0419",
        measurement_ids=["M6", "M7", "M8"],
        measurements=[
            _measurement("M6", "CMM-02", value=32.011),
            _measurement("M7", "CMM-02", value=32.014),
            _measurement("M8", "CMM-02", value=32.009),
        ],
    )

    assert updated["support_sets"] == [["M1"], ["M6", "M7", "M8"]]
    assert updated["validity_state"] == "ACTIVE"
    assert db.measurements.find_one({"_id": "M8"})["current_verdict"] == "pass"


def test_corroborate_same_gauge_joins_existing_set_and_does_not_promote():
    db = MockDatabase()
    _seed_measurements(db, ids=("M1", "M2"))
    db.measurements.insert_one(_measurement("M3", "BG-07"))
    write_lesson(db, **_lesson_kwargs(measurement_ids=["M1", "M2"]))

    updated = corroborate(db, "L1", job_id="NCR-0500", measurement_ids=["M3"])

    assert updated["support_sets"] == [["M1", "M2", "M3"]]
    # The same instrument is not independent evidence.
    assert updated["validity_state"] == "PROVISIONAL"
    assert updated["expire_at"] is not None


def test_corroborate_rejects_unknown_measurement_and_empty_list():
    db = MockDatabase()
    _seed_measurements(db, ids=("M1",))
    write_lesson(db, **_lesson_kwargs(measurement_ids=["M1"]))

    with pytest.raises(ProvenanceError):
        corroborate(db, "L1", job_id="x", measurement_ids=["M999"])
    with pytest.raises(ProvenanceError):
        corroborate(db, "L1", job_id="x", measurement_ids=[])


def test_corroborate_with_independent_holding_set_promotes_historical_only():
    """Corroboration is the only path allowed to promote (PLAN 6.4 / 7.4)."""
    db = MockDatabase()
    _seed_measurements(db, ids=("M1",))
    write_lesson(db, **_lesson_kwargs(measurement_ids=["M1"]))
    # Simulate a cascade flip on the only existing set.
    m1 = db.measurements.find_one({"_id": "M1"})
    m1["current_verdict"] = "fail"
    db.measurements.update_one({"_id": "M1"}, {"$set": {"current_verdict": "fail"}})
    db.memories.update_one({"_id": "L1"}, {"$set": {"validity_state": "HISTORICAL_ONLY"}})

    db.measurements.insert_one(_measurement("M6", "CMM-02"))
    updated = corroborate(db, "L1", job_id="NCR-0501", measurement_ids=["M6"])

    # M6 holds, so Section 7.4 promotes: corroboration is the only path allowed
    # to promote, and the new independent instrument does hold.
    assert updated["validity_state"] == "ACTIVE"
    assert updated["history"][-1]["from_state"] == "HISTORICAL_ONLY"

"""Tests for backend/app/agent/ingest.py (PLAN Section 7.3).

Every test is offline: the forced Claude call is monkeypatched and the
committed NCR-0412 draft is the fallback the demo replays.
"""

import copy

import pytest

from backend.app.agent import ingest
from backend.app.agent.ingest import (
    NCRValidationError,
    ingest_ncr,
    load_fallback_draft,
    validate_draft,
)
from backend.app.agent.llm import LLMUnavailable
from backend.tests.demo_state import ncr_payload, seed_base_data
from backend.tests.mock_db import MockDatabase

ALLOWED = {f"M{i}" for i in range(1, 17)}


def _offline(monkeypatch, calls=None):
    def unavailable(*args, **kwargs):
        if calls is not None:
            calls.append(kwargs.get("attempt"))
        raise LLMUnavailable("no ANTHROPIC_API_KEY in tests")

    monkeypatch.setattr(ingest, "draft_lessons", unavailable)


def test_ingest_writes_l1_l2_f1_provisional_in_fixture_order(monkeypatch):
    calls = []
    stored = []
    _offline(monkeypatch, calls)
    monkeypatch.setattr(ingest, "store_draft_lessons", lambda *a, **k: stored.append(a))

    db = seed_base_data(MockDatabase("test_ingest"))
    response = ingest_ncr(db, ncr_payload())

    assert response["memory_ids"] == ["L1", "L2", "F1"]
    assert response["draft_source"] == "fallback"
    # Two failed attempts (0 and 1) before the committed draft is used.
    assert calls == [0, 1]
    assert len(stored) == 1
    assert response["draft_errors"]

    by_id = {doc["_id"]: doc for doc in response["memories"]}
    assert set(by_id) == {"L1", "L2", "F1"}
    assert by_id["L1"]["validity_state"] == "PROVISIONAL"
    assert by_id["L1"]["support_sets"] == [["M1", "M2", "M3", "M4", "M5"]]
    assert by_id["L2"]["support_sets"] == [["M9", "M10", "M11", "M12", "M13"]]
    assert by_id["F1"]["support_sets"] == [["M14", "M15", "M16"]]
    assert by_id["F1"]["type"] == "failed_attempt"

    stored_l1 = db.memories.find_one({"_id": "L1"})
    assert stored_l1["source"]["ncr_id"] == "NCR-0412"
    assert stored_l1["expire_at"] is not None
    assert len(stored_l1["embedding"]) == 1024
    assert len(stored_l1["history"]) == 1
    assert stored_l1["history"][0]["event"] == "created"

    # Measurements were upserted with a fresh recomputation history.
    for measurement_id in ("M1", "M9", "M14"):
        stored_measurement = db.measurements.find_one({"_id": measurement_id})
        assert stored_measurement["current_verdict"] == stored_measurement["verdict"]
        assert stored_measurement["verdict_history"] == []


def test_ingest_rejects_unknown_llm_citation_then_falls_back(monkeypatch):
    calls = []

    def bad_draft(ncr_input, *, attempt=0, model=None):
        calls.append(attempt)
        return (
            {
                "lessons": [
                    {
                        "kind": "lesson",
                        "title": "Invented",
                        "content": "Cites a measurement that was never sent.",
                        "action": "Do the invented thing",
                        "scope": {"material": "Inconel 718", "process": "finish boring"},
                        "measurement_ids": ["M999"],
                    }
                ]
            },
            "llm",
        )

    monkeypatch.setattr(ingest, "draft_lessons", bad_draft)
    monkeypatch.setattr(ingest, "store_draft_lessons", lambda *a, **k: None)

    db = seed_base_data(MockDatabase("test_ingest"))
    response = ingest_ncr(db, ncr_payload())

    assert calls == [0, 1]
    assert response["draft_source"] == "fallback"
    assert response["memory_ids"] == ["L1", "L2", "F1"]
    assert "M999" not in str(db.memories.find({}))
    assert db.memories.find_one({"title": "Invented"}) is None


def test_ingest_retries_once_then_accepts_the_llm_draft(monkeypatch):
    calls = []
    good = load_fallback_draft("NCR-0412")

    def flaky_draft(ncr_input, *, attempt=0, model=None):
        calls.append(attempt)
        if attempt == 0:
            return ({"lessons": [{"kind": "lesson"}]}, "llm")
        return (copy.deepcopy(good), "llm")

    monkeypatch.setattr(ingest, "draft_lessons", flaky_draft)
    monkeypatch.setattr(ingest, "store_draft_lessons", lambda *a, **k: None)

    db = seed_base_data(MockDatabase("test_ingest"))
    response = ingest_ncr(db, ncr_payload())

    assert calls == [0, 1]
    assert response["draft_source"] == "llm"
    assert response["memory_ids"] == ["L1", "L2", "F1"]


def test_ingest_accepts_a_cached_draft(monkeypatch):
    monkeypatch.setattr(
        ingest,
        "draft_lessons",
        lambda ncr_input, *, attempt=0, model=None: (load_fallback_draft("NCR-0412"), "cache"),
    )

    db = seed_base_data(MockDatabase("test_ingest"))
    response = ingest_ncr(db, ncr_payload())

    assert response["draft_source"] == "cache"
    assert response["draft_errors"] == []


def test_ingest_refuses_an_ncr_without_a_matching_offline_draft(monkeypatch):
    _offline(monkeypatch)

    db = seed_base_data(MockDatabase("test_ingest"))
    payload = ncr_payload(ncr_id="NCR-9999")

    with pytest.raises(NCRValidationError) as excinfo:
        ingest_ncr(db, payload)
    assert "NCR-9999" in str(excinfo.value)


def test_ingest_requires_measurements():
    db = MockDatabase("test_ingest")
    payload = ncr_payload()
    payload["measurements"] = []

    with pytest.raises(NCRValidationError):
        ingest_ncr(db, payload)

    assert db.measurements.find({}) == []


def test_ingest_refuses_an_invalid_measurement_document():
    db = MockDatabase("test_ingest")
    payload = ncr_payload()
    payload["measurements"] = [{"_id": "M1", "gauge_id": "BG-07"}]

    with pytest.raises(NCRValidationError) as excinfo:
        ingest_ncr(db, payload)
    assert "index 0" in str(excinfo.value)


def test_validate_draft_rejects_empty_ids_and_bad_kind():
    lesson = load_fallback_draft("NCR-0412")["lessons"][0]

    missing = dict(lesson, measurement_ids=[])
    clean, error = validate_draft({"lessons": [missing]}, ALLOWED)
    assert clean is None and "measurement_ids" in error

    bad_kind = dict(lesson, kind="episode")
    clean, error = validate_draft({"lessons": [bad_kind]}, ALLOWED)
    assert clean is None and "kind" in error

    clean, error = validate_draft({"lessons": []}, ALLOWED)
    assert clean is None and "non-empty" in error


def test_validate_draft_strips_unknown_scope_fields():
    lesson = dict(load_fallback_draft("NCR-0412")["lessons"][0])
    lesson["scope"] = dict(lesson["scope"], customer="Acme", operator="Dana")

    clean, error = validate_draft({"lessons": [lesson]}, ALLOWED)

    assert error is None
    assert set(clean["lessons"][0]["scope"]) == {
        "material",
        "process",
        "machine",
        "feature_class",
        "tolerance_band",
    }

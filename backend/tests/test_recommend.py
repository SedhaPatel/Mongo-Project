"""Tests for backend/app/agent/recommend.py (PLAN Section 7.7).

The LLM is monkeypatched: these tests prove the code-built plan, the verify
instrument choice, the wording guard and the decision persistence.  No API
server, no MongoDB, no network.
"""

from datetime import datetime, timezone

import pytest

from backend.app.agent import recommend as recommend_module
from backend.app.agent.llm import LLMUnavailable
from backend.app.agent.recommend import (
    build_plan_steps,
    pick_verify_instrument,
    recommend,
    validate_reword,
)
from backend.app.memory.writer import corroborate
from backend.app.validity.cascade import run_cascade
from backend.tests.demo_state import STAGE2_QUERY, STAGE2_SCOPE, build_demo_db
from backend.tests.mock_db import MockDatabase

NOW = datetime(2026, 10, 31, 9, 30, tzinfo=timezone.utc)
CAL_TIME = datetime(2026, 10, 31, 10, 0, tzinfo=timezone.utc)


def _unavailable(*args, **kwargs):
    raise LLMUnavailable("no ANTHROPIC_API_KEY in tests")


def _stage2_db() -> MockDatabase:
    db = build_demo_db()
    corroborate(db, "L1", measurement_ids=["M6", "M7", "M8"], job_id="NCR-0419")
    return db


def _stage3_db() -> MockDatabase:
    db = _stage2_db()
    run_cascade(db, "BG-07", "ev-bg07-test", 0.006, 0.002, event_time=CAL_TIME)
    return db


def _step_ids(steps):
    return [(step["kind"], step["lesson_ids"][0]) for step in steps]


def test_stage2_plan_applies_l1_l2_and_avoids_f1(monkeypatch):
    monkeypatch.setattr(recommend_module, "reword_plan", _unavailable)
    db = _stage2_db()

    response = recommend(
        db, query=STAGE2_QUERY, scope=STAGE2_SCOPE, persist=True, now=NOW
    )

    pairs = _step_ids(response["plan_steps"])
    assert ("apply", "L1") in pairs
    assert ("apply", "L2") in pairs
    assert ("avoid", "F1") in pairs
    assert "L1" in response["lessons_used"]
    assert response["lessons_used"].count("L1") == 1

    l2_step = next(s for s in response["plan_steps"] if s["lesson_ids"] == ["L2"])
    assert l2_step["text"].startswith("Apply: Raise coolant concentration")
    f1_step = next(s for s in response["plan_steps"] if s["lesson_ids"] == ["F1"])
    assert f1_step["text"].startswith("Do not attempt feed reduction")
    assert "Do not: Do not" not in f1_step["text"]
    assert f1_step["text"].endswith("(F1)")

    # Full ranking trace, one row per retrieved memory, every term present.
    assert len(response["ranking_trace"]) == 5
    assert [row["memory_id"] for row in response["ranking_trace"][:3]] == ["L2", "L1", "F1"]
    assert set(response["ranking_trace"][0]) == {
        "memory_id",
        "vector_score",
        "state",
        "state_bias",
        "mw",
        "mw_term",
        "recency",
        "recency_term",
        "scope_match",
        "scope_term",
        "final",
    }

    assert response["decision_id"] == "D3"
    stored = db.decisions.find_one({"_id": "D3"})
    assert stored["lessons_used"] == response["lessons_used"]
    assert stored["ranking_trace"] == response["ranking_trace"]
    assert stored["review_flag"] is False
    for memory_id in ("L1", "L2", "F1"):
        assert "D3" in db.memories.find_one({"_id": memory_id})["used_by"]

    assert response["reword_source"] == "code"
    assert len(response["reword_errors"]) == 2


def test_stage3_verify_step_on_cmm02_and_l1_unchanged(monkeypatch):
    monkeypatch.setattr(recommend_module, "reword_plan", _unavailable)
    db = _stage3_db()

    response = recommend(
        db, query=STAGE2_QUERY, scope=STAGE2_SCOPE, persist=False, now=NOW
    )

    l2_step = next(s for s in response["plan_steps"] if s["lesson_ids"] == ["L2"])
    assert l2_step["kind"] == "verify"
    assert l2_step["verify_instrument"] == "CMM-02"
    assert l2_step["text"].startswith("Verify on CMM-02 before adopting: Raise coolant")

    l1_step = next(s for s in response["plan_steps"] if s["lesson_ids"] == ["L1"])
    assert l1_step["kind"] == "apply"

    f1_step = next(s for s in response["plan_steps"] if s["lesson_ids"] == ["F1"])
    assert f1_step["kind"] == "avoid"

    assert "L2" in response["explanation"]
    assert "NEEDS_VERIFICATION" in response["explanation"]
    assert "CMM-02" in response["explanation"]
    assert response["decision_id"] is None
    assert db.decisions.find_one({"_id": "D3"}) is None


def test_reword_that_changes_step_count_is_rejected(monkeypatch):
    calls = []

    def dropped_step(plan_input, *, attempt=0, model=None):
        calls.append(attempt)
        steps = [dict(step) for step in plan_input["draft_steps"]]
        return ({"steps": steps[:-1], "explanation": "short"}, "llm")

    monkeypatch.setattr(recommend_module, "reword_plan", dropped_step)
    db = _stage2_db()

    response = recommend(
        db, query=STAGE2_QUERY, scope=STAGE2_SCOPE, persist=False, now=NOW
    )

    assert calls == [0, 1]
    assert response["reword_source"] == "code"
    assert len(response["plan_steps"]) == 5
    assert any("step count" in error for error in response["reword_errors"])
    # The code-built wording survived the rejected reword.
    l2_step = next(s for s in response["plan_steps"] if s["lesson_ids"] == ["L2"])
    assert l2_step["text"].startswith("Apply: Raise coolant")


def test_reword_with_same_shape_is_applied(monkeypatch):
    calls = []

    def reword(plan_input, *, attempt=0, model=None):
        calls.append(attempt)
        steps = [
            dict(step, text=f"REWORDED {index}: {step['text']}")
            for index, step in enumerate(plan_input["draft_steps"])
        ]
        return ({"steps": steps, "explanation": "Reworded explanation."}, "llm")

    monkeypatch.setattr(recommend_module, "reword_plan", reword)
    db = _stage3_db()

    response = recommend(
        db, query=STAGE2_QUERY, scope=STAGE2_SCOPE, persist=False, now=NOW
    )

    assert calls == [0]
    assert response["reword_source"] == "llm"
    assert response["explanation"] == "Reworded explanation."
    assert all(step["text"].startswith("REWORDED") for step in response["plan_steps"])
    l2_step = next(s for s in response["plan_steps"] if s["lesson_ids"] == ["L2"])
    # The LLM cannot change the instrument chosen by code.
    assert l2_step["verify_instrument"] == "CMM-02"
    assert l2_step["kind"] == "verify"


def test_reword_retries_once_before_accepting(monkeypatch):
    calls = []

    def flaky(plan_input, *, attempt=0, model=None):
        calls.append(attempt)
        steps = [dict(step) for step in plan_input["draft_steps"]]
        if attempt == 0:
            steps[0]["kind"] = "avoid"
            return ({"steps": steps, "explanation": "x"}, "llm")
        steps[0]["text"] = "Second try wording"
        return ({"steps": steps, "explanation": "second try"}, "llm")

    monkeypatch.setattr(recommend_module, "reword_plan", flaky)
    db = _stage2_db()

    response = recommend(
        db, query=STAGE2_QUERY, scope=STAGE2_SCOPE, persist=False, now=NOW
    )

    assert calls == [0, 1]
    assert response["reword_source"] == "llm"
    assert response["plan_steps"][0]["text"] == "Second try wording"
    assert any("kind changed" in error for error in response["reword_errors"])


def test_pick_verify_instrument_prefers_cmm_then_alphabetical():
    db = _stage3_db()
    l2 = db.memories.find_one({"_id": "L2"})
    assert pick_verify_instrument(db, l2) == "CMM-02"

    db.gauges.update_one({"_id": "CMM-02"}, {"$set": {"cal_status": "OUT_OF_TOLERANCE"}})
    assert pick_verify_instrument(db, l2) == "CMM-05"

    db.gauges.update_one({"_id": "CMM-05"}, {"$set": {"cal_status": "EXPIRED"}})
    assert pick_verify_instrument(db, l2) == "BG-03"


def test_pick_verify_instrument_never_returns_a_weakened_set_gauge():
    db = _stage3_db()
    l2 = db.memories.find_one({"_id": "L2"})

    # BG-07 is in L2's weakened set; only the gauge types chosen by the test
    # remain, so the excluded gauge cannot come back even when first by ID.
    for gauge_id in ("BG-03", "CMM-02", "CMM-05", "HG-04", "MIC-11"):
        db.gauges.update_one({"_id": gauge_id}, {"$set": {"cal_status": "EXPIRED"}})
    db.gauges.update_one({"_id": "BG-07"}, {"$set": {"cal_status": "OK"}})

    assert pick_verify_instrument(db, l2) is None


def test_history_only_lesson_does_not_produce_an_apply_step(monkeypatch):
    monkeypatch.setattr(recommend_module, "reword_plan", _unavailable)
    db = _stage2_db()
    db.memories.update_one({"_id": "L1"}, {"$set": {"validity_state": "HISTORICAL_ONLY"}})

    ranked = [
        {"memory": db.memories.find_one({"_id": "L1"}), "trace": {"memory_id": "L1"}},
    ]
    assert build_plan_steps(db, ranked) == []


def test_validate_reword_rejects_changed_ids():
    steps = [
        {"kind": "apply", "text": "Apply: A", "lesson_ids": ["L1"]},
        {"kind": "avoid", "text": "Do not: B", "lesson_ids": ["F1"]},
    ]

    bad = [
        {"kind": "apply", "text": "Apply: A", "lesson_ids": ["L2"]},
        {"kind": "avoid", "text": "Do not: B", "lesson_ids": ["F1"]},
    ]
    clean, error = validate_reword({"steps": bad, "explanation": ""}, steps)
    assert clean is None and "lesson_ids changed" in error

    clean, error = validate_reword({"steps": steps, "explanation": ""}, steps)
    assert error is None
    assert clean["steps"] == steps

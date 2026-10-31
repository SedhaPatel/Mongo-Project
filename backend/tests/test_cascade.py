"""Unit and integration tests for validity/cascade.py.

Covers Sections 6.5, 9.5 and Section 14 (Milestone 5 acceptance check).
Uses MockDatabase for deterministic, sub-second execution without network dependencies.
"""

from datetime import datetime, timezone
from pathlib import Path
import yaml

from backend.app.validity.cascade import run_cascade
from backend.seed.generate import generate_background_lessons, generate_filler_measurements
from backend.seed.reset import parse_datetime
from backend.tests.mock_db import MockDatabase

SCENARIO_FILE = Path(__file__).resolve().parent.parent / "seed" / "scenario.yaml"


def setup_demo_scenario_db() -> MockDatabase:
    """Prepares an in-memory database with the full demo scenario state."""
    db = MockDatabase("test_metrologic")

    with open(SCENARIO_FILE, "r", encoding="utf-8") as f:
        scenario_data = yaml.safe_load(f)

    # 1. Gauges
    for g in scenario_data.get("gauges", []):
        db.gauges.insert_one(parse_datetime(g))

    # 2. Scenario measurements (M1 to M16, plus M-old)
    for m in scenario_data.get("measurements", []):
        db.measurements.insert_one(parse_datetime(m))

    # 3. Background lessons and filler measurements
    b_lessons, _ = generate_background_lessons(13)
    for b in b_lessons:
        db.memories.insert_one(parse_datetime(b))

    filler = generate_filler_measurements(b_lessons)
    for fm in filler:
        # Don't duplicate M-old if already in scenario measurements
        if fm["_id"] != "M-old":
            db.measurements.insert_one(parse_datetime(fm))

    # 4. Demo memories (L1, L2, F1)
    for mem in scenario_data.get("memories", []):
        db.memories.insert_one(parse_datetime(mem))

    # 5. Decisions D1 and D2
    for dec in scenario_data.get("decisions", []):
        db.decisions.insert_one(parse_datetime(dec))

    return db


def test_cascade_suspect_window_m_old_untouched():
    """Proves Section 6.1: M-old dated before last_good_cal is untouched by cascade."""
    db = setup_demo_scenario_db()

    m_old_before = db.measurements.find_one({"_id": "M-old"})
    assert m_old_before["verdict"] == "pass"
    assert m_old_before["current_verdict"] == "pass"
    assert len(m_old_before.get("verdict_history", [])) == 0

    event_id = "ev-bg07-test-suspect"
    event_time = datetime(2026, 10, 31, 9, 30, 0, tzinfo=timezone.utc)

    # Run cascade on BG-07: reads high by 0.006, U=0.002
    summary = run_cascade(
        db=db,
        gauge_id="BG-07",
        event_id=event_id,
        e=0.006,
        U=0.002,
        event_time=event_time,
    )

    m_old_after = db.measurements.find_one({"_id": "M-old"})
    # M-old must be untouched because timestamp is 2026-07-20 < last_good_cal 2026-08-01
    assert m_old_after["current_verdict"] == "pass"
    assert len(m_old_after.get("verdict_history", [])) == 0


def test_cascade_expected_outcome_table_9_5():
    """Proves Section 9.5 expected outcome table:

    - L1 stays ACTIVE with history note 'saved by independent support on CMM-02'
    - L2 demoted from PROVISIONAL to NEEDS_VERIFICATION
    - F1 remains PROVISIONAL
    - B1 to B13 remain ACTIVE
    - Measurements recomputed per worked example
    - Decisions D1 and D2 flagged with part serials and reason
    """
    db = setup_demo_scenario_db()

    event_id = "ev-bg07-001"
    event_time = datetime(2026, 10, 31, 9, 30, 0, tzinfo=timezone.utc)

    summary = run_cascade(
        db=db,
        gauge_id="BG-07",
        event_id=event_id,
        e=0.006,
        U=0.002,
        event_time=event_time,
    )

    # 1. Assert measurements current_verdicts
    assert db.measurements.find_one({"_id": "M1"})["current_verdict"] == "pass"
    assert db.measurements.find_one({"_id": "M2"})["current_verdict"] == "indeterminate"
    assert db.measurements.find_one({"_id": "M3"})["current_verdict"] == "fail"  # flipped!
    assert db.measurements.find_one({"_id": "M4"})["current_verdict"] == "pass"
    assert db.measurements.find_one({"_id": "M5"})["current_verdict"] == "pass"
    assert db.measurements.find_one({"_id": "M9"})["current_verdict"] == "pass"
    assert db.measurements.find_one({"_id": "M10"})["current_verdict"] == "indeterminate"
    assert db.measurements.find_one({"_id": "M11"})["current_verdict"] == "pass"
    assert db.measurements.find_one({"_id": "M12"})["current_verdict"] == "indeterminate"
    assert db.measurements.find_one({"_id": "M13"})["current_verdict"] == "pass"
    assert db.measurements.find_one({"_id": "M14"})["current_verdict"] == "fail"
    assert db.measurements.find_one({"_id": "M15"})["current_verdict"] == "fail"
    assert db.measurements.find_one({"_id": "M16"})["current_verdict"] == "fail"
    assert db.measurements.find_one({"_id": "M-old"})["current_verdict"] == "pass"

    # 2. Assert Lesson L1: stays ACTIVE due to CMM-02 support
    l1 = db.memories.find_one({"_id": "L1"})
    assert l1["validity_state"] == "ACTIVE"
    # History contains note that independent support on CMM-02 saved it
    save_notes = [h.get("note", "") for h in l1.get("history", [])]
    assert any("saved by independent support on CMM-02" in note for note in save_notes)

    # 3. Assert Lesson L2: demoted to NEEDS_VERIFICATION
    l2 = db.memories.find_one({"_id": "L2"})
    assert l2["validity_state"] == "NEEDS_VERIFICATION"

    # 4. Assert Failed Attempt F1: remains PROVISIONAL
    f1 = db.memories.find_one({"_id": "F1"})
    assert f1["validity_state"] == "PROVISIONAL"

    # 5. Assert Background lessons B1..B13 are untouched (still ACTIVE)
    for b_idx in range(1, 14):
        b_doc = db.memories.find_one({"_id": f"B{b_idx}"})
        assert b_doc["validity_state"] == "ACTIVE"

    # 6. Assert Decisions D1 and D2 are flagged
    d1 = db.decisions.find_one({"_id": "D1"})
    assert d1["review_flag"] is True
    assert "Used L2, now NEEDS_VERIFICATION" in d1["review_reason"]
    assert "SN-2208" in d1["part_serials"]

    d2 = db.decisions.find_one({"_id": "D2"})
    assert d2["review_flag"] is True
    assert "Used L2, now NEEDS_VERIFICATION" in d2["review_reason"]
    assert "SN-2211" in d2["part_serials"]


def test_cascade_strict_idempotency():
    """Proves Section 6.5: Calling run_cascade twice changes nothing the second time."""
    db = setup_demo_scenario_db()

    event_id = "ev-bg07-idempotent-001"
    event_time = datetime(2026, 10, 31, 9, 30, 0, tzinfo=timezone.utc)

    # First run
    res1 = run_cascade(db, "BG-07", event_id, 0.006, 0.002, event_time)
    audit_count_1 = len(db.audit_log.find())
    l2_hist_count_1 = len(db.memories.find_one({"_id": "L2"}).get("history", []))
    m3_hist_count_1 = len(db.measurements.find_one({"_id": "M3"}).get("verdict_history", []))

    # Second run with identical parameters
    res2 = run_cascade(db, "BG-07", event_id, 0.006, 0.002, event_time)
    audit_count_2 = len(db.audit_log.find())
    l2_hist_count_2 = len(db.memories.find_one({"_id": "L2"}).get("history", []))
    m3_hist_count_2 = len(db.measurements.find_one({"_id": "M3"}).get("verdict_history", []))

    # Assert results are identical
    assert res1 == res2
    # Zero new audit log rows
    assert audit_count_1 == audit_count_2
    # Zero new memory history entries
    assert l2_hist_count_1 == l2_hist_count_2
    # Zero new verdict history entries
    assert m3_hist_count_1 == m3_hist_count_2

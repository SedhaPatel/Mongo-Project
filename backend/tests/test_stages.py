"""Tests for the complete demo stage progression (Stages 1a, 1b, 2, 3-arm, 3).

Covers Section 10 and Gate 1, Gate 2, Gate 3 transitions.
"""

from backend.seed.stages import (
    run_stage_1a,
    run_stage_1b,
    run_stage_2,
    run_stage_3_arm,
    run_stage_3,
)
from backend.tests.test_cascade import setup_demo_scenario_db


def test_full_demo_stage_lifecycle():
    """Runs through reset -> Stage 1a -> Stage 1b -> Stage 2 -> Stage 3-arm -> Stage 3."""
    db = setup_demo_scenario_db()

    # 1. Stage 1a
    res_1a = run_stage_1a(db)
    assert res_1a["status"] == "success"
    l1 = db.memories.find_one({"_id": "L1"})
    l2 = db.memories.find_one({"_id": "L2"})
    f1 = db.memories.find_one({"_id": "F1"})
    assert l1["validity_state"] == "PROVISIONAL"
    assert l2["validity_state"] == "PROVISIONAL"
    assert f1["validity_state"] == "PROVISIONAL"

    # 2. Stage 1b (Corroboration of L1 on CMM-02)
    res_1b = run_stage_1b(db)
    assert res_1b["status"] == "success"
    l1_corr = db.memories.find_one({"_id": "L1"})
    assert l1_corr["validity_state"] == "ACTIVE"
    assert len(l1_corr["support_sets"]) == 2  # BG-07 and CMM-02

    # 3. Stage 2 (Query and plan decision)
    res_2 = run_stage_2(db)
    assert res_2["status"] == "success"
    d_st2 = db.decisions.find_one({"_id": "D-STAGE2"})
    assert d_st2 is not None
    assert d_st2["review_flag"] is False

    # 4. Stage 3 Arm (TTL demo helper)
    res_3_arm = run_stage_3_arm(db)
    assert res_3_arm["status"] == "success"
    t1 = db.memories.find_one({"_id": "T1"})
    assert t1 is not None
    assert t1["validity_state"] == "PROVISIONAL"
    assert t1["expire_at"] is not None

    # 5. Stage 3 (BG-07 +6 µm calibration event & cascade)
    res_3 = run_stage_3(db)
    assert res_3["status"] == "success"

    # L1 must stay ACTIVE (saved by CMM-02)
    l1_final = db.memories.find_one({"_id": "L1"})
    assert l1_final["validity_state"] == "ACTIVE"
    save_notes = [h.get("note", "") for h in l1_final.get("history", [])]
    assert any("saved by independent support on CMM-02" in n for n in save_notes)

    # L2 must be demoted to NEEDS_VERIFICATION
    l2_final = db.memories.find_one({"_id": "L2"})
    assert l2_final["validity_state"] == "NEEDS_VERIFICATION"

    # F1 remains PROVISIONAL
    f1_final = db.memories.find_one({"_id": "F1"})
    assert f1_final["validity_state"] == "PROVISIONAL"

    # Decisions D1, D2, and D-STAGE2 must be flagged
    assert db.decisions.find_one({"_id": "D1"})["review_flag"] is True
    assert db.decisions.find_one({"_id": "D2"})["review_flag"] is True
    assert db.decisions.find_one({"_id": "D-STAGE2"})["review_flag"] is True


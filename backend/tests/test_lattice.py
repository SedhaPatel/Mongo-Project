"""Unit tests for validity/lattice.py.

Covers Sections 6.3, 6.4 and Section 14 (M2 acceptance check).
Pure deterministic Python - does not require a database connection.
"""

from backend.app.validity.lattice import (
    evaluate_measurement_member,
    evaluate_memory_member,
    evaluate_support_set,
    lesson_state,
    evaluate_lesson_from_measurements,
)
from backend.app.models import ValidityState


def test_measurement_member_evaluation():
    # pass -> pass (unchanged)
    assert evaluate_measurement_member("pass", "pass") == "unchanged"
    # pass -> indeterminate (weakened)
    assert evaluate_measurement_member("pass", "indeterminate") == "weakened"
    # pass -> fail (flipped)
    assert evaluate_measurement_member("pass", "fail") == "flipped"
    # fail -> pass (flipped)
    assert evaluate_measurement_member("fail", "pass") == "flipped"
    # fail -> fail (unchanged)
    assert evaluate_measurement_member("fail", "fail") == "unchanged"
    # indeterminate -> indeterminate (unchanged)
    assert evaluate_measurement_member("indeterminate", "indeterminate") == "unchanged"


def test_memory_member_evaluation():
    assert evaluate_memory_member("ACTIVE") == "unchanged"
    assert evaluate_memory_member("PROVISIONAL") == "unchanged"
    assert evaluate_memory_member("NEEDS_VERIFICATION") == "weakened"
    assert evaluate_memory_member("HISTORICAL_ONLY") == "flipped"
    assert evaluate_memory_member("SUPERSEDED") == "flipped"


def test_support_set_status():
    # All unchanged -> holds
    assert evaluate_support_set(["unchanged", "unchanged"]) == "holds"
    # One weakened, none flipped -> weakened
    assert evaluate_support_set(["unchanged", "weakened", "unchanged"]) == "weakened"
    # One flipped, even with weakened -> broken
    assert evaluate_support_set(["unchanged", "weakened", "flipped"]) == "broken"
    # Empty set -> holds
    assert evaluate_support_set([]) == "holds"


def test_lesson_state_transitions():
    # 1. ACTIVE lesson, one set broken, another holds -> stays ACTIVE
    assert lesson_state("ACTIVE", ["broken", "holds"]) == "ACTIVE"

    # 2. PROVISIONAL lesson, only set weakened -> becomes NEEDS_VERIFICATION
    assert lesson_state("PROVISIONAL", ["weakened"]) == "NEEDS_VERIFICATION"

    # 3. PROVISIONAL lesson, all sets hold -> stays PROVISIONAL (never promotes)
    assert lesson_state("PROVISIONAL", ["holds"]) == "PROVISIONAL"

    # 4. NEEDS_VERIFICATION lesson hit by event where all sets hold -> stays NEEDS_VERIFICATION
    assert lesson_state("NEEDS_VERIFICATION", ["holds"]) == "NEEDS_VERIFICATION"

    # 5. All sets broken -> HISTORICAL_ONLY
    assert lesson_state("ACTIVE", ["broken", "broken"]) == "HISTORICAL_ONLY"
    assert lesson_state("PROVISIONAL", ["broken"]) == "HISTORICAL_ONLY"

    # 6. HISTORICAL_ONLY never promotes back to ACTIVE or NEEDS_VERIFICATION
    assert lesson_state("HISTORICAL_ONLY", ["holds"]) == "HISTORICAL_ONLY"
    assert lesson_state("HISTORICAL_ONLY", ["weakened"]) == "HISTORICAL_ONLY"


def test_l1_saved_by_cmm02_scenario():
    """Scenario for L1 (corroborated on BG-07 and CMM-02).

    Set 1 (BG-07): M1(pass), M2(indeterminate), M3(fail), M4(pass), M5(pass) -> broken.
    Set 2 (CMM-02): M6(pass), M7(pass), M8(pass) -> holds.
    Expected: L1 stays ACTIVE, saved_by_independent_support=True.
    """
    measurements = {
        "M1": {"verdict": "pass", "current_verdict": "pass"},
        "M2": {"verdict": "pass", "current_verdict": "indeterminate"},
        "M3": {"verdict": "pass", "current_verdict": "fail"},
        "M4": {"verdict": "pass", "current_verdict": "pass"},
        "M5": {"verdict": "pass", "current_verdict": "pass"},
        "M6": {"verdict": "pass", "current_verdict": "pass"},
        "M7": {"verdict": "pass", "current_verdict": "pass"},
        "M8": {"verdict": "pass", "current_verdict": "pass"},
    }
    support_sets = [["M1", "M2", "M3", "M4", "M5"], ["M6", "M7", "M8"]]

    res = evaluate_lesson_from_measurements(
        old_state="ACTIVE",
        support_sets=support_sets,
        measurements_map=measurements,
    )
    assert res["computed_state"] == "ACTIVE"
    assert res["set_statuses"] == ["broken", "holds"]
    assert res["state_changed"] is False
    assert res["saved_by_independent_support"] is True
    assert res["surviving_set_index"] == 1


def test_l2_demotion_scenario():
    """Scenario for L2 (only BG-07):

    M9(pass), M10(indeterminate), M11(pass), M12(indeterminate), M13(pass).
    No flips, but two weakened -> weakened set -> demotes to NEEDS_VERIFICATION.
    """
    measurements = {
        "M9": {"verdict": "pass", "current_verdict": "pass"},
        "M10": {"verdict": "pass", "current_verdict": "indeterminate"},
        "M11": {"verdict": "pass", "current_verdict": "pass"},
        "M12": {"verdict": "pass", "current_verdict": "indeterminate"},
        "M13": {"verdict": "pass", "current_verdict": "pass"},
    }
    support_sets = [["M9", "M10", "M11", "M12", "M13"]]

    res = evaluate_lesson_from_measurements(
        old_state="PROVISIONAL",
        support_sets=support_sets,
        measurements_map=measurements,
    )
    assert res["computed_state"] == "NEEDS_VERIFICATION"
    assert res["set_statuses"] == ["weakened"]
    assert res["state_changed"] is True
    assert res["saved_by_independent_support"] is False


def test_transitive_demotion_scenario():
    """Scenario for synthetic L3 built on L2.

    L2 is demoted to NEEDS_VERIFICATION.
    L3 has support_set containing ["L2"].
    L3 should resolve to NEEDS_VERIFICATION.
    """
    memories = {
        "L2": {"validity_state": "NEEDS_VERIFICATION"},
    }
    support_sets = [["L2"]]

    res = evaluate_lesson_from_measurements(
        old_state="ACTIVE",
        support_sets=support_sets,
        measurements_map={},
        memories_map=memories,
    )
    assert res["computed_state"] == "NEEDS_VERIFICATION"
    assert res["set_statuses"] == ["weakened"]
    assert res["state_changed"] is True


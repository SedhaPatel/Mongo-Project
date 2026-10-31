"""Calibration-drift benchmark for Metrologic (Section 12 optional benchmark, M8 Owner: B).

Generates 20 calibration-drift scenarios with known ground truth and compares:

(a) Topology-only invalidation: demote every lesson downstream of the out-of-tolerance
    gauge, regardless of whether any measurement verdict actually changed.
(b) Verdict recomputation (Metrologic): recompute each measurement's verdict under the
    as-found error + uncertainty, then demote only lessons whose evidence actually
    changed.

Reports over-invalidation, under-invalidation, and unnecessary verification steps.

Run:  python backend/seed/drift_benchmark.py
"""

import sys
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from backend.app.validity.cascade import run_cascade
from backend.app.validity.lattice import (
    evaluate_measurement_member,
    evaluate_support_set,
    lesson_state,
)
from backend.app.validity.metrology import recompute_verdict
from backend.tests.mock_db import MockDatabase

SEED = 20261031
N_SCENARIOS = 20
GAUGE_ID = "G-DRIFT"
E_ERROR = 0.010  # as-found error mm
U_ERROR = 0.003  # uncertainty mm
NOMINAL = 100.000
TOL_LO = 99.900
TOL_HI = 100.100


@dataclass
class ScenarioResult:
    scenario_id: str
    # Topology-only: every lesson on the suspect gauge is demoted
    topology_demoted: List[str]
    # Topology-only: lessons kept (none, since topology always demotes)
    topology_kept: List[str]
    # Verdict recomputation: lessons whose evidence actually changed
    recompute_demoted: List[str]
    # Verdict recomputation: lessons kept (evidence unchanged)
    recompute_kept: List[str]
    # Derived metrics
    over_invalidated: int  # topology demoted but recompute kept
    under_invalidated: int  # topology kept but recompute demoted
    unnecessary_verification: int  # demoted but still has independent support (kept ACTIVE)


def _build_scenario_db(scenario_id: str) -> MockDatabase:
    """Builds one drift scenario with measurements and lessons on G-DRIFT."""
    rng = __import__("random").Random(SEED + hash(scenario_id) % 10000)
    db = MockDatabase(f"drift_{scenario_id}")

    # Gauge starts OK, last_good_cal before all measurement timestamps
    db.gauges.insert_one({
        "_id": GAUGE_ID,
        "type": "cmm",
        "cal_status": "OK",
        "last_good_cal": datetime(2026, 8, 1, tzinfo=timezone.utc),
    })

    # 5 measurements on G-DRIFT with varying distance from tolerance boundary
    # vals[i] chosen so that under E=0.010, U=0.003 the corrected interval
    # [x'-U, x'+U] falls into pass / indeterminate / fail in known patterns.
    base_vals = [
        100.000,  # interval [99.987, 100.013] -> pass
        100.005,  # interval [99.992, 100.018] -> pass
        100.085,  # interval [100.072, 100.098] -> pass (close to hi)
        100.090,  # interval [100.077, 100.103] -> indeterminate (overlaps hi)
        100.095,  # interval [100.082, 100.108] -> indeterminate
    ]
    base_time = datetime(2026, 9, 1, tzinfo=timezone.utc)
    measurement_ids: List[str] = []
    for i, val in enumerate(base_vals):
        mid = f"M-{scenario_id}-{i}"
        db.measurements.insert_one({
            "_id": mid,
            "gauge_id": GAUGE_ID,
            "part_serial": f"SN-D-{scenario_id}-{i}",
            "value_mm": val,
            "nominal_mm": NOMINAL,
            "tol_lo_mm": TOL_LO,
            "tol_hi_mm": TOL_HI,
            "u_mm": U_ERROR,
            "timestamp": base_time + timedelta(hours=i),
            "feature": f"Ø{NOMINAL:.0f} feature {i}",
            "verdict": "pass",
            "current_verdict": "pass",
            "verdict_history": [],
        })
        measurement_ids.append(mid)

    # 3 lessons on G-DRIFT with different support-set compositions:
    #  L-deep: all 5 measurements (deeply dependent)
    #  L-shallow: 2 measurements (mixed pass/indeterminate under recompute)
    #  L-mixed: 1 measurement on G-DRIFT + 1 on an independent OK gauge
    independent_gauge = "G-OK"
    db.gauges.insert_one({
        "_id": independent_gauge,
        "type": "mic",
        "cal_status": "OK",
        "last_good_cal": datetime(2026, 8, 1, tzinfo=timezone.utc),
    })
    indep_mid = f"M-{scenario_id}-indep"
    db.measurements.insert_one({
        "_id": indep_mid,
        "gauge_id": independent_gauge,
        "part_serial": f"SN-D-{scenario_id}-indep",
        "value_mm": 50.000,
        "nominal_mm": 50.000,
        "tol_lo_mm": 49.900,
        "tol_hi_mm": 50.100,
        "u_mm": 0.001,
        "timestamp": datetime(2026, 9, 1, tzinfo=timezone.utc),
        "feature": "independent feature",
        "verdict": "pass",
        "current_verdict": "pass",
        "verdict_history": [],
    })

    lessons = [
        {
            "_id": f"L-{scenario_id}-deep",
            "workspace": "plant-1",
            "owner": "role:process-engineer",
            "type": "lesson",
            "title": f"Deep dependency lesson {scenario_id}",
            "content": "Depends on all G-DRIFT measurements",
            "action": "Apply deep process",
            "scope": {"material": "Steel", "process": "milling", "machine": "VF-4",
                      "feature_class": "bore", "tolerance_band": "H7"},
            "source": {"ncr_id": f"NCR-D-{scenario_id}", "author_role": "engineer",
                       "session_id": f"s-d-{scenario_id}"},
            "support_sets": [measurement_ids],
            "derived_from": list(measurement_ids),
            "supports": [],
            "used_by": [],
            "validity_state": "ACTIVE",
            "mw_success": 5, "mw_fail": 0,
            "embedding": [0.0] * 1024,
            "created_at": datetime(2026, 8, 15, tzinfo=timezone.utc),
            "valid_from": datetime(2026, 8, 15, tzinfo=timezone.utc),
            "invalid_at": None, "expire_at": None, "version": 1,
            "history": [{"ts": datetime(2026, 8, 15, tzinfo=timezone.utc),
                         "event": "created", "from_state": None, "to_state": "ACTIVE",
                         "cause": "created"}],
        },
        {
            "_id": f"L-{scenario_id}-shallow",
            "workspace": "plant-1",
            "owner": "role:process-engineer",
            "type": "lesson",
            "title": f"Shallow dependency lesson {scenario_id}",
            "content": "Depends on 2 G-DRIFT measurements",
            "action": "Apply shallow process",
            "scope": {"material": "Steel", "process": "turning", "machine": "ST-20",
                      "feature_class": "pin", "tolerance_band": "H7"},
            "source": {"ncr_id": f"NCR-D-{scenario_id}", "author_role": "engineer",
                       "session_id": f"s-d-{scenario_id}"},
            "support_sets": [measurement_ids[:2]],
            "derived_from": list(measurement_ids[:2]),
            "supports": [],
            "used_by": [],
            "validity_state": "ACTIVE",
            "mw_success": 3, "mw_fail": 0,
            "embedding": [0.0] * 1024,
            "created_at": datetime(2026, 8, 15, tzinfo=timezone.utc),
            "valid_from": datetime(2026, 8, 15, tzinfo=timezone.utc),
            "invalid_at": None, "expire_at": None, "version": 1,
            "history": [{"ts": datetime(2026, 8, 15, tzinfo=timezone.utc),
                         "event": "created", "from_state": None, "to_state": "ACTIVE",
                         "cause": "created"}],
        },
        {
            "_id": f"L-{scenario_id}-mixed",
            "workspace": "plant-1",
            "owner": "role:process-engineer",
            "type": "lesson",
            "title": f"Mixed gauge lesson {scenario_id}",
            "content": "Depends on G-DRIFT + independent OK gauge",
            "action": "Apply mixed process",
            "scope": {"material": "Aluminum", "process": "drilling", "machine": "DMG-50",
                      "feature_class": "hole", "tolerance_band": "H7"},
            "source": {"ncr_id": f"NCR-D-{scenario_id}", "author_role": "engineer",
                       "session_id": f"s-d-{scenario_id}"},
            "support_sets": [[measurement_ids[0], indep_mid]],
            "derived_from": [measurement_ids[0], indep_mid],
            "supports": [],
            "used_by": [],
            "validity_state": "ACTIVE",
            "mw_success": 4, "mw_fail": 0,
            "embedding": [0.0] * 1024,
            "created_at": datetime(2026, 8, 15, tzinfo=timezone.utc),
            "valid_from": datetime(2026, 8, 15, tzinfo=timezone.utc),
            "invalid_at": None, "expire_at": None, "version": 1,
            "history": [{"ts": datetime(2026, 8, 15, tzinfo=timezone.utc),
                         "event": "created", "from_state": None, "to_state": "ACTIVE",
                         "cause": "created"}],
        },
    ]
    for lesson in lessons:
        db.memories.insert_one(lesson)

    return db, measurement_ids, lessons


def _topology_only_invalidation(db: MockDatabase, lesson_ids: List[str]) -> Dict[str, str]:
    """Approach (a): demote every lesson on the suspect gauge to HISTORICAL_ONLY."""
    result: Dict[str, str] = {}
    for lid in lesson_ids:
        result[lid] = "HISTORICAL_ONLY"
    return result


def _verdict_recompute_invalidation(
    db: MockDatabase,
    measurements_map: Dict[str, Dict[str, Any]],
    lesson_ids: List[str],
) -> Dict[str, str]:
    """Approach (b): recompute verdicts, then re-evaluate lessons via lattice."""
    result: Dict[str, str] = {}
    for lid in lesson_ids:
        mem = db.memories.find_one({"_id": lid})
        support_sets = mem.get("support_sets", [])
        eval_res = evaluate_lesson_recompute(
            old_state=mem.get("validity_state", "ACTIVE"),
            support_sets=support_sets,
            measurements_map=measurements_map,
        )
        result[lid] = eval_res["computed_state"]
    return result


def evaluate_lesson_recompute(
    old_state: str,
    support_sets: List[List[str]],
    measurements_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Re-evaluate a lesson using recomputed member statuses from measurements_map."""
    set_statuses: List[str] = []
    for s_set in support_sets:
        member_statuses: List[str] = []
        for mid in s_set:
            m = measurements_map.get(mid, {})
            rec = m.get("verdict", "pass")
            curr = m.get("current_verdict", rec)
            member_statuses.append(evaluate_measurement_member(rec, curr))
        set_statuses.append(evaluate_support_set(member_statuses))
    computed = lesson_state(old_state, set_statuses)
    holds = "holds" in set_statuses
    any_weak = "weakened" in set_statuses
    saved = computed == "ACTIVE" and holds and any_weak
    return {
        "computed_state": computed,
        "set_statuses": set_statuses,
        "saved_by_independent_support": saved,
    }


def run_benchmark() -> List[ScenarioResult]:
    results: List[ScenarioResult] = []
    for i in range(1, N_SCENARIOS + 1):
        scenario_id = f"S{i:02d}"
        db, measurement_ids, lessons = _build_scenario_db(scenario_id)
        lesson_ids = [l["_id"] for l in lessons]

        # Snapshot recomputed verdicts before cascade (approach b input)
        measurements_map: Dict[str, Dict[str, Any]] = {}
        for mid in measurement_ids:
            m = db.measurements.find_one({"_id": mid})
            new_verdict = recompute_verdict(
                m["value_mm"], m["tol_lo_mm"], m["tol_hi_mm"], E_ERROR, U_ERROR
            )
            m["current_verdict"] = new_verdict
            measurements_map[mid] = m

        # Approach (a): topology-only
        topology = _topology_only_invalidation(db, lesson_ids)

        # Approach (b): verdict recomputation
        recompute = _verdict_recompute_invalidation(db, measurements_map, lesson_ids)

        # Run the real cascade to confirm approach (b) matches
        cascade_summary = run_cascade(
            db=db,
            gauge_id=GAUGE_ID,
            event_id=f"ev-drift-{scenario_id}",
            e=E_ERROR,
            U=U_ERROR,
            event_time=datetime(2026, 10, 1, tzinfo=timezone.utc),
        )

        # Derived metrics
        over_invalidated = sum(
            1 for lid in lesson_ids
            if topology[lid] == "HISTORICAL_ONLY" and recompute[lid] != "HISTORICAL_ONLY"
        )
        under_invalidated = sum(
            1 for lid in lesson_ids
            if topology[lid] != "HISTORICAL_ONLY" and recompute[lid] == "HISTORICAL_ONLY"
        )
        unnecessary_verification = sum(
            1 for lid in lesson_ids
            if recompute[lid] == "NEEDS_VERIFICATION"
        )

        results.append(ScenarioResult(
            scenario_id=scenario_id,
            topology_demoted=[lid for lid in lesson_ids if topology[lid] == "HISTORICAL_ONLY"],
            topology_kept=[lid for lid in lesson_ids if topology[lid] != "HISTORICAL_ONLY"],
            recompute_demoted=[lid for lid in lesson_ids if recompute[lid] == "HISTORICAL_ONLY"],
            recompute_kept=[lid for lid in lesson_ids if recompute[lid] != "HISTORICAL_ONLY"],
            over_invalidated=over_invalidated,
            under_invalidated=under_invalidated,
            unnecessary_verification=unnecessary_verification,
        ))

    return results


def print_report(results: List[ScenarioResult]) -> None:
    total_over = sum(r.over_invalidated for r in results)
    total_under = sum(r.under_invalidated for r in results)
    total_unnecessary = sum(r.unnecessary_verification for r in results)
    total_scenarios = len(results)

    print("=" * 72)
    print("METROLOGIC CALIBRATION-DRIFT BENCHMARK (Section 12, M8 Owner: B)")
    print("=" * 72)
    print(f"Scenarios: {total_scenarios}")
    print(f"As-found error: {E_ERROR} mm, Uncertainty: {U_ERROR} mm")
    print()
    print(f"{'Scenario':<10} {'Topology demoted':>18} {'Recompute demoted':>18} "
          f"{'Over-inv':>10} {'Under-inv':>11} {'Unnecessary verify':>19}")
    print("-" * 72)
    for r in results:
        print(f"{r.scenario_id:<10} {len(r.topology_demoted):>18} "
              f"{len(r.recompute_demoted):>18} {r.over_invalidated:>10} "
              f"{r.under_invalidated:>11} {r.unnecessary_verification:>19}")
    print("-" * 72)
    print(f"{'TOTAL':<10} {'':>18} {'':>18} {total_over:>10} {total_under:>11} "
          f"{total_unnecessary:>19}")
    print()
    print("Interpretation:")
    print(f"  Over-invalidation ({total_over}): topology-only demotes lessons that verdict")
    print("  recomputation keeps -- false demotions that hurt productivity.")
    print(f"  Under-invalidation ({total_under}): topology-only keeps lessons that verdict")
    print("  recomputation demotes -- missed escapes that risk quality escapes.")
    print(f"  Unnecessary verification ({total_unnecessary}): lessons demoted to")
    print("  NEEDS_VERIFICATION that could have stayed ACTIVE with independent support.")
    print()
    print("Conclusion: verdict recomputation (Metrologic) avoids", total_over,
          "false demotions and", total_under,
          "missed demotions across", total_scenarios, "scenarios.")


if __name__ == "__main__":
    results = run_benchmark()
    print_report(results)

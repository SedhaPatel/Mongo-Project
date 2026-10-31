"""Support-set lattice and validity state resolution for Metrologic.

Implements Sections 6.3 and 6.4 of docs/PLAN.md:
Evaluates evidence across independent instruments to determine if a lesson
holds, is weakened, or is broken under metrological calibration events.
"""

from typing import Any, Dict, List, Optional, Union
from backend.app.models import ValidityState, Verdict

SEVERITY: Dict[str, int] = {
    ValidityState.ACTIVE.value: 0,
    ValidityState.PROVISIONAL.value: 1,
    ValidityState.NEEDS_VERIFICATION.value: 2,
    ValidityState.HISTORICAL_ONLY.value: 3,
    ValidityState.SUPERSEDED.value: 4,
}


def evaluate_measurement_member(recorded_verdict: str, current_verdict: str) -> str:
    """Evaluates whether an individual measurement member is flipped, weakened, or unchanged.

    - flipped: recorded != current and both in {pass, fail}
    - weakened: current is indeterminate and recorded was not indeterminate
    - unchanged: otherwise
    """
    rec = recorded_verdict.lower()
    curr = current_verdict.lower()

    if rec != curr and rec in {"pass", "fail"} and curr in {"pass", "fail"}:
        return "flipped"

    if curr == "indeterminate" and rec != "indeterminate":
        return "weakened"

    return "unchanged"


def evaluate_memory_member(validity_state: Union[ValidityState, str]) -> str:
    """Evaluates a memory member (for transitive dependency chains).

    - unchanged: ACTIVE or PROVISIONAL
    - weakened: NEEDS_VERIFICATION
    - flipped: HISTORICAL_ONLY or SUPERSEDED
    """
    st = validity_state.value if isinstance(validity_state, ValidityState) else str(validity_state)
    if st in {ValidityState.ACTIVE.value, ValidityState.PROVISIONAL.value}:
        return "unchanged"
    if st == ValidityState.NEEDS_VERIFICATION.value:
        return "weakened"
    if st in {ValidityState.HISTORICAL_ONLY.value, ValidityState.SUPERSEDED.value}:
        return "flipped"
    return "unchanged"


def evaluate_support_set(member_statuses: List[str]) -> str:
    """Evaluates the status of a single support set from its member statuses.

    - broken: if ANY member is flipped
    - weakened: if no member is flipped and ANY member is weakened
    - holds: otherwise (all members unchanged)
    """
    if not member_statuses:
        return "holds"

    if any(s == "flipped" for s in member_statuses):
        return "broken"
    if any(s == "weakened" for s in member_statuses):
        return "weakened"
    return "holds"


def lesson_state(old_state: Union[ValidityState, str], set_statuses: List[str]) -> str:
    """Resolves lesson validity state across independent support sets.

    Resolution rule (best set wins):
      - If ANY set holds -> ACTIVE
      - Else if ANY set weakened -> NEEDS_VERIFICATION
      - Else (all broken) -> HISTORICAL_ONLY

    Monotonic severity constraint:
      - A cascade never promotes: keep max(old_state, computed, key=SEVERITY.get)
    """
    old_st = old_state.value if isinstance(old_state, ValidityState) else str(old_state)
    if not set_statuses:
        return old_st

    if "holds" in set_statuses:
        computed = ValidityState.ACTIVE.value
    elif "weakened" in set_statuses:
        computed = ValidityState.NEEDS_VERIFICATION.value
    else:
        computed = ValidityState.HISTORICAL_ONLY.value

    # Monotonicity check: cascade never promotes
    return max(old_st, computed, key=lambda s: SEVERITY.get(s, 0))


def evaluate_lesson_from_measurements(
    old_state: Union[ValidityState, str],
    support_sets: List[List[str]],
    measurements_map: Dict[str, Dict[str, Any]],
    memories_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Evaluates an entire lesson given its support sets and lookup maps.

    Returns:
      {
        "computed_state": str,
        "set_statuses": List[str],
        "state_changed": bool,
        "saved_by_independent_support": bool,
        "surviving_set_index": Optional[int]
      }
    """
    if memories_map is None:
        memories_map = {}

    set_statuses: List[str] = []
    for s_set in support_sets:
        member_statuses: List[str] = []
        for mid in s_set:
            if mid.startswith("M") or mid in measurements_map:
                m_doc = measurements_map.get(mid, {})
                rec = m_doc.get("verdict", "pass")
                curr = m_doc.get("current_verdict", rec)
                member_statuses.append(evaluate_measurement_member(rec, curr))
            else:
                mem_doc = memories_map.get(mid, {})
                mem_st = mem_doc.get("validity_state", ValidityState.ACTIVE.value)
                member_statuses.append(evaluate_memory_member(mem_st))

        set_statuses.append(evaluate_support_set(member_statuses))

    old_st = old_state.value if isinstance(old_state, ValidityState) else str(old_state)
    new_st = lesson_state(old_st, set_statuses)

    # Independent support saved check:
    # State is ACTIVE, at least one set is holds, but at least one set is NOT holds
    saved_by_independent = (
        new_st == ValidityState.ACTIVE.value
        and "holds" in set_statuses
        and any(s in {"weakened", "broken"} for s in set_statuses)
    )

    surviving_idx = set_statuses.index("holds") if saved_by_independent else None

    return {
        "computed_state": new_st,
        "set_statuses": set_statuses,
        "state_changed": (new_st != old_st),
        "saved_by_independent_support": saved_by_independent,
        "surviving_set_index": surviving_idx,
    }


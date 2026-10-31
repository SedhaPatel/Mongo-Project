"""Deterministic ranking with a full per-memory trace (PLAN Section 7.5).

final = vector_score
      + state_bias
      + 0.2 * (MW - 0.5)
      + 0.05 * recency
      + 0.1 * scope_match

Every term is returned in ``ranking_trace`` so the UI can show one column per
term and nobody has to trust an opaque score.
"""

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

# Starting weights from PLAN 7.5; tune on seed data, never hide a term.
MW_WEIGHT = 0.2
RECENCY_WEIGHT = 0.05
SCOPE_WEIGHT = 0.1
RECENCY_HALF_LIFE_DAYS = 90.0

STATE_BIAS: Dict[str, float] = {
    "ACTIVE": 0.12,
    "PROVISIONAL": 0.04,
    "NEEDS_VERIFICATION": -0.10,
    "HISTORICAL_ONLY": -0.22,
    # SUPERSEDED is ranked like HISTORICAL_ONLY (DECISIONS 7).
    "SUPERSEDED": -0.22,
}

SCOPE_FIELDS: Sequence[str] = (
    "material",
    "process",
    "machine",
    "feature_class",
    "tolerance_band",
)


def memory_worth(success: int, fail: int) -> float:
    """MW = (successes + 1) / (successes + failures + 2)."""
    success = int(success or 0)
    fail = int(fail or 0)
    return (success + 1) / (success + fail + 2)


def _as_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def recency_factor(created_at: Any, now: Optional[datetime] = None) -> float:
    """exp(-age_days / 90); missing dates score 0, future dates clamp to 1."""
    created = _as_datetime(created_at)
    if created is None:
        return 0.0
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - created).total_seconds() / 86400.0)
    return math.exp(-age_days / RECENCY_HALF_LIFE_DAYS)


def _normalise(value: Any) -> str:
    return " ".join(str(value).strip().lower().split())


def scope_match(query_scope: Optional[Dict[str, Any]], doc_scope: Optional[Dict[str, Any]]) -> float:
    """Share of the *supplied* scope fields that match the memory's scope.

    Material and process are ranking terms, not hard filters (DECISIONS 5).
    With no scope supplied the term is neutral (1.0) rather than a division
    by zero; see docs/DECISIONS.md.
    """
    doc_scope = doc_scope or {}
    supplied = [
        field
        for field in SCOPE_FIELDS
        if query_scope and query_scope.get(field) not in (None, "")
    ]
    if not supplied:
        return 1.0
    matches = sum(
        1
        for field in supplied
        if _normalise(doc_scope.get(field, "")) == _normalise(query_scope[field])
    )
    return matches / len(supplied)


def score_memory(
    memory: Dict[str, Any],
    query_scope: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Return one ``ranking_trace`` row for a memory document."""
    state = str(memory.get("validity_state", "PROVISIONAL"))
    state_bias = STATE_BIAS.get(state, 0.0)
    mw = memory_worth(memory.get("mw_success", 0), memory.get("mw_fail", 0))
    mw_term = MW_WEIGHT * (mw - 0.5)
    recency = recency_factor(memory.get("created_at") or memory.get("valid_from"), now)
    recency_term = RECENCY_WEIGHT * recency
    match = scope_match(query_scope, memory.get("scope"))
    scope_term = SCOPE_WEIGHT * match
    vector_score = float(memory.get("vector_score", 0.0) or 0.0)

    final = vector_score + state_bias + mw_term + recency_term + scope_term
    return {
        "memory_id": memory.get("_id"),
        "vector_score": round(vector_score, 6),
        "state": state,
        "state_bias": round(state_bias, 6),
        "mw": round(mw, 6),
        "mw_term": round(mw_term, 6),
        "recency": round(recency, 6),
        "recency_term": round(recency_term, 6),
        "scope_match": round(match, 6),
        "scope_term": round(scope_term, 6),
        "final": round(final, 6),
    }


def rank_memories(
    memories: Sequence[Dict[str, Any]],
    query_scope: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Score and sort memories, highest final score first.

    Returns ``[{"memory": <doc>, "trace": <ranking_trace>}]``.  Ties break on
    memory ID so repeated runs produce byte-identical traces (PLAN 10).
    """
    rows = [
        {"memory": memory, "trace": score_memory(memory, query_scope, now)}
        for memory in memories
    ]
    rows.sort(key=lambda row: (-row["trace"]["final"], str(row["trace"]["memory_id"])))
    return rows


def traces(ranked: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract the trace rows from ``rank_memories`` output."""
    return [row["trace"] for row in ranked]

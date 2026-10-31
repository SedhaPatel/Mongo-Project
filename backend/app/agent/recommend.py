"""Deterministic plan building with LLM wording only (PLAN Section 7.7).

The order is fixed:

1. retrieve + rank (Section 7.5);
2. **code** builds every plan step from the memory's type and validity state;
3. the LLM may reword ``text`` only -- step count, ``kind`` and ``lesson_ids``
   are compared against the code-built plan and any mismatch falls back;
4. optionally persist the decision and add it to each memory's ``used_by``.

The LLM never chooses which lesson to apply, never picks the verify
instrument, and never changes a validity state.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from pymongo.database import Database

from backend.app.agent.llm import LLMUnavailable, reword_plan
from backend.app.config import WORKSPACE
from backend.app.events import log_event
from backend.app.memory.retrieval import retrieve_memories, traces
from backend.app.models import Decision
from backend.app.validity.lattice import evaluate_lesson_from_measurements

APPLY_STATES = {"ACTIVE", "PROVISIONAL"}
FAILED_ATTEMPT = "failed_attempt"
_LEARNING_TYPES = {"lesson", "failed_attempt"}


def _next_decision_id(db: Database) -> str:
    """Next free ``D<integer>``; demo-only IDs such as ``D-STAGE2`` are ignored."""
    pattern = re.compile(r"^D(\d+)$")
    highest = 0
    for doc in db.decisions.find({}):
        match = pattern.match(str(doc.get("_id", "")))
        if match:
            highest = max(highest, int(match.group(1)))
    return f"D{highest + 1}"


def _member_gauges(db: Database, member_id: str, seen: Optional[Set[str]] = None) -> Set[str]:
    """Instruments behind one support-set member (measurement or memory)."""
    if member_id.startswith("M"):
        measurement = db.measurements.find_one({"_id": member_id})
        return {measurement["gauge_id"]} if measurement else set()

    seen = seen or set()
    if member_id in seen:
        return set()
    seen.add(member_id)

    memory = db.memories.find_one({"_id": member_id})
    if not memory:
        return set()

    gauges: Set[str] = set()
    for support_set in memory.get("support_sets", []):
        for mid in support_set:
            gauges |= _member_gauges(db, mid, seen)
    return gauges


def _lesson_member_maps(
    db: Database, support_sets: Sequence[Sequence[str]]
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    member_ids = {mid for support_set in support_sets for mid in support_set}
    measurements = {
        doc["_id"]: doc for doc in db.measurements.find({"_id": {"$in": sorted(member_ids)}})
    }
    memories: Dict[str, Dict[str, Any]] = {}
    for member_id in sorted(member_ids):
        if member_id in measurements:
            continue
        memory = db.memories.find_one({"_id": member_id})
        if memory:
            memories[member_id] = memory
    return measurements, memories


def weakened_or_broken_gauges(db: Database, lesson: Dict[str, Any]) -> Set[str]:
    """Gauges whose support set no longer holds, so they cannot verify."""
    support_sets = [list(s) for s in lesson.get("support_sets") or []]
    if not support_sets:
        return set()

    measurements, memories = _lesson_member_maps(db, support_sets)
    evaluation = evaluate_lesson_from_measurements(
        lesson.get("validity_state", "PROVISIONAL"),
        support_sets,
        measurements,
        memories,
    )

    excluded: Set[str] = set()
    for support_set, status in zip(support_sets, evaluation["set_statuses"]):
        if status == "holds":
            continue
        for member_id in support_set:
            excluded |= _member_gauges(db, member_id)
    return excluded


def pick_verify_instrument(db: Database, lesson: Dict[str, Any]) -> Optional[str]:
    """First OK instrument outside the lesson's weakened/broken sets.

    Preference: ``type == "cmm"`` (a calibration lab result is what the
    lesson needs), then gauge ID alphabetically.  ``None`` when no gauge is
    both OK and independent.
    """
    excluded = weakened_or_broken_gauges(db, lesson)
    candidates = [
        gauge
        for gauge in db.gauges.find({"cal_status": "OK"})
        if gauge["_id"] not in excluded
    ]
    candidates.sort(key=lambda gauge: (0 if gauge.get("type") == "cmm" else 1, str(gauge["_id"])))
    return candidates[0]["_id"] if candidates else None


def _apply_text(action: str) -> str:
    return f"Apply: {action}"


def _verify_text(action: str, instrument: Optional[str]) -> str:
    if instrument:
        return f"Verify on {instrument} before adopting: {action}"
    return f"Verify on an independent instrument before adopting: {action}"


def _avoid_text(action: str, memory_id: str) -> str:
    # The failed-attempt action is already an imperative "Do not ..."; do not
    # stack a second "Do not:" in front of it.
    prefix = "" if action.strip().lower().startswith(("do not", "never")) else "Do not: "
    return f"{prefix}{action}. Failed on a prior job ({memory_id})"


def build_plan_steps(db: Database, ranked: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Code-built plan, in rank order (PLAN 7.7 step 2)."""
    steps: List[Dict[str, Any]] = []
    for row in ranked:
        memory = row["memory"]
        memory_id = str(memory.get("_id"))
        state = str(memory.get("validity_state", ""))
        memory_type = memory.get("type")
        action = str(memory.get("action", "")).strip()
        if not action or memory_type not in _LEARNING_TYPES:
            continue

        if memory_type == FAILED_ATTEMPT:
            steps.append(
                {
                    "kind": "avoid",
                    "text": _avoid_text(action, memory_id),
                    "lesson_ids": [memory_id],
                }
            )
        elif state in APPLY_STATES:
            steps.append(
                {"kind": "apply", "text": _apply_text(action), "lesson_ids": [memory_id]}
            )
        elif state == "NEEDS_VERIFICATION":
            instrument = pick_verify_instrument(db, memory)
            steps.append(
                {
                    "kind": "verify",
                    "text": _verify_text(action, instrument),
                    "lesson_ids": [memory_id],
                    "verify_instrument": instrument,
                }
            )
        # HISTORICAL_ONLY / SUPERSEDED memories never produce an apply step.
    return steps


def build_explanation(
    steps: Sequence[Dict[str, Any]], memories: Dict[str, Dict[str, Any]]
) -> str:
    """One deterministic sentence, grounded in the memory history."""
    for step in steps:
        if step.get("kind") != "verify":
            continue
        memory_id = step["lesson_ids"][0]
        memory = memories.get(memory_id, {})
        state = memory.get("validity_state", "NEEDS_VERIFICATION")
        cause = ""
        for entry in reversed(memory.get("history", [])):
            if entry.get("to_state") == state and entry.get("cause"):
                cause = str(entry["cause"])
                break
        detail = f" after {cause}" if cause else ""
        return (
            f"{memory_id} is now {state}{detail}, so the plan verifies it on "
            f"{step.get('verify_instrument')} before it is applied."
        )

    applies = [step["lesson_ids"][0] for step in steps if step.get("kind") == "apply"]
    avoids = [step["lesson_ids"][0] for step in steps if step.get("kind") == "avoid"]
    parts: List[str] = []
    if applies:
        parts.append("applies " + ", ".join(applies))
    if avoids:
        parts.append("avoids " + ", ".join(avoids))
    joined = " and ".join(parts) if parts else "has no usable step"
    return (
        "Ranked by similarity, validity state, Memory Worth and recency; "
        f"the plan {joined}."
    )


def validate_reword(
    result: Any, code_steps: Sequence[Dict[str, Any]]
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Accept only wording changes: same count, same order, same kind/IDs."""
    if not isinstance(result, dict):
        return None, "reword result is not a JSON object"
    steps = result.get("steps")
    if not isinstance(steps, list):
        return None, "reword result has no steps list"
    if len(steps) != len(code_steps):
        return None, f"step count changed from {len(code_steps)} to {len(steps)}"

    merged_steps: List[Dict[str, Any]] = []
    for index, (code_step, new_step) in enumerate(zip(code_steps, steps)):
        if not isinstance(new_step, dict):
            return None, f"steps[{index}] is not an object"
        if new_step.get("kind") != code_step["kind"]:
            return None, f"steps[{index}].kind changed"
        if list(new_step.get("lesson_ids") or []) != list(code_step["lesson_ids"]):
            return None, f"steps[{index}].lesson_ids changed"
        text = new_step.get("text")
        if not isinstance(text, str) or not text.strip():
            return None, f"steps[{index}].text is empty"

        merged = dict(code_step)
        merged["text"] = text.strip()
        merged_steps.append(merged)

    explanation = result.get("explanation")
    if not isinstance(explanation, str) or not explanation.strip():
        explanation = None
    return {"steps": merged_steps, "explanation": explanation}, None


def _reword_or_code(
    query: str,
    scope: Dict[str, Any],
    code_steps: Sequence[Dict[str, Any]],
    explanation: str,
    ranked: Sequence[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], str, Optional[str], List[str]]:
    """Ask for wording; return ``(steps, source, explanation, errors)``."""
    used_ids = [mid for step in code_steps for mid in step["lesson_ids"]]
    memories = {row["memory"]["_id"]: row["memory"] for row in ranked if row["memory"]["_id"] in used_ids}
    plan_input = {
        "query": query,
        "scope": scope,
        "draft_steps": list(code_steps),
        "draft_explanation": explanation,
        "memories": [
            {
                "_id": memory.get("_id"),
                "type": memory.get("type"),
                "validity_state": memory.get("validity_state"),
                "title": memory.get("title"),
                "history": memory.get("history", []),
            }
            for memory in memories.values()
        ],
    }

    errors: List[str] = []
    for attempt in (0, 1):
        try:
            result, origin = reword_plan(plan_input, attempt=attempt)
        except LLMUnavailable as exc:
            errors.append(f"attempt {attempt}: {exc}")
            continue

        validated, error = validate_reword(result, code_steps)
        if error is None:
            return (
                validated["steps"],
                origin,
                validated["explanation"] or explanation,
                errors,
            )
        errors.append(f"attempt {attempt}: {error}")

    return list(code_steps), "code", explanation, errors


def recommend(
    db: Database,
    *,
    query: str,
    scope: Optional[Dict[str, Any]] = None,
    workspace: str = WORKSPACE,
    persist: bool = True,
    history: bool = False,
    part_serials: Optional[Sequence[str]] = None,
    decision_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Handle ``POST /recommend`` (PLAN Section 7.7)."""
    scope = dict(scope or {})
    ranked = retrieve_memories(
        db,
        query=query,
        scope=scope,
        workspace=workspace,
        history=history,
        rank_limit=5,
        now=now,
    )

    code_steps = build_plan_steps(db, ranked)
    memories_by_id = {row["memory"]["_id"]: row["memory"] for row in ranked}
    explanation = build_explanation(code_steps, memories_by_id)

    steps, reword_source, explanation, reword_errors = _reword_or_code(
        query, scope, code_steps, explanation, ranked
    )

    lessons_used = [mid for step in steps for mid in step["lesson_ids"]]
    lesson_ids = list(dict.fromkeys(lessons_used))
    ranking_trace = traces(ranked)

    created_at = now or datetime.now().astimezone()
    serials = list(part_serials or scope.get("part_serials") or [])

    stored_id: Optional[str] = None
    if persist:
        stored_id = decision_id or _next_decision_id(db)
        decision = Decision(
            _id=stored_id,
            query=query,
            scope=scope,
            plan_steps=steps,
            lessons_used=lesson_ids,
            ranking_trace=ranking_trace,
            part_serials=serials,
            created_at=created_at,
            review_flag=False,
            review_reason=None,
        ).model_dump(by_alias=True)
        db.decisions.update_one({"_id": stored_id}, {"$set": decision}, upsert=True)
        for memory_id in lesson_ids:
            db.memories.update_one({"_id": memory_id}, {"$addToSet": {"used_by": stored_id}})
        log_event(
            db,
            "decision_created",
            decision_id=stored_id,
            lessons_used=lesson_ids,
            details={"query": query, "scope": scope},
        )

    return {
        "decision_id": stored_id,
        "query": query,
        "scope": scope,
        "plan_steps": steps,
        "lessons_used": lesson_ids,
        "ranking_trace": ranking_trace,
        "explanation": explanation,
        "reword_source": reword_source,
        "reword_errors": reword_errors,
        "part_serials": serials,
        "persisted": bool(persist),
    }

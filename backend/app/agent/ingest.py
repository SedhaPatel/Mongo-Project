"""NCR ingest and lesson drafting (PLAN Section 7.3).

The flow is deliberately boring and inspectable:

1. validate + upsert the measurements from the request;
2. ask Claude for a ``draft_lessons`` tool call (forced ``tool_choice``);
3. validate every draft against the input measurement IDs, retry once;
4. fall back to ``seed/fixtures/ncr_0412_lessons.json`` when the model is
   unavailable or keeps citing IDs that were not supplied;
5. write each validated draft through :func:`memory.writer.write_lesson`,
   which is the only code that can persist a lesson.

Nothing here decides validity: every lesson is written PROVISIONAL and the
lattice in ``validity/`` owns everything after that.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from pymongo.database import Database

from backend.app.agent.llm import LLMUnavailable, draft_lessons, store_draft_lessons
from backend.app.config import WORKSPACE
from backend.app.memory.writer import write_lesson
from backend.app.models import Measurement

NCR_FIXTURE = (
    Path(__file__).resolve().parent.parent.parent / "seed" / "fixtures" / "ncr_0412_lessons.json"
)

ALLOWED_KINDS = ("lesson", "failed_attempt")
SCOPE_FIELDS = ("material", "process", "machine", "feature_class", "tolerance_band")


class NCRValidationError(ValueError):
    """The request body or the returned draft cannot be used safely."""


def load_fallback_draft(ncr_id: str) -> Dict[str, Any]:
    """Load the committed offline draft, but only for the NCR it describes."""
    try:
        fixture = json.loads(NCR_FIXTURE.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise NCRValidationError(f"fallback draft fixture missing: {NCR_FIXTURE}") from exc

    if fixture.get("ncr_id") != ncr_id:
        raise NCRValidationError(
            f"no offline draft for {ncr_id!r}; the committed fixture covers "
            f"{fixture.get('ncr_id')!r}"
        )
    return {"lessons": fixture.get("lessons", [])}


def _upsert_measurements(db: Database, measurements: Sequence[Dict[str, Any]]) -> List[str]:
    """Validate, normalise and upsert each measurement; return their IDs."""
    if not measurements:
        raise NCRValidationError("measurements must contain at least one document")

    ids: List[str] = []
    for index, raw in enumerate(measurements):
        if not isinstance(raw, dict):
            raise NCRValidationError(f"measurements[{index}] is not an object")
        try:
            record = Measurement(**raw).model_dump(by_alias=True)
        except Exception as exc:  # pydantic.ValidationError and friends
            raise NCRValidationError(f"invalid measurement at index {index}: {exc}") from exc

        # The recorded verdict is immutable evidence; a new NCR starts with a
        # clean recomputation history (PLAN 7.3 step 1).
        record["current_verdict"] = record["verdict"]
        record["verdict_history"] = []

        db.measurements.update_one({"_id": record["_id"]}, {"$set": record}, upsert=True)
        ids.append(record["_id"])
    return ids


def _prompt_input(
    payload: Dict[str, Any], workspace: str, measurements: Sequence[Dict[str, Any]]
) -> Dict[str, Any]:
    """Stable, PII-free prompt body (also the disk-cache key, PLAN 7.6)."""
    summaries = [
        {
            "_id": m["_id"],
            "gauge_id": m["gauge_id"],
            "feature": m.get("feature"),
            "verdict": m.get("verdict"),
        }
        for m in measurements
    ]
    return {
        "ncr_id": payload["ncr_id"],
        "workspace": workspace,
        "summary": payload.get("summary", ""),
        "trials": payload.get("trials", []),
        "measurements": summaries,
    }


def validate_draft(
    draft: Any, allowed_ids: Set[str]
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Validate a ``draft_lessons`` result; return ``(clean, error)``.

    Hard rules from PLAN 7.3: every cited ID must come from the input and each
    lesson must cite at least one ID.  A draft that breaks them is never
    written, not even partially.
    """
    if not isinstance(draft, dict):
        return None, "draft is not a JSON object"
    lessons = draft.get("lessons")
    if not isinstance(lessons, list) or not lessons:
        return None, "draft.lessons must be a non-empty list"

    clean: List[Dict[str, Any]] = []
    for index, item in enumerate(lessons):
        if not isinstance(item, dict):
            return None, f"lessons[{index}] is not an object"

        kind = item.get("kind")
        if kind not in ALLOWED_KINDS:
            return None, f"lessons[{index}].kind must be one of {ALLOWED_KINDS}"

        for field in ("title", "content", "action"):
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                return None, f"lessons[{index}].{field} must be a non-empty string"

        scope = item.get("scope")
        if not isinstance(scope, dict):
            return None, f"lessons[{index}].scope must be an object"
        for field in ("material", "process"):
            value = scope.get(field)
            if not isinstance(value, str) or not value.strip():
                return None, f"lessons[{index}].scope.{field} is required"

        measurement_ids = item.get("measurement_ids")
        if not isinstance(measurement_ids, list) or not measurement_ids:
            return None, f"lessons[{index}].measurement_ids must be a non-empty list"
        if not all(isinstance(mid, str) and mid for mid in measurement_ids):
            return None, f"lessons[{index}].measurement_ids must contain strings"

        unknown = [mid for mid in measurement_ids if mid not in allowed_ids]
        if unknown:
            return None, (
                f"lessons[{index}] cites measurement(s) not in the input: "
                + ", ".join(unknown)
            )

        clean.append(
            {
                "kind": kind,
                "title": item["title"].strip(),
                "content": item["content"].strip(),
                "action": item["action"].strip(),
                "scope": {
                    field: str(scope[field]).strip()
                    for field in SCOPE_FIELDS
                    if scope.get(field) not in (None, "")
                },
                "measurement_ids": list(dict.fromkeys(measurement_ids)),
            }
        )

    return {"lessons": clean}, None


def _obtain_draft(
    prompt: Dict[str, Any],
) -> Tuple[Dict[str, Any], str, List[str]]:
    """Try the forced tool twice, then the committed fixture.

    Returns ``(validated_draft, origin, errors)`` where ``origin`` is one of
    ``llm``, ``cache`` or ``fallback``.
    """
    allowed_ids = {m["_id"] for m in prompt["measurements"]}
    errors: List[str] = []

    for attempt in (0, 1):
        try:
            result, origin = draft_lessons(prompt, attempt=attempt)
        except LLMUnavailable as exc:
            errors.append(f"attempt {attempt}: {exc}")
            continue

        clean, error = validate_draft(result, allowed_ids)
        if error is None:
            return clean, origin, errors
        errors.append(f"attempt {attempt}: {error}")

    fallback = load_fallback_draft(prompt["ncr_id"])
    clean, error = validate_draft(fallback, allowed_ids)
    if error is not None:
        raise NCRValidationError(
            "the offline draft is not valid for this NCR: " + error
        )

    # Seed the disk cache so an offline replay returns the same bytes.
    store_draft_lessons(prompt, clean)
    return clean, "fallback", errors


def ingest_ncr(
    db: Database,
    payload: Dict[str, Any],
    *,
    workspace: Optional[str] = None,
) -> Dict[str, Any]:
    """Handle ``POST /ncr`` (PLAN Section 7.3)."""
    if not isinstance(payload, dict):
        raise NCRValidationError("request body must be a JSON object")
    ncr_id = payload.get("ncr_id")
    if not isinstance(ncr_id, str) or not ncr_id.strip():
        raise NCRValidationError("ncr_id is required")

    workspace = workspace or payload.get("workspace") or WORKSPACE
    measurement_ids = _upsert_measurements(db, payload.get("measurements", []))
    prompt = _prompt_input(payload, workspace, payload["measurements"])

    draft, origin, errors = _obtain_draft(prompt)

    source = {
        "ncr_id": ncr_id,
        "author_role": payload.get("author_role", "manufacturing-engineer"),
        "session_id": payload.get("session_id"),
    }

    created: List[Dict[str, Any]] = []
    for lesson in draft["lessons"]:
        doc = write_lesson(
            db,
            type=lesson["kind"],
            title=lesson["title"],
            content=lesson["content"],
            action=lesson["action"],
            scope=lesson["scope"],
            measurement_ids=lesson["measurement_ids"],
            source=source,
            workspace=workspace,
        )
        created.append(doc)

    return {
        "ncr_id": ncr_id,
        "workspace": workspace,
        "draft_source": origin,
        "draft_errors": errors,
        "measurement_ids": measurement_ids,
        "memory_ids": [doc["_id"] for doc in created],
        "memories": [
            {
                "_id": doc["_id"],
                "type": doc["type"],
                "title": doc["title"],
                "validity_state": doc["validity_state"],
                "support_sets": doc["support_sets"],
                "derived_from": doc["derived_from"],
            }
            for doc in created
        ],
    }

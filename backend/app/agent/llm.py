"""Claude and Gemini calls for Metrologic, with forced tool use and a disk cache.

Two jobs only (PLAN Section 0 rule 2):

- ``draft_lessons`` turns NCR text into lesson drafts (Section 7.3).
- ``reword_plan`` rewrites wording of plan steps that code already built
  (Section 7.7).  It may never add, remove or re-type a step.

Every response is cached by ``sha256(model + canonical JSON input)`` in
``CACHE_DIR`` (Section 7.6), so the demo replays byte-identically offline.
``OFFLINE=1`` on a miss raises :class:`LLMUnavailable`; callers fall back to the
committed fixtures.  Supports both Google Gemini and Anthropic Claude REST APIs.
"""

import json
from typing import Any, Dict, List, Optional, Tuple

import httpx

from backend.app.cache import compute_cache_key, get_cached_response, set_cached_response
from backend.app.config import (
    ANTHROPIC_API_KEY,
    GOOGLE_API_KEY,
    LLM_MODEL,
    LLM_PROVIDER,
)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

DRAFT_TOOL = "draft_lessons"
REWORD_TOOL = "reword_plan"


class LLMUnavailable(RuntimeError):
    """The model could not be reached (no key, offline cache miss, transport error)."""


DRAFT_SYSTEM = (
    "You draft reusable manufacturing lessons from a non-conformance report (NCR). "
    f"Call the {DRAFT_TOOL} tool exactly once. Rules: cite ONLY measurement IDs that "
    "appear in the input; never invent an ID. A trial whose outcome is 'fail' becomes "
    "kind 'failed_attempt'; a trial whose outcome is 'pass' becomes kind 'lesson'. "
    "Each draft must cite at least one measurement ID, and its scope must name the "
    "material and the process. Write a short title, one or two sentences of content, "
    "and one imperative action. Do not mention customer or operator names."
)

DRAFT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "lessons": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["lesson", "failed_attempt"]},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "action": {"type": "string"},
                    "scope": {
                        "type": "object",
                        "properties": {
                            "material": {"type": "string"},
                            "process": {"type": "string"},
                            "machine": {"type": "string"},
                            "feature_class": {"type": "string"},
                            "tolerance_band": {"type": "string"},
                        },
                        "required": ["material", "process"],
                    },
                    "measurement_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                },
                "required": [
                    "kind",
                    "title",
                    "content",
                    "action",
                    "scope",
                    "measurement_ids",
                ],
            },
        }
    },
    "required": ["lessons"],
}

REWORD_SYSTEM = (
    "You rewrite plan steps for a machinist. The steps were built by deterministic "
    "code from stored memories. Return the SAME number of steps in the SAME order, "
    f"with the SAME kind and the SAME lesson_ids; call {REWORD_TOOL} exactly once. "
    "Improve only the 'text' wording. Do not add advice, do not merge steps, do not "
    "drop steps, do not rename lessons. The explanation must be one sentence grounded "
    "in the supplied state history, and must not invent measurements or gauges."
)

REWORD_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string"},
                    "lesson_ids": {"type": "array", "items": {"type": "string"}},
                    "text": {"type": "string"},
                },
                "required": ["kind", "lesson_ids", "text"],
            },
        },
        "explanation": {"type": "string"},
    },
    "required": ["steps", "explanation"],
}


def _canonical_json(obj: Any) -> str:
    """Serialize objects to JSON with default=str to safely support datetimes."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)


def _tool_payload(system: str, user_input: Dict[str, Any], attempt: int) -> Dict[str, Any]:
    """Canonical cache payload; ``attempt`` forces a real second call on retry."""
    return {"system": system, "input": user_input, "attempt": attempt}


def _cache_key(model: str, tool: str, payload: Dict[str, Any]) -> str:
    return compute_cache_key(f"{model}:tool:{tool}", payload)


def _call_gemini_tool(
    system: str,
    user_input: Dict[str, Any],
    tool: str,
    schema: Dict[str, Any],
    model: str,
) -> Dict[str, Any]:
    """Call Google Gemini REST API with forced function declaration."""
    if not GOOGLE_API_KEY:
        raise LLMUnavailable("GOOGLE_API_KEY is not configured")

    gemini_model = model
    if not gemini_model or "gemini" not in gemini_model.lower():
        gemini_model = "gemini-2.5-flash"
    elif gemini_model == "gemini-2.5-flash-lite":
        gemini_model = "gemini-2.5-flash"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"

    body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": _canonical_json(user_input)}],
            }
        ],
        "systemInstruction": {
            "parts": [{"text": system}],
        },
        "tools": [
            {
                "functionDeclarations": [
                    {
                        "name": tool,
                        "description": schema.get("description", tool),
                        "parameters": schema,
                    }
                ]
            }
        ],
        "toolConfig": {
            "functionCallingConfig": {
                "mode": "ANY",
                "allowedFunctionNames": [tool],
            }
        },
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                url,
                headers={
                    "x-goog-api-key": GOOGLE_API_KEY,
                    "content-type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise LLMUnavailable(f"Gemini request failed: {exc}") from exc

    candidates = data.get("candidates", [])
    if not candidates:
        raise LLMUnavailable("Gemini returned no candidates")

    for part in candidates[0].get("content", {}).get("parts", []):
        fn_call = part.get("functionCall")
        if fn_call and fn_call.get("name") == tool:
            args = fn_call.get("args")
            if isinstance(args, dict):
                return args
    raise LLMUnavailable(f"Gemini returned no functionCall block for {tool}")


def _messages_body(
    system: str,
    user_input: Dict[str, Any],
    tool: str,
    schema: Dict[str, Any],
    model: str,
    max_tokens: int,
) -> Dict[str, Any]:
    return {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [
            {
                "role": "user",
                "content": _canonical_json(user_input),
            }
        ],
        "tools": [{"name": tool, "description": schema.get("description", tool), "input_schema": schema}],
        "tool_choice": {"type": "tool", "name": tool},
    }


def _call_forced_tool(
    *,
    tool: str,
    schema: Dict[str, Any],
    system: str,
    user_input: Dict[str, Any],
    attempt: int = 0,
    model: str = LLM_MODEL,
    max_tokens: int = 2048,
) -> Tuple[Dict[str, Any], str]:
    """Call the model with a forced tool; returns ``(tool_input, origin)``."""
    payload = _tool_payload(system, user_input, attempt)
    key = _cache_key(model, tool, payload)
    try:
        cached = get_cached_response(key)
    except RuntimeError as exc:  # OFFLINE=1 and a miss
        raise LLMUnavailable(str(exc)) from exc
    if cached is not None:
        return cached, "cache"

    # Provider selection: Gemini or Anthropic
    if LLM_PROVIDER == "gemini" or (GOOGLE_API_KEY and not ANTHROPIC_API_KEY):
        result = _call_gemini_tool(system, user_input, tool, schema, model)
        set_cached_response(key, result)
        return result, "llm"

    if not ANTHROPIC_API_KEY:
        raise LLMUnavailable("Neither GOOGLE_API_KEY nor ANTHROPIC_API_KEY is configured")

    body = _messages_body(system, user_input, tool, schema, model, max_tokens)
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                ANTHROPIC_URL,
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise LLMUnavailable(f"Anthropic request failed: {exc}") from exc

    for block in data.get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == tool:
            result = block.get("input")
            if not isinstance(result, dict):
                raise LLMUnavailable(f"{tool} returned a non-object tool input")
            set_cached_response(key, result)
            return result, "llm"
    raise LLMUnavailable(f"model returned no forced tool_use block for {tool}")


def draft_lessons(
    ncr_input: Dict[str, Any], *, attempt: int = 0, model: str = LLM_MODEL
) -> Tuple[Dict[str, Any], str]:
    """Draft lessons from NCR text.  Returns ``({"lessons": [...]}, origin)``."""
    return _call_forced_tool(
        tool=DRAFT_TOOL,
        schema=dict(DRAFT_SCHEMA, description=DRAFT_SYSTEM),
        system=DRAFT_SYSTEM,
        user_input=ncr_input,
        attempt=attempt,
        model=model,
    )


def store_draft_lessons(
    ncr_input: Dict[str, Any], result: Dict[str, Any], *, attempt: int = 0, model: str = LLM_MODEL
) -> None:
    """Seed the disk cache with a validated fallback draft (offline replay)."""
    payload = _tool_payload(DRAFT_SYSTEM, ncr_input, attempt)
    set_cached_response(_cache_key(model, DRAFT_TOOL, payload), result)


def reword_plan(
    plan_input: Dict[str, Any], *, attempt: int = 0, model: str = LLM_MODEL
) -> Tuple[Dict[str, Any], str]:
    """Rewrite plan wording.  Validation of the shape happens in recommend.py."""
    return _call_forced_tool(
        tool=REWORD_TOOL,
        schema=dict(REWORD_SCHEMA, description=REWORD_SYSTEM),
        system=REWORD_SYSTEM,
        user_input=plan_input,
        attempt=attempt,
        model=model,
        max_tokens=1500,
    )

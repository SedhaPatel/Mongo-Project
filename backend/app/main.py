"""FastAPI application for Metrologic.

Implements Section 8 of docs/PLAN.md: the JSON API, the two change stream
watchers (started in lifespan), and the SSE feed the frontend subscribes to.

Design rules enforced here:

- **No database at import time.**  ``get_db_handle()`` is lazy, so importing
  this module (or ``create_app()``) never needs MongoDB.  Tests inject an
  in-memory database by setting ``main._db``.
- **One SSE bus.**  ``GET /events`` subscribes to ``backend.app.events``, the
  same bus every watcher and endpoint publishes to, and unsubscribes inside
  the response generator.
- **Thin endpoints.**  Business logic lives in ``agent/ingest.py``,
  ``agent/recommend.py``, ``memory/writer.py`` and ``validity/cascade.py``.
"""

import asyncio
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pymongo.database import Database

from backend.app.agent.ingest import NCRValidationError, ingest_ncr
from backend.app.agent.recommend import recommend
from backend.app.config import MONGODB_DB, WORKSPACE
from backend.app.db import bootstrap, get_db
from backend.app.events import (
    clear_events,
    get_replay_events,
    set_event_loop,
    subscribe_events,
    unsubscribe_events,
)
from backend.app.memory.retrieval import search_memories
from backend.app.memory.writer import ProvenanceError, corroborate
from backend.app.streams.gauge_watcher import (
    post_calibration_event,
    start_gauge_watcher,
    stop_gauge_watcher,
)
from backend.app.streams.memory_watcher import start_memory_watcher, stop_memory_watcher
from backend.seed.reset import parse_datetime

SCENARIO_FILE = Path(__file__).resolve().parent.parent / "seed" / "scenario.yaml"

STAGE2_QUERY = "Process plan for an Inconel 718 sleeve with a Ø28H7 bore"
STAGE2_SCOPE: Dict[str, str] = {
    "material": "Inconel 718",
    "process": "finish boring",
    "machine": "VF-4",
    "feature_class": "bore",
    "tolerance_band": "H7",
}

# Request trials for NCR-0412 (PLAN 7.3).  The measurement documents themselves
# come from seed/scenario.yaml, which stays the single source of truth.
NCR_0412_TRIALS: List[Dict[str, Any]] = [
    {
        "id": "A",
        "description": "Reduce feed only",
        "outcome": "fail",
        "measurement_ids": ["M14", "M15", "M16"],
    },
    {
        "id": "B",
        "description": "Spring pass plus lower radial engagement",
        "outcome": "pass",
        "measurement_ids": ["M1", "M2", "M3", "M4", "M5"],
    },
    {
        "id": "C",
        "description": "Coolant concentration 8% to 10% on Inconel 718",
        "outcome": "pass",
        "measurement_ids": ["M9", "M10", "M11", "M12", "M13"],
    },
]

# Resolve lazily; watchers and endpoints share the same handle once created.
_db: Optional[Database] = None


def get_db_handle() -> Database:
    global _db
    if _db is None:
        _db = get_db(MONGODB_DB)
    return _db


def _supports_change_streams(db: Database) -> bool:
    """True only on a replica set / mongos (change streams are unavailable otherwise)."""
    try:
        hello = db.command("hello")
    except Exception:
        return False
    return bool(hello.get("setName") or hello.get("msg") == "isdbgrid")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bootstrap the database and start watchers when the deployment supports them."""
    db = get_db_handle()
    set_event_loop(asyncio.get_running_loop())

    try:
        bootstrap(db)
    except Exception as exc:  # pragma: no cover - deployment dependent
        print(f"Notice: bootstrap failed: {exc}")

    if _supports_change_streams(db):
        try:
            start_gauge_watcher(db)
            start_memory_watcher(db)
        except Exception as exc:  # pragma: no cover - deployment dependent
            print(f"Notice: failed to start watchers: {exc}")

    try:
        yield
    finally:
        stop_gauge_watcher()
        stop_memory_watcher()
        set_event_loop(None)


def _sse_stream(replay: int = 0):
    """StreamingResponse body for ``GET /events?replay=1``."""

    async def _gen():
        q = subscribe_events()
        try:
            if replay:
                for event in get_replay_events(200):
                    yield f"data: {json.dumps(event, default=str)}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(event, default=str)}\n\n"
        finally:
            unsubscribe_events(q)

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _scenario() -> Dict[str, Any]:
    with open(SCENARIO_FILE, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _scenario_measurements(ids) -> List[Dict[str, Any]]:
    wanted = set(ids)
    return [m for m in _scenario().get("measurements", []) if m["_id"] in wanted]


def _demo_ncr_body() -> Dict[str, Any]:
    """Stage 1a request: the 13 BG-07 measurements from the scenario."""
    ids = [f"M{i}" for i in range(1, 6)] + [f"M{i}" for i in range(9, 17)]
    return {
        "ncr_id": "NCR-0412",
        "workspace": WORKSPACE,
        "summary": (
            "Ti-6Al-4V housing, Ø32H7 bore tapered after finish boring. "
            "Separate chatter on Inconel 718 sleeve."
        ),
        "trials": NCR_0412_TRIALS,
        "measurements": _scenario_measurements(ids),
    }


def _demo_stage(stage_n: int, step: Optional[str] = None) -> Dict[str, Any]:
    """Dispatch ``POST /demo/stage/{n}?step=...`` (PLAN Section 10)."""
    db = get_db_handle()

    if stage_n == 1 and step in (None, "a"):
        response = ingest_ncr(db, _demo_ncr_body())
        return {"stage": "1a", "status": "success", **response}

    if stage_n == 1 and step == "b":
        cmm = [parse_datetime(m) for m in _scenario_measurements(["M6", "M7", "M8"])]
        memory = corroborate(
            db,
            "L1",
            measurement_ids=["M6", "M7", "M8"],
            job_id="NCR-0419",
            measurements=cmm,
        )
        return {
            "stage": "1b",
            "status": "success",
            "memory_id": memory["_id"],
            "new_state": memory["validity_state"],
            "memory": memory,
        }

    if stage_n == 2:
        response = recommend(
            db,
            query=STAGE2_QUERY,
            scope=STAGE2_SCOPE,
            persist=True,
            part_serials=["SN-3001", "SN-3002"],
            decision_id="D-STAGE2",
        )
        return {"stage": "2", "status": "success", **response}

    if stage_n == 3 and step == "arm":
        from backend.seed.stages import run_stage_3_arm

        return run_stage_3_arm(db)

    if stage_n == 3 and step is None:
        from backend.seed.stages import run_stage_3

        return run_stage_3(db)

    raise HTTPException(
        status_code=404,
        detail=f"unknown demo stage {stage_n}" + (f"?step={step}" if step else ""),
    )


def _demo_reset() -> Dict[str, Any]:
    """``POST /demo/reset``: drop, reload seed data, clear the replay buffer."""
    from backend.seed.reset import reset_database

    result = reset_database(get_db_handle())
    clear_events()
    return result


def _post_ncr(payload: Dict[str, Any]) -> Dict[str, Any]:
    """``POST /ncr`` (PLAN 7.3)."""
    try:
        return ingest_ncr(get_db_handle(), payload)
    except NCRValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProvenanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _post_corroborate(lesson_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """``POST /lessons/{id}/corroborate`` (PLAN 7.4)."""
    measurement_ids = payload.get("measurement_ids") or []
    if not isinstance(measurement_ids, list):
        raise HTTPException(status_code=400, detail="measurement_ids must be a list")
    measurements = payload.get("measurements") or []
    if not isinstance(measurements, list):
        raise HTTPException(status_code=400, detail="measurements must be a list")

    try:
        return corroborate(
            get_db_handle(),
            lesson_id,
            measurement_ids=measurement_ids,
            job_id=str(payload.get("job_id", "")),
            measurements=measurements,
        )
    except ProvenanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"memory not found: {lesson_id}") from exc


def _post_recommend(payload: Dict[str, Any]) -> Dict[str, Any]:
    """``POST /recommend`` (PLAN 7.7)."""
    query = payload.get("query")
    if not isinstance(query, str) or not query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    scope = payload.get("scope") or {}
    if not isinstance(scope, dict):
        raise HTTPException(status_code=400, detail="scope must be an object")

    try:
        return recommend(
            get_db_handle(),
            query=query,
            scope=scope,
            workspace=payload.get("workspace") or WORKSPACE,
            persist=bool(payload.get("persist", True)),
            history=bool(payload.get("history", False)),
            part_serials=payload.get("part_serials"),
        )
    except (ValueError, RuntimeError) as exc:
        # Offline embedding miss (OFFLINE=1 or no Voyage key for unseen text).
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _calibration_endpoint(payload: Dict[str, Any], direct: bool = False) -> Dict[str, Any]:
    """Write an as-found calibration result to ``gauges`` and run the cascade."""
    gauge_id = payload.get("gauge_id") or payload.get("gauge")
    if not isinstance(gauge_id, str) or not gauge_id:
        raise HTTPException(status_code=400, detail="gauge_id is required")

    result = str(payload.get("result", "OUT_OF_TOLERANCE"))
    if result.upper() != "OUT_OF_TOLERANCE":
        raise HTTPException(
            status_code=400, detail="only OUT_OF_TOLERANCE calibration events are supported"
        )

    db = get_db_handle()
    if db.gauges.find_one({"_id": gauge_id}) is None:
        raise HTTPException(status_code=404, detail=f"gauge not found: {gauge_id}")

    try:
        e = float(payload.get("as_found_error_mm", 0.0))
        u = float(payload.get("as_found_u_mm", 0.0))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="as_found values must be numbers") from exc

    direct_flag = bool(direct) or bool(payload.get("direct"))
    # Change streams cannot run on a standalone server; perform the cascade
    # inline instead of silently doing nothing (DECISIONS 23).
    if not direct_flag and not _supports_change_streams(db):
        direct_flag = True

    return post_calibration_event(
        db=db,
        gauge_id=gauge_id,
        as_found_error_mm=e,
        as_found_u_mm=u,
        direct=direct_flag,
        event_id=payload.get("event_id"),
        event_time=payload.get("event_time"),
    )


def _review_decisions() -> List[Dict[str, Any]]:
    """``GET /decisions/review``: flagged decisions, newest first."""
    docs = list(get_db_handle().decisions.find({"review_flag": True}))
    docs.sort(key=lambda doc: str(doc.get("created_at") or ""), reverse=True)
    return [
        {
            "_id": doc["_id"],
            "query": doc.get("query", ""),
            "plan_steps": doc.get("plan_steps", []),
            "lessons_used": doc.get("lessons_used", []),
            "part_serials": doc.get("part_serials", []),
            "created_at": doc.get("created_at"),
            "review_reason": doc.get("review_reason"),
        }
        for doc in docs
    ]


def _is_background(memory_id: Any) -> bool:
    return re.match(r"^B\d+$", str(memory_id)) is not None


def _graph_elements() -> Dict[str, Any]:
    """Cytoscape elements, kept under 40 nodes (PLAN 8.1).

    Demo lessons (anything not ``B<n>``) keep one child node per referenced
    measurement.  Filler measurements collapse into one ``measurement_group``
    per gauge.  The 13 background lessons collapse into one ``lesson_group``
    node (``background=true``) so the live graph stays inside the budget; the
    UI can hide that node behind its background toggle.
    """
    db = get_db_handle()
    gauges = list(db.gauges.find({}))
    memories = list(db.memories.find({"type": {"$in": ["lesson", "failed_attempt"]}}))
    decisions = list(db.decisions.find({}))

    background = [memory for memory in memories if _is_background(memory["_id"])]
    demo_memories = [memory for memory in memories if not _is_background(memory["_id"])]
    demo_ids = {memory["_id"] for memory in demo_memories}

    measurement_ids: List[str] = []
    for memory in demo_memories:
        for support_set in memory.get("support_sets", []):
            for member_id in support_set:
                if member_id not in demo_ids and member_id not in measurement_ids:
                    measurement_ids.append(member_id)
    measurements = list(db.measurements.find({"_id": {"$in": measurement_ids}}))
    measurement_by_id = {measurement["_id"]: measurement for measurement in measurements}

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    edge_ids = set()

    for gauge in gauges:
        nodes.append(
            {
                "data": {
                    "id": f"g:{gauge['_id']}",
                    "label": f"Gauge: {gauge['_id']} ({gauge.get('type', 'gauge')})",
                    "kind": "gauge",
                    "status": gauge.get("cal_status", "OK"),
                }
            }
        )

    for measurement_id, measurement in measurement_by_id.items():
        nodes.append(
            {
                "data": {
                    "id": measurement_id,
                    "label": (
                        f"{measurement_id}: {measurement.get('value_mm', '?')} "
                        f"({measurement.get('verdict', 'pass')})"
                    ),
                    "kind": "measurement",
                    "verdict": measurement.get("verdict", "pass"),
                    "current_verdict": measurement.get(
                        "current_verdict", measurement.get("verdict", "pass")
                    ),
                    "parent": f"g:{measurement.get('gauge_id', '')}",
                }
            }
        )

    # One filler group per gauge; the count excludes child measurements.
    child_ids = set(measurement_by_id)
    for gauge in gauges:
        gauge_id = gauge["_id"]
        filler = [
            measurement
            for measurement in db.measurements.find({"gauge_id": gauge_id})
            if measurement["_id"] not in child_ids
        ]
        if not filler:
            continue
        group_id = f"group:{gauge_id}"
        nodes.append(
            {
                "data": {
                    "id": group_id,
                    "label": f"{len(filler)} other measurements",
                    "kind": "measurement_group",
                    "count": len(filler),
                    "parent": f"g:{gauge_id}",
                }
            }
        )

    for memory in demo_memories:
        memory_id = memory["_id"]
        nodes.append(
            {
                "data": {
                    "id": memory_id,
                    "label": f"{memory_id}: {memory.get('title', memory.get('type', ''))}",
                    "kind": "lesson" if memory.get("type") == "lesson" else "failed_attempt",
                    "state": memory.get("validity_state", "PROVISIONAL"),
                    "flagged": memory.get("validity_state") == "HISTORICAL_ONLY",
                }
            }
        )
        for support_set in memory.get("support_sets", []):
            for member_id in support_set:
                source_id = None
                if member_id in measurement_by_id:
                    source_id = member_id
                elif member_id in demo_ids:
                    source_id = member_id
                if source_id is None:
                    continue
                edge_id = f"e_{source_id}_{memory_id}"
                if edge_id in edge_ids:
                    continue
                edge_ids.add(edge_id)
                edges.append(
                    {"data": {"id": edge_id, "source": source_id, "target": memory_id}}
                )

    if background:
        nodes.append(
            {
                "data": {
                    "id": "background_lessons",
                    "label": f"{len(background)} background lessons",
                    "kind": "lesson_group",
                    "count": len(background),
                    "background": True,
                }
            }
        )

    for decision in decisions:
        decision_id = decision["_id"]
        nodes.append(
            {
                "data": {
                    "id": decision_id,
                    "label": f"{decision_id}: {str(decision.get('query', ''))[:40]}",
                    "kind": "decision",
                    "flagged": decision.get("review_flag", False),
                }
            }
        )
        for lesson_id in decision.get("lessons_used", []):
            if lesson_id not in demo_ids:
                continue
            edge_id = f"e_{lesson_id}_{decision_id}"
            if edge_id in edge_ids:
                continue
            edge_ids.add(edge_id)
            edges.append(
                {"data": {"id": edge_id, "source": lesson_id, "target": decision_id}}
            )

    # Cytoscape convention, matching frontend/fixtures/graph.stage*.json.
    return {"elements": {"nodes": nodes, "edges": edges}}


def _memory_detail(memory_id: str) -> Dict[str, Any]:
    """Memory document plus its evidence chain (recorded vs current verdict)."""
    db = get_db_handle()
    memory = db.memories.find_one({"_id": memory_id})
    if memory is None:
        raise HTTPException(status_code=404, detail="memory not found")

    evidence: List[Dict[str, Any]] = []
    for set_index, support_set in enumerate(memory.get("support_sets", [])):
        for member_id in support_set:
            measurement = db.measurements.find_one({"_id": member_id})
            if measurement is None:
                member_memory = db.memories.find_one({"_id": member_id})
                if member_memory is not None:
                    evidence.append(
                        {
                            "memory_id": member_id,
                            "validity_state": member_memory.get("validity_state"),
                            "support_set_index": set_index,
                        }
                    )
                continue

            gauge = db.gauges.find_one({"_id": measurement.get("gauge_id")}) or {}
            evidence.append(
                {
                    "measurement_id": measurement["_id"],
                    "gauge_id": measurement.get("gauge_id"),
                    "gauge_cal_status": gauge.get("cal_status", "OK"),
                    "value_mm": measurement.get("value_mm"),
                    "verdict": measurement.get("verdict"),
                    "current_verdict": measurement.get("current_verdict"),
                    "u_mm": measurement.get("u_mm"),
                    "timestamp": measurement.get("timestamp"),
                    "feature": measurement.get("feature"),
                    "support_set_index": set_index,
                }
            )

    # Flat document (as in frontend/fixtures/memory.L1.json) plus the evidence
    # chain required by PLAN Section 8.
    return {**memory, "evidence": evidence}


def _memories_search(
    q: str,
    material: Optional[str] = None,
    process: Optional[str] = None,
    machine: Optional[str] = None,
    feature_class: Optional[str] = None,
    tolerance_band: Optional[str] = None,
    history: int = 0,
    scope_filter: int = 0,
    limit: int = 10,
    rank_limit: int = 5,
) -> Dict[str, Any]:
    """``GET /memories/search`` (PLAN 7.5)."""
    scope = {
        key: value
        for key, value in {
            "material": material,
            "process": process,
            "machine": machine,
            "feature_class": feature_class,
            "tolerance_band": tolerance_band,
        }.items()
        if value
    }
    try:
        return search_memories(
            get_db_handle(),
            query=q,
            scope=scope,
            history=bool(history),
            scope_filter=bool(scope_filter),
            limit=limit,
            rank_limit=rank_limit,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    app = FastAPI(title="Metrologic", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- SSE feed (Section 7.1) ----
    app.add_api_route("/events", _sse_stream, methods=["GET"], include_in_schema=False)

    # ---- memory and agent endpoints (Section 7/8) ----
    app.add_api_route("/ncr", _post_ncr, methods=["POST"], include_in_schema=False)
    app.add_api_route(
        "/lessons/{lesson_id}/corroborate",
        _post_corroborate,
        methods=["POST"],
        include_in_schema=False,
    )
    app.add_api_route("/recommend", _post_recommend, methods=["POST"], include_in_schema=False)

    # `/memories/search` must be registered before `/memories/{memory_id}`.
    app.add_api_route(
        "/memories/search", _memories_search, methods=["GET"], include_in_schema=False
    )
    app.add_api_route(
        "/memories/{memory_id}", _memory_detail, methods=["GET"], include_in_schema=False
    )
    app.add_api_route("/graph", _graph_elements, methods=["GET"], include_in_schema=False)

    # ---- calibration and review ----
    app.add_api_route(
        "/calibration", _calibration_endpoint, methods=["POST"], include_in_schema=False
    )
    app.add_api_route(
        "/decisions/review", _review_decisions, methods=["GET"], include_in_schema=False
    )

    # ---- demo stage runners (Section 10) ----
    app.add_api_route(
        "/demo/stage/{stage_n}", _demo_stage, methods=["POST"], include_in_schema=False
    )
    app.add_api_route("/demo/reset", _demo_reset, methods=["POST"], include_in_schema=False)

    return app


# ``uvicorn backend.app.main:app`` (Makefile) and the shim both work.
app = create_app()

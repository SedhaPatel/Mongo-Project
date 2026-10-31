"""FastAPI application for Metrologic.

Implements Section 8 of docs/PLAN.md: the whole JSON API, the two change
stream watchers (started in lifespan), and the SSE feed the frontend
subscribes to.  Every endpoint that belongs to a runner is thin: the
actual business logic lives in backend/seed/stages.py for the demo
stages and in backend/app/validity/cascade.py for the calibration event.
The two watchers never block the event loop: each runs in its own daemon
thread, and SSE listeners subscribe to a thread-safe asyncio queue that
publishers (the watcher threads) push into with call_soon_threadsafe.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

from backend.app.streams.sse import subscribe, unsubscribe
from fastapi import FastAPI, HTTPException
from fastapi.responses import EventSourceResponse, StreamingResponse
from pymongo.database import Database

from backend.app.config import (
    CACHE_DIR,
    MONGODB_DB,
    MONGODB_URI,
    OFFLINE,
    WORKSPACE,
)
from backend.app.db import bootstrap, get_db

from backend.app.streams.gauge_watcher import (
    post_calibration_event,
    start_gauge_watcher,
    stop_gauge_watcher,
)



# Resolve the database once; watchers and endpoints share the same handle.
_db: Optional[Database] = None


def get_db_handle() -> Database:
    global _db
    if _db is None:
        _db = get_db(MONGODB_DB)
    return _db


DB = get_db_handle()


def _demo_stage_runner(stage_n: int, step: Optional[str] = None) -> Dict[str, object]:
    """Dispatch the demo stage runners from backend/seed/stages.py."""
    from backend.seed.stages import (
        run_stage_1a,
        run_stage_1b,
        run_stage_2,
        run_stage_3,
        run_stage_3_arm,
    )

    if stage_n == 1 and step == "a":
        return run_stage_1a(DB)
    if stage_n == 1 and step == "b":
        return run_stage_1b(DB)
    if stage_n == 2:
        return run_stage_2(DB)
    if stage_n == 3 and step == "arm":
        return run_stage_3_arm(DB)
    if stage_n == 3:
        return run_stage_3(DB)
    raise HTTPException(status_code=404, detail=f"unknown demo stage {stage_n}{f'?step={step}' if step else ''}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bootstrap the database and start the two change stream watchers."""
    try:
        bootstrap(DB)
    except Exception as exc:  # pragma: no cover - depends on MongoDB deployment
        print(f"Notice: bootstrap failed: {exc}")

    try:
        start_gauge_watcher(DB)
        start_memory_watcher(DB)
    except Exception as exc:
        print(f"Notice: failed to start watchers: {exc}")

    yield

    stop_gauge_watcher()
    stop_memory_watcher()


def _sse_stream():
    """StreamingResponse body for GET /events?replay=1.

    Each SSE connection owns an asyncio.Queue; the publishers (the watcher
    threads) call loop.call_soon_threadsafe(queue.put_nowait, item), so the
    push is safe even though the queue is shared across threads.  First the
    replay buffer of the last 200 events, then a blocking get with a short
    timeout so the connection stays alive for new events.
    """
    loop = asyncio.get_running_loop()
    # Register the connection's queue as a subscriber before yielding
    

    q = subscribe()
    try:
        async def _gen():
            # Replay: last 200 audit events
            for ev in list(_REPLAY)[-200:]:
                yield f"data: {ev}\n\n"
            # Subscribe to live events
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {ev}\n\n"
    finally:
        unsubscribe(q)

    return EventSourceResponse(_gen(), media_type="text/event-stream")


def create_app() -> FastAPI:
    """Build the FastAPI application with CORS allowed for the Next.js dev server."""
    app = FastAPI(title="Metrologic", lifespan=lifespan)

    app.add_api_route("/events", _sse_stream, methods=["GET"], include_in_schema=False)

    # ---- demo stage runners (Section 10) ----
    app.add_api_route("/demo/stage/1", _demo_stage_runner, methods=["POST"], include_in_schema=False)
    app.add_api_route("/demo/stage/1?step=a", _demo_stage_runner, methods=["POST"], include_in_schema=False)
    app.add_api_route("/demo/stage/1?step=b", _demo_stage_runner, methods=["POST"], include_in_schema=False)
    app.add_api_route("/demo/stage/2", _demo_stage_runner, methods=["POST"], include_in_schema=False)
    app.add_api_route("/demo/stage/3", _demo_stage_runner, methods=["POST"], include_in_schema=False)
    app.add_api_route("/demo/stage/3?step=arm", _demo_stage_runner, methods=["POST"], include_in_schema=False)
    app.add_api_route("/demo/reset", _demo_stage_runner, methods=["POST"], include_in_schema=False)

    # ---- calibration event (Section 8) ----
    app.add_api_route("/calibration", _calibration_endpoint, methods=["POST"], include_in_schema=False)

    # ---- decisions review ----
    app.add_api_route("/decisions/review", _review_decisions, methods=["GET"], include_in_schema=False)

    # ---- provenance graph (GET /graph) ----
    app.add_api_route("/graph", _graph_elements, methods=["GET"], include_in_schema=False)

    # ---- memory detail + retrieval (not implemented 405) ----
    app.add_api_route("/memories/{memory_id}", _memory_detail, methods=["GET"], include_in_schema=False)
    app.add_api_route("/memories/search", _memories_search, methods=["GET"], include_in_schema=False)
    return app


def _calibration_endpoint(request: Dict[str, object]) -> Dict[str, object]:
    """Write an as-found calibration result to `gauges` and trigger the cascade."""
    gauge_id = str(request.get("gauge_id"))
    e = float(request.get("as_found_error_mm", 0.0))
    U = float(request.get("as_found_u_mm", 0.0))
    result = str(request.get("result", "OUT_OF_TOLERANCE"))
    direct = request.get("direct", False)
    if result.upper() != "OUT_OF_TOLERANCE":
        raise HTTPException(status_code=400, detail="only OUT_OF_TOLERANCE calibration events are supported")

    from backend.app.streams.gauge_watcher import post_calibration_event

    return post_calibration_event(
        db=DB,
        gauge_id=gauge_id,
        as_found_error_mm=e,
        as_found_u_mm=U,
        direct=bool(direct),
    )


def _review_decisions() -> List[Dict[str, object]]:
    """Return decisions with review_flag == true (Section 8, GET /decisions/review)."""
    docs = list(DB.decisions.find({"review_flag": True})).sort("created_at", -1)
    out: List[Dict[str, object]] = []
    for d in docs:
        out.append(
            {
                "_id": d["_id"],
                "query": d.get("query", ""),
                "plan_steps": d.get("plan_steps", []),
                "lessons_used": d.get("lessons_used", []),
                "part_serials": d.get("part_serials", []),
                "created_at": d.get("created_at"),
                "review_reason": d.get("review_reason"),
            }
        )
    return out


def _graph_elements() -> Dict[str, object]:
    """Cytoscape-format elements: gauge compound parents, measurements, lessons, decisions."""
    # Build the element set from the current database state.  In fixture mode
    # (offline, no MongoDB) the frontend uses its own fixtures; here we return
    # the live graph.  Pull the demo subset in one pass so the UI never waits.
    docs = list(DB.memories.find({"type": {"$in": ["lesson", "failed_attempt"]}}))
    doc_ids = {d["_id"] for d in docs}
    mem_map: Dict[str, Dict[str, object]] = {}
    for d in docs:
        mem_map[d["_id"]] = d

    # All demo-referenced measurements are the ones that appear in support_sets
    demo_mes: List[str] = []
    for sid in doc_ids:
        for s in mem_map[sid].get("support_sets", []):
            demo_mes += s
    demo_mes = list(dict.fromkeys(demo_mes))  # preserve order, dedupe
    mes_docs = list(DB.measurements.find({"_id": {"$in": demo_mes}}))
    mes_by_id: Dict[str, Dict[str, object]] = {m["_id"]: m for m in mes_docs}
    mes_by_gauge: Dict[str, List[str]] = {}
    for m in mes_by_id.values():
        mes_by_gauge.setdefault(m.get("gauge_id", "?"), []).append(m["_id"])

    # Gauge compound parents
    gauges = list(DB.gauges.find({}))
    nodes = []
    edges = []
    for g in gauges:
        nodes.append(
            {
                "data": {
                    "id": f"g:{g['_id']}",
                    "label": f"Gauge: {g['_id']} ({g.get('type', 'gauge')})",
                    "kind": "gauge",
                    "status": g.get("cal_status", "OK"),
                }
            }
        )

    # Measurement children for demo lessons
    seen_edges = set()
    for mid, m in mes_by_id.items():
        parent = m.get("parent", m.get("gauge_id", ""))
        nodes.append(
            {
                "data": {
                    "id": mid,
                    "label": f"{mid}: {m.get('value_mm', '?')} ({m.get('verdict', 'pass')})",
                    "kind": "measurement",
                    "verdict": m.get("verdict", "pass"),
                    "current_verdict": m.get("current_verdict", m.get("verdict", "pass")),
                    "parent": parent,
                }
            }
        )
        for sid in mem_map:
            for s in mem_map[sid].get("support_sets", []):
                if mid in s:
                    eid = f"e_{sid}_{mid}"
                    if eid not in seen_edges:
                        seen_edges.add(eid)
                        edges.append({"data": {"id": eid, "source": mid, "target": sid}})

    # Lesson nodes
    for sid, mem in mem_map.items():
        nodes.append(
            {
                "data": {
                    "id": sid,
                    "label": f"{sid}: {mem.get('title', mem.get('type', ''))}",
                    "kind": "lesson" if mem.get("type") == "lesson" else "failed_attempt",
                    "state": mem.get("validity_state", "PROVISIONAL"),
                    "flagged": mem.get("validity_state") == "HISTORICAL_ONLY",
                }
            }
        )

    # Decision nodes (flagged if review_flag)
    decisions = list(DB.decisions.find({}))
    for dec in decisions:
        nodes.append(
            {
                "data": {
                    "id": dec["_id"],
                    "label": f"{dec['_id']}: {dec.get('query', '')[:40]}",
                    "kind": "decision",
                    "flagged": dec.get("review_flag", False),
                }
            }
        )
        for lw in dec.get("lessons_used", []):
            eid = f"e_{lw}_{dec['_id']}"
            if eid not in seen_edges:
                seen_edges.add(eid)
                edges.append({"data": {"id": eid, "source": lw, "target": dec["_id"]}})

    return {"nodes": nodes, "edges": edges}


def _memory_detail(memory_id: str) -> Dict[str, object]:
    """Memory detail: the document plus an evidence chain (each measurement with recorded vs current verdict)."""
    rec = DB.memories.find_one({"_id": memory_id})
    if rec is None:
        raise HTTPException(status_code=404, detail="memory not found")

    evidence: List[Dict[str, object]] = []
    for s in rec.get("support_sets", []):
        for mid in s:
            mrec = DB.measurements.find_one({"_id": mid})
            if mrec is None:
                continue
            evidence.append(
                {
                    "measurement_id": mrec["_id"],
                    "gauge_id": mrec.get("gauge_id"),
                    "value_mm": mrec.get("value_mm"),
                    "verdict": mrec.get("verdict"),
                    "current_verdict": mrec.get("current_verdict"),
                    "u_mm": mrec.get("u_mm"),
                    "timestamp": mrec.get("timestamp"),
                    "feature": mrec.get("feature"),
                }
            )
    return {"memory": rec, "evidence": evidence}


def _memories_search() -> Dict[str, object]:
    raise HTTPException(status_code=405, detail="not implemented in this milestone")

"""API tests for backend/app/main.py (PLAN Section 8).

Uses FastAPI's TestClient with the in-memory MockDatabase: no MongoDB, no
API key, no network.  ``main._db`` is injected before the lifespan runs, so
``get_db_handle()`` never opens a real connection.
"""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from backend.app import events as event_bus
from backend.app import main
from backend.tests.demo_state import STAGE2_QUERY, STAGE2_SCOPE, seed_base_data
from backend.tests.mock_db import MockDatabase


@pytest.fixture()
def api(monkeypatch):
    db = seed_base_data(MockDatabase("test_api"))
    monkeypatch.setattr(main, "_db", db)
    with TestClient(main.app) as client:
        yield client, db


def _calibration_body() -> dict:
    return {
        "gauge_id": "BG-07",
        "as_found_error_mm": 0.006,
        "as_found_u_mm": 0.002,
        "result": "OUT_OF_TOLERANCE",
    }


def test_stage_flow_end_to_end_through_the_api(api):
    client, db = api

    # ---- Stage 1a: POST /ncr writes L1, L2, F1 as PROVISIONAL ----
    stage1a = client.post("/demo/stage/1?step=a")
    assert stage1a.status_code == 200
    body = stage1a.json()
    assert body["status"] == "success"
    assert body["memory_ids"] == ["L1", "L2", "F1"]
    assert {m["validity_state"] for m in body["memories"]} == {"PROVISIONAL"}
    assert db.memories.find_one({"_id": "L2"})["support_sets"] == [
        ["M9", "M10", "M11", "M12", "M13"]
    ]

    # ---- Stage 1b: POST /lessons/L1/corroborate promotes L1 ----
    stage1b = client.post("/demo/stage/1?step=b")
    assert stage1b.status_code == 200
    assert stage1b.json()["new_state"] == "ACTIVE"
    l1 = db.memories.find_one({"_id": "L1"})
    assert len(l1["support_sets"]) == 2
    assert l1["support_sets"][1] == ["M6", "M7", "M8"]

    # The public corroborate endpoint is the same path (see the dedicated test
    # below), so the demo triad is not changed before the Stage 2 plan.

    # ---- Stage 2: plan applies L1 + L2 and avoids F1, with a full trace ----
    stage2 = client.post("/demo/stage/2")
    assert stage2.status_code == 200
    stage2_body = stage2.json()
    assert stage2_body["decision_id"] == "D-STAGE2"
    assert stage2_body["lessons_used"][:3] == ["L2", "L1", "F1"]
    pairs = {(step["kind"], step["lesson_ids"][0]) for step in stage2_body["plan_steps"]}
    assert ("apply", "L1") in pairs
    assert ("apply", "L2") in pairs
    assert ("avoid", "F1") in pairs
    assert len(stage2_body["ranking_trace"]) == 5
    assert db.memories.find_one({"_id": "L2"})["used_by"] == ["D-STAGE2"]

    # A direct /recommend with persist=false writes nothing new.
    decision_count = len(db.decisions.find({}))
    preview = client.post(
        "/recommend",
        json={
            "query": STAGE2_QUERY,
            "scope": STAGE2_SCOPE,
            "persist": False,
        },
    )
    assert preview.status_code == 200
    assert preview.json()["decision_id"] is None
    assert len(db.decisions.find({})) == decision_count

    # ---- Stage 3: calibration cascade, L2 -> NEEDS_VERIFICATION, L1 stays ----
    calibration = client.post("/calibration?direct=1", json=_calibration_body())
    assert calibration.status_code == 200
    summary = calibration.json()["cascade_summary"]
    assert summary["measurements_recomputed"] >= 1
    assert db.memories.find_one({"_id": "L2"})["validity_state"] == "NEEDS_VERIFICATION"
    assert db.memories.find_one({"_id": "L1"})["validity_state"] == "ACTIVE"

    reask = client.post(
        "/recommend",
        json={"query": STAGE2_QUERY, "scope": STAGE2_SCOPE, "persist": True},
    )
    assert reask.status_code == 200
    reasked = reask.json()
    l2_step = next(s for s in reasked["plan_steps"] if s["lesson_ids"] == ["L2"])
    assert l2_step["kind"] == "verify"
    assert l2_step["verify_instrument"] == "CMM-02"
    l1_step = next(s for s in reasked["plan_steps"] if s["lesson_ids"] == ["L1"])
    assert l1_step["kind"] == "apply"

    # ---- Review list: the three decisions that used L2 before the cascade ----
    review = client.get("/decisions/review")
    assert review.status_code == 200
    review_ids = {decision["_id"] for decision in review.json()}
    assert review_ids == {"D1", "D2", "D-STAGE2"}
    assert all(decision["review_reason"] for decision in review.json())
    assert all("part_serials" in decision for decision in review.json())
    # Newest first: the Stage 2 decision was created after the seeded D1/D2.
    assert [decision["_id"] for decision in review.json()] == ["D-STAGE2", "D2", "D1"]

    # ---- Memory detail: evidence chain with gauge status ----
    detail = client.get("/memories/L1")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["_id"] == "L1"
    assert detail_body["validity_state"] == "ACTIVE"
    assert detail_body["history"]
    by_measurement = {
        item["measurement_id"]: item
        for item in detail_body["evidence"]
        if item.get("measurement_id")
    }
    assert by_measurement["M1"]["gauge_cal_status"] == "OUT_OF_TOLERANCE"
    assert by_measurement["M6"]["gauge_cal_status"] == "OK"
    assert by_measurement["M1"]["verdict"] == "pass"

    # ---- Search endpoint is not shadowed by /memories/{memory_id} ----
    search = client.get(
        "/memories/search",
        params={"q": STAGE2_QUERY, "material": "Inconel 718", "process": "finish boring"},
    )
    assert search.status_code == 200
    search_body = search.json()
    assert search_body["query"] == STAGE2_QUERY
    assert search_body["count"] == len(search_body["memories"])
    assert search_body["memories"][0]["_id"] == "L2"
    assert "L1" in {memory["_id"] for memory in search_body["memories"]}
    assert len(search_body["ranking_trace"]) == search_body["count"]

    # ---- Graph stays under the node budget ----
    graph = client.get("/graph")
    assert graph.status_code == 200
    graph_body = graph.json()
    nodes = graph_body["elements"]["nodes"]
    edges = graph_body["elements"]["edges"]
    assert 0 < len(nodes) < 40
    assert edges
    kinds = {node["data"]["kind"] for node in nodes}
    assert {"gauge", "measurement", "measurement_group", "lesson", "decision"} <= kinds
    assert any(node["data"].get("background") for node in nodes)


def test_corroborate_merges_same_gauge_evidence(api):
    """``POST /lessons/{id}/corroborate`` adds a BG-07 measurement to L2's set."""
    client, db = api
    client.post("/demo/stage/1?step=a")

    again = client.post(
        "/lessons/L2/corroborate",
        json={"job_id": "NCR-0500", "measurement_ids": ["M3"]},
    )
    assert again.status_code == 200
    assert again.json()["validity_state"] == "PROVISIONAL"
    assert again.json()["support_sets"] == [["M9", "M10", "M11", "M12", "M13", "M3"]]


def test_ncr_rejects_a_body_without_measurements(api):
    client, db = api
    before = {doc["_id"] for doc in db.memories.find({})}
    response = client.post("/ncr", json={"ncr_id": "NCR-0412", "measurements": []})
    assert response.status_code == 400
    assert "measurements" in response.json()["detail"]
    assert {doc["_id"] for doc in db.memories.find({})} == before
    assert db.memories.find_one({"_id": "L1"}) is None


def test_corroborate_unknown_lesson_returns_404(api):
    client, _ = api
    response = client.post(
        "/lessons/L404/corroborate",
        json={"job_id": "x", "measurement_ids": ["M1"]},
    )
    assert response.status_code == 404


def test_corroborate_without_measurement_ids_returns_400(api):
    client, db = api
    client.post("/demo/stage/1?step=a")
    response = client.post("/lessons/L1/corroborate", json={"job_id": "x"})
    assert response.status_code == 400
    assert db.memories.find_one({"_id": "L1"})["validity_state"] == "PROVISIONAL"


def test_recommend_requires_a_query(api):
    client, _ = api
    assert client.post("/recommend", json={"scope": STAGE2_SCOPE}).status_code == 400


def test_calibration_accepts_the_literal_direct_true_flag(api):
    """``ControlBar``/the script call ``POST /calibration?direct=true``."""
    client, db = api
    response = client.post("/calibration?direct=true", json=_calibration_body())
    assert response.status_code == 200
    assert response.json()["direct"] is True
    assert db.gauges.find_one({"_id": "BG-07"})["cal_status"] == "OUT_OF_TOLERANCE"


def test_calibration_unknown_gauge_returns_404(api):
    client, _ = api
    body = _calibration_body()
    body["gauge_id"] = "BG-99"
    assert client.post("/calibration?direct=1", json=body).status_code == 404


def test_events_replays_and_unsubscribes_in_generator(api):
    """The SSE generator owns subscribe/unsubscribe (fix 1 in main.py).

    TestClient cannot close an endless event stream cleanly, so the response
    body iterator is driven directly: one replay chunk, then ``aclose()``.
    """
    client, db = api
    event_bus.clear_events()
    event_bus.log_event(db, "api_test_event", cause="stream check")

    routes = {route.path for route in main.app.routes if hasattr(route, "path")}
    assert "/events" in routes

    async def read_one_then_close():
        response = main._sse_stream(replay=1)
        iterator = response.body_iterator
        assert event_bus._SUBSCRIBERS == []
        chunk = await iterator.__anext__()
        assert len(event_bus._SUBSCRIBERS) == 1
        await iterator.aclose()
        return chunk

    chunk = asyncio.run(read_one_then_close())

    assert isinstance(chunk, str)
    assert chunk.startswith("data: ")
    payload = json.loads(chunk[len("data: "):].strip())
    assert payload["event"] == "api_test_event"
    # The generator's finally block removed the connection's queue.
    assert event_bus._SUBSCRIBERS == []


def test_event_bus_broadcasts_to_active_subscribers(api):
    _, db = api
    event_bus.clear_events()

    async def scenario():
        queue = event_bus.subscribe_events()
        try:
            event_bus.log_event(db, "broadcast_check", details={"n": 1})
            return await asyncio.wait_for(queue.get(), timeout=2.0)
        finally:
            event_bus.unsubscribe_events(queue)

    received = asyncio.run(scenario())
    assert received["event"] == "broadcast_check"
    assert received["details"] == {"n": 1}
    assert event_bus._SUBSCRIBERS == []

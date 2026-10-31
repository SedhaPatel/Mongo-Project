"""Tests for memory/ranking.py and memory/retrieval.py (PLAN Section 7.5).

Deterministic and offline: the seed data comes from backend/seed, the lesson
embeddings come from the committed fixture, and no API server or LLM is used.
"""

import math
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.memory.ranking import (
    MW_WEIGHT,
    RECENCY_WEIGHT,
    SCOPE_WEIGHT,
    STATE_BIAS,
    memory_worth,
    rank_memories,
    recency_factor,
    scope_match,
    score_memory,
    traces,
)
from backend.app.memory.retrieval import cosine_similarity, retrieve_memories, search_memories
from backend.app.embeddings import get_embedding
from backend.tests.demo_state import STAGE2_QUERY, STAGE2_SCOPE, build_demo_db

NOW = datetime(2026, 10, 31, 9, 30, tzinfo=timezone.utc)


def test_state_bias_table():
    assert STATE_BIAS == {
        "ACTIVE": 0.12,
        "PROVISIONAL": 0.04,
        "NEEDS_VERIFICATION": -0.10,
        "HISTORICAL_ONLY": -0.22,
        "SUPERSEDED": -0.22,
    }


@pytest.mark.parametrize(
    "success,fail,expected",
    [(0, 0, 0.5), (1, 0, 2 / 3), (2, 0, 0.75), (0, 2, 0.25), (5, 1, 6 / 8)],
)
def test_memory_worth_formula(success, fail, expected):
    assert memory_worth(success, fail) == pytest.approx(expected)


def test_recency_formula_and_missing_date():
    created = datetime(2026, 10, 31, 9, 30, tzinfo=timezone.utc)
    assert recency_factor(created, now=NOW) == pytest.approx(1.0)
    ninety = NOW - timedelta(days=90)
    assert recency_factor(ninety, now=NOW) == pytest.approx(math.exp(-1.0))
    assert recency_factor(None, now=NOW) == 0.0
    # Future timestamps clamp rather than scoring above 1.
    assert recency_factor(NOW + timedelta(days=5), now=NOW) == pytest.approx(1.0)


def test_scope_match_is_share_of_supplied_fields():
    l1_scope = {
        "material": "Ti-6Al-4V",
        "process": "finish boring",
        "machine": "VF-4",
        "feature_class": "bore",
        "tolerance_band": "H7",
    }
    assert scope_match(STAGE2_SCOPE, l1_scope) == pytest.approx(4 / 5)
    assert scope_match(STAGE2_SCOPE, dict(l1_scope, material="Inconel 718")) == pytest.approx(1.0)
    assert scope_match({"material": "inconel 718"}, l1_scope) == pytest.approx(0.0)
    # No scope supplied: neutral term, not a crash.
    assert scope_match({}, l1_scope) == pytest.approx(1.0)
    assert scope_match(None, l1_scope) == pytest.approx(1.0)


def _memory(memory_id="L2", state="PROVISIONAL", vector_score=0.5, created=None):
    return {
        "_id": memory_id,
        "validity_state": state,
        "vector_score": vector_score,
        "mw_success": 2,
        "mw_fail": 0,
        "created_at": created or NOW,
        "scope": dict(STAGE2_SCOPE),
    }


def test_ranking_trace_contains_every_term():
    trace = score_memory(_memory(), query_scope=STAGE2_SCOPE, now=NOW)

    assert set(trace) == {
        "memory_id",
        "vector_score",
        "state",
        "state_bias",
        "mw",
        "mw_term",
        "recency",
        "recency_term",
        "scope_match",
        "scope_term",
        "final",
    }
    assert trace["vector_score"] == pytest.approx(0.5)
    assert trace["state"] == "PROVISIONAL"
    assert trace["state_bias"] == pytest.approx(0.04)
    assert trace["mw"] == pytest.approx(0.75)
    assert trace["mw_term"] == pytest.approx(MW_WEIGHT * 0.25)
    assert trace["recency"] == pytest.approx(1.0)
    assert trace["recency_term"] == pytest.approx(RECENCY_WEIGHT)
    assert trace["scope_match"] == pytest.approx(1.0)
    assert trace["scope_term"] == pytest.approx(SCOPE_WEIGHT)
    assert trace["final"] == pytest.approx(0.5 + 0.04 + 0.05 + 0.05 + 0.1)


def test_needs_verification_lowers_the_same_memory():
    active = score_memory(_memory(state="PROVISIONAL"), query_scope=STAGE2_SCOPE, now=NOW)
    weakened = score_memory(_memory(state="NEEDS_VERIFICATION"), query_scope=STAGE2_SCOPE, now=NOW)
    assert weakened["final"] == pytest.approx(active["final"] - 0.14)


def test_historical_and_superseded_get_the_same_bias():
    historical = score_memory(_memory(state="HISTORICAL_ONLY"), now=NOW)
    superseded = score_memory(_memory(state="SUPERSEDED"), now=NOW)
    assert historical["state_bias"] == superseded["state_bias"] == pytest.approx(-0.22)


def test_rank_is_deterministic_and_orders_by_final():
    db = build_demo_db()
    memories = db.memories.find({"type": {"$in": ["lesson", "failed_attempt"]}})
    query_vector = get_embedding(STAGE2_QUERY, input_type="query")
    for memory in memories:
        memory["vector_score"] = cosine_similarity(query_vector, memory["embedding"])

    ranked = rank_memories(memories, query_scope=STAGE2_SCOPE, now=NOW)

    ids = [row["trace"]["memory_id"] for row in ranked]
    assert ids[:2] == ["L2", "L1"]
    assert "F1" in ids

    finals = [row["trace"]["final"] for row in ranked]
    assert finals == sorted(finals, reverse=True)

    # Same input -> byte-identical traces, which is what the demo replay needs.
    again = rank_memories(memories, query_scope=STAGE2_SCOPE, now=NOW)
    assert traces(ranked) == traces(again)


def test_rank_ties_break_on_memory_id():
    rows = rank_memories([_memory("F1"), _memory("L1")], now=NOW)
    assert [row["trace"]["memory_id"] for row in rows] == ["F1", "L1"]


def test_retrieval_returns_trace_and_expected_demo_lessons():
    db = build_demo_db()

    ranked = retrieve_memories(
        db,
        query=STAGE2_QUERY,
        scope=STAGE2_SCOPE,
        rank_limit=5,
        now=NOW,
    )

    ids = [row["trace"]["memory_id"] for row in ranked]
    assert ids[:2] == ["L2", "L1"]
    assert "F1" in ids
    for row in ranked:
        assert row["trace"] == score_memory(row["memory"], STAGE2_SCOPE, NOW)


def test_retrieval_history_mode_can_see_historical_only():
    db = build_demo_db()
    db.memories.update_one({"_id": "L1"}, {"$set": {"validity_state": "HISTORICAL_ONLY"}})

    default_ids = [
        row["trace"]["memory_id"]
        for row in retrieve_memories(
            db, query=STAGE2_QUERY, scope=STAGE2_SCOPE, rank_limit=20, now=NOW
        )
    ]
    assert "L1" not in default_ids

    history_ids = [
        row["trace"]["memory_id"]
        for row in retrieve_memories(
            db,
            query=STAGE2_QUERY,
            scope=STAGE2_SCOPE,
            history=True,
            rank_limit=20,
            now=NOW,
        )
    ]
    assert "L1" in history_ids


def test_retrieval_scope_filter_is_optional():
    db = build_demo_db()

    unfiltered = retrieve_memories(db, query=STAGE2_QUERY, scope=STAGE2_SCOPE, now=NOW)
    assert any(row["memory"]["scope"]["material"] == "Ti-6Al-4V" for row in unfiltered)

    filtered = retrieve_memories(
        db,
        query=STAGE2_QUERY,
        scope=STAGE2_SCOPE,
        scope_filter=True,
        now=NOW,
    )
    assert filtered
    assert all(row["memory"]["scope"]["material"] == "Inconel 718" for row in filtered)


def test_search_memories_response_shape():
    db = build_demo_db()
    response = search_memories(db, query=STAGE2_QUERY, scope=STAGE2_SCOPE, now=NOW)

    assert response["query"] == STAGE2_QUERY
    assert response["count"] == len(response["memories"])
    assert len(response["ranking_trace"]) == response["count"]
    assert response["ranking_trace"][0]["memory_id"] == response["memories"][0]["_id"]

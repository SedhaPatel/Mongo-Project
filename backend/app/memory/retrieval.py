"""Filtered vector retrieval (PLAN Section 7.5).

Primary path: ``$vectorSearch`` on the ``memories_vec`` index with pre-filters
on workspace, type and validity state.  ``history=True`` drops the state
filter but keeps the same shape.

Fallback path: when the deployment has no Atlas Vector Search (a standalone
MongoDB, or the in-memory ``mock_db`` used by the tests), the same filter is
applied with ``find`` and cosine similarity is computed in Python.  The
fallback is selected only when the aggregation cannot produce a vector score,
so an Atlas deployment always uses the real index.
"""

import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from pymongo.database import Database

from backend.app.config import WORKSPACE
from backend.app.embeddings import get_embedding
from backend.app.memory.ranking import rank_memories, traces

DEFAULT_STATES: Sequence[str] = ("ACTIVE", "PROVISIONAL", "NEEDS_VERIFICATION")
DEFAULT_TYPES: Sequence[str] = ("lesson", "failed_attempt")
VECTOR_INDEX = "memories_vec"
NUM_CANDIDATES = 100


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _scalar_filter(
    workspace: str,
    types: Sequence[str],
    states: Sequence[str],
    history: bool,
    scope_filter: bool,
    scope: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """The pre-filters shared by $vectorSearch and the fallback path."""
    query: Dict[str, Any] = {
        "workspace": workspace,
        "type": {"$in": list(types)},
    }
    if not history:
        query["validity_state"] = {"$in": list(states)}
    if scope_filter and scope:
        for field in ("material", "process"):
            if scope.get(field):
                query[f"scope.{field}"] = scope[field]
    return query


def _matches_scope_filter(memory: Dict[str, Any], scope: Optional[Dict[str, Any]]) -> bool:
    if not scope:
        return True
    memory_scope = memory.get("scope") or {}
    for field in ("material", "process"):
        wanted = scope.get(field)
        if wanted and str(memory_scope.get(field, "")).strip().lower() != str(wanted).strip().lower():
            return False
    return True


def _atlas_vector_search(
    db: Database,
    query_vector: Sequence[float],
    query_filter: Dict[str, Any],
    limit: int,
) -> Optional[List[Dict[str, Any]]]:
    """Run $vectorSearch; return None when the deployment cannot serve it."""
    pipeline = [
        {
            "$vectorSearch": {
                "index": VECTOR_INDEX,
                "path": "embedding",
                "queryVector": list(query_vector),
                "numCandidates": max(NUM_CANDIDATES, limit * 10),
                "limit": limit,
                "filter": query_filter,
            }
        },
        {"$addFields": {"vector_score": {"$meta": "vectorSearchScore"}}},
    ]
    try:
        docs = list(db.memories.aggregate(pipeline))
    except Exception:
        return None
    if docs and any("vector_score" not in doc for doc in docs):
        # The in-memory mock ignores $vectorSearch; never trust that result.
        return None
    return docs


def _fallback_vector_search(
    db: Database,
    query_vector: Sequence[float],
    query_filter: Dict[str, Any],
    limit: int,
    scope_filter: bool = False,
    scope: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Cosine search over the same pre-filter, for non-Atlas deployments."""
    # Drop dotted scope keys: the in-memory mock cannot traverse them, and the
    # scope filter is applied explicitly below.
    scalar_filter = {
        key: value for key, value in query_filter.items() if not key.startswith("scope.")
    }
    docs = [doc for doc in db.memories.find(scalar_filter) if doc.get("embedding")]
    if scope_filter:
        docs = [doc for doc in docs if _matches_scope_filter(doc, scope)]
    for doc in docs:
        doc["vector_score"] = cosine_similarity(query_vector, doc["embedding"])
    docs.sort(key=lambda doc: (-doc["vector_score"], str(doc.get("_id"))))
    return docs[:limit]


def retrieve_memories(
    db: Database,
    *,
    query: str,
    scope: Optional[Dict[str, Any]] = None,
    workspace: str = WORKSPACE,
    history: bool = False,
    scope_filter: bool = False,
    limit: int = 10,
    rank_limit: int = 5,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Retrieve and rank memories for a query.

    Returns ``[{"memory": <doc>, "trace": <ranking_trace>}]`` (at most
    ``rank_limit`` rows).
    """
    query_vector = get_embedding(query, input_type="query")
    query_filter = _scalar_filter(
        workspace=workspace,
        types=DEFAULT_TYPES,
        states=DEFAULT_STATES,
        history=history,
        scope_filter=scope_filter,
        scope=scope,
    )

    candidates = _atlas_vector_search(db, query_vector, query_filter, limit)
    if candidates is None:
        candidates = _fallback_vector_search(
            db,
            query_vector,
            query_filter,
            limit,
            scope_filter=scope_filter,
            scope=scope,
        )
    elif scope_filter:
        # $vectorSearch already applied the filter; keep the contract explicit.
        candidates = [doc for doc in candidates if _matches_scope_filter(doc, scope)]

    ranked = rank_memories(candidates, query_scope=scope, now=now)
    return ranked[:rank_limit]


def search_memories(
    db: Database,
    *,
    query: str,
    scope: Optional[Dict[str, Any]] = None,
    workspace: str = WORKSPACE,
    history: bool = False,
    scope_filter: bool = False,
    limit: int = 10,
    rank_limit: int = 5,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """JSON shape for ``GET /memories/search``."""
    ranked = retrieve_memories(
        db,
        query=query,
        scope=scope,
        workspace=workspace,
        history=history,
        scope_filter=scope_filter,
        limit=limit,
        rank_limit=rank_limit,
        now=now,
    )
    return {
        "query": query,
        "scope": scope or {},
        "history": history,
        "count": len(ranked),
        "ranking_trace": traces(ranked),
        "memories": [row["memory"] for row in ranked],
    }

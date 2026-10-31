"""MongoDB connection, collection management, and idempotent bootstrap."""

import time
from typing import Optional
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.operations import SearchIndexModel

from backend.app.config import MONGODB_URI, MONGODB_DB

_client: Optional[MongoClient] = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI)
    return _client


def get_db(db_name: Optional[str] = None) -> Database:
    client = get_client()
    return client[db_name or MONGODB_DB]


def bootstrap(db: Optional[Database] = None) -> None:
    """Idempotently bootstrap collections, indexes, pre-images, and vector search."""
    if db is None:
        db = get_db()

    existing_collections = db.list_collection_names()

    # 1. Ensure required collections exist
    collections = ["memories", "measurements", "gauges", "decisions", "audit_log", "stream_state"]
    for coll_name in collections:
        if coll_name not in existing_collections:
            db.create_collection(coll_name)

    # 2. Pre-images on memories
    try:
        db.command({"collMod": "memories", "changeStreamPreAndPostImages": {"enabled": True}})
    except Exception as e:
        print(f"Notice: collMod for changeStreamPreAndPostImages on memories: {e}")

    # 3. TTL index on memories.expire_at
    mem_indexes = [idx["name"] for idx in db.memories.list_indexes()]
    if "expire_at_ttl" not in mem_indexes and not any("expire_at" in idx.get("key", {}) for idx in db.memories.list_indexes()):
        db.memories.create_index("expire_at", expireAfterSeconds=0, name="expire_at_ttl")

    # 4. Standard indexes
    db.measurements.create_index([("gauge_id", 1), ("timestamp", 1)], name="gauge_timestamp_idx")
    db.decisions.create_index([("lessons_used", 1)], name="lessons_used_idx")
    db.audit_log.create_index([("ts", 1)], name="ts_idx")

    # 5. Atlas Vector Search index on memories
    try:
        existing_search_indexes = list(db.memories.list_search_indexes())
        has_vec = any(idx.get("name") == "memories_vec" for idx in existing_search_indexes)
        if not has_vec:
            vec_model = SearchIndexModel(
                name="memories_vec",
                type="vectorSearch",
                definition={
                    "fields": [
                        {"type": "vector", "path": "embedding", "numDimensions": 1024, "similarity": "cosine"},
                        {"type": "filter", "path": "workspace"},
                        {"type": "filter", "path": "type"},
                        {"type": "filter", "path": "validity_state"},
                        {"type": "filter", "path": "scope.material"},
                        {"type": "filter", "path": "scope.process"},
                    ]
                },
            )
            db.memories.create_search_index(model=vec_model)
    except Exception as e:
        print(f"Notice: vector search index creation (may require Atlas or Atlas Local): {e}")


def wait_for_index_ready(db: Database, index_name: str = "memories_vec", timeout_s: int = 60) -> bool:
    """Poll search index until its queryable status is READY."""
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            indexes = list(db.memories.list_search_indexes())
            for idx in indexes:
                if idx.get("name") == index_name:
                    status = idx.get("status")
                    queryable = idx.get("queryable")
                    if status == "READY" or queryable is True:
                        return True
        except Exception:
            pass
        time.sleep(2)
    return False


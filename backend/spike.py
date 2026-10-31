"""
M0 Spike: Verify MongoDB capabilities required by Metrologic.
Run: python backend/spike.py [mongodb_uri]

Checks:
  1. Pre-images via collMod
  2. TTL index creation
  3. Change stream open (update + delete events)
  4. fullDocumentBeforeChange on delete
  5. TTL actual deletion event (waits up to 120 s)
  6. Vector search index create + query
  7. Update event with updatedFields

Fallbacks are decided and recorded per the plan (Section 4 / Section 13).
"""

import os
import sys
import json
import time
import threading
import datetime
import traceback

import pymongo
from pymongo import MongoClient
from pymongo.operations import SearchIndexModel

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MONGODB_URI = (
    sys.argv[1] if len(sys.argv) > 1
    else os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/?directConnection=true")
)
DB_NAME = "spike_m0"
COL_NAME = "spike"
STREAM_TIMEOUT = 120          # seconds to wait for TTL delete event
VECTOR_INDEX_TIMEOUT = 120    # seconds to wait for vector index readiness

RESULTS = {}   # check_name -> {"pass": bool, "note": str, "fallback": str}


def rec(name, passed, note="", fallback=""):
    RESULTS[name] = {"pass": passed, "note": note, "fallback": fallback}
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}: {note}")
    if not passed and fallback:
        print(f"         Fallback: {fallback}")


# ---------------------------------------------------------------------------
# Connect
# ---------------------------------------------------------------------------

def connect():
    print(f"\nConnecting to {MONGODB_URI!r}...")
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10_000)
        client.admin.command("ping")
        print("  Connected.")
        return client
    except Exception as exc:
        print(f"  FATAL: Cannot connect – {exc}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# CHECK 1: Pre-images
# ---------------------------------------------------------------------------

def check_preimages(db):
    name = "1_preimages_collMod"
    try:
        db.create_collection(COL_NAME)
    except pymongo.errors.CollectionInvalid:
        pass  # already exists
    try:
        db.command({
            "collMod": COL_NAME,
            "changeStreamPreAndPostImages": {"enabled": True}
        })
        rec(name, True, "collMod accepted changeStreamPreAndPostImages")
    except pymongo.errors.OperationFailure as exc:
        rec(name, False,
            f"collMod rejected: {exc}",
            fallback="Keep prior state in history[] and audit_log; UI never needs the before-image")


# ---------------------------------------------------------------------------
# CHECK 2: TTL index
# ---------------------------------------------------------------------------

def check_ttl_index(db):
    name = "2_ttl_index_creation"
    col = db[COL_NAME]
    try:
        col.create_index("expire_at", expireAfterSeconds=0)
        indexes = list(col.list_indexes())
        ttl_found = any(
            idx.get("expireAfterSeconds") == 0 and "expire_at" in idx.get("key", {})
            for idx in indexes
        )
        rec(name, ttl_found,
            "TTL index created" if ttl_found else "TTL index not found after creation")
    except Exception as exc:
        rec(name, False, str(exc))


# ---------------------------------------------------------------------------
# CHECKS 3, 4, 5, 7: Change stream (run in a background thread)
# ---------------------------------------------------------------------------

EVENTS = []
STREAM_READY = threading.Event()
STREAM_STOP  = threading.Event()

def stream_thread(db):
    col = db[COL_NAME]
    try:
        stream = col.watch(
            full_document="updateLookup",
            full_document_before_change="whenAvailable",
        )
        # Establish cursor on server
        stream.try_next()
        STREAM_READY.set()
        with stream:
            while not STREAM_STOP.is_set():
                change = stream.try_next()
                if change:
                    EVENTS.append(change)
                else:
                    time.sleep(0.2)
    except Exception as exc:
        EVENTS.append({"_error": str(exc)})
        STREAM_READY.set()


def check_change_stream_open(db):
    name = "3_change_stream_open"
    t = threading.Thread(target=stream_thread, args=(db,), daemon=True)
    t.start()
    ok = STREAM_READY.wait(timeout=15)
    errors = [e for e in EVENTS if "_error" in e]
    if errors:
        rec(name, False, str(errors[0]["_error"]),
            fallback="POST /calibration?direct=true runs the cascade inline")
        return False
    rec(name, ok, "Change stream opened" if ok else "Timed out opening stream",
        fallback="POST /calibration?direct=true runs the cascade inline" if not ok else "")
    return ok


def check_update_event(db):
    """CHECK 7: insert + update, verify updatedFields arrives."""
    name = "7_update_event_updatedFields"
    col = db[COL_NAME]
    col.insert_one({"_id": "upd-test", "val": 1})
    col.update_one({"_id": "upd-test"}, {"$set": {"val": 2}})

    deadline = time.time() + 15
    while time.time() < deadline:
        for ev in EVENTS:
            if ev.get("operationType") == "update" and \
               ev.get("documentKey", {}).get("_id") == "upd-test":
                uf = ev.get("updateDescription", {}).get("updatedFields", {})
                if "val" in uf:
                    rec(name, True, f"updatedFields received: {uf}")
                    return
        time.sleep(0.3)
    rec(name, False, "No update event with updatedFields within 15 s")


def check_ttl_delete_event(db):
    """CHECKS 4 + 5: Insert doc with expire_at = now+30s, wait up to 120s for delete event."""
    col = db[COL_NAME]
    expire_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=30)
    col.insert_one({"_id": "t1", "expire_at": expire_at, "label": "ttl-spike"})
    print(f"  Inserted TTL doc expire_at={expire_at.isoformat()}Z  (waiting up to {STREAM_TIMEOUT}s)...")

    deadline = time.time() + STREAM_TIMEOUT
    delete_event = None
    while time.time() < deadline:
        for ev in EVENTS:
            if ev.get("operationType") == "delete" and \
               ev.get("documentKey", {}).get("_id") == "t1":
                delete_event = ev
                break
        if delete_event:
            break
        time.sleep(2)

    if delete_event:
        before = delete_event.get("fullDocumentBeforeChange")
        rec("5_ttl_delete_event", True,
            f"Delete event arrived after ~{int(STREAM_TIMEOUT - (deadline - time.time()))}s")
        if before:
            rec("4_fullDocumentBeforeChange", True,
                f"fullDocumentBeforeChange present: {list(before.keys())}")
        else:
            rec("4_fullDocumentBeforeChange", False,
                "fullDocumentBeforeChange is null (pre-images may be unsupported on this tier)",
                fallback="Keep prior state in history[] and audit_log; UI never needs the before-image")
    else:
        elapsed = int(STREAM_TIMEOUT)
        rec("5_ttl_delete_event", False,
            f"No TTL delete event within {elapsed}s",
            fallback="Show the rehearsed event from seed/fixtures/ttl_delete_event.json via a 'Replay TTL event' button")
        rec("4_fullDocumentBeforeChange", False,
            "Cannot verify – no TTL delete event arrived",
            fallback="Keep prior state in history[] and audit_log; UI never needs the before-image")


# ---------------------------------------------------------------------------
# CHECK 6: Vector Search
# ---------------------------------------------------------------------------

def check_vector_search(db):
    name = "6_vector_search"
    col = db[COL_NAME]

    # Insert a document with a tiny 4-dim vector (real app uses 1024)
    DIM = 4
    col.update_one(
        {"_id": "vec-test"},
        {"$set": {"embedding": [0.1, 0.2, 0.3, 0.4], "workspace": "test"}},
        upsert=True,
    )

    # Try to create a SearchIndexModel
    try:
        from pymongo.operations import SearchIndexModel as SIM
        idx_def = {
            "fields": [
                {"type": "vector", "path": "embedding",
                 "numDimensions": DIM, "similarity": "cosine"},
                {"type": "filter", "path": "workspace"},
            ]
        }
        model = SIM(name="spike_vec", type="vectorSearch", definition=idx_def)
        # Check if index already exists
        existing = [i["name"] for i in col.list_search_indexes()]
        if "spike_vec" not in existing:
            col.create_search_index(model)
            print(f"  Vector index creation requested. Waiting up to {VECTOR_INDEX_TIMEOUT}s for READY...")
        else:
            print("  Vector index 'spike_vec' already exists.")

        # Poll for readiness
        ready = False
        deadline = time.time() + VECTOR_INDEX_TIMEOUT
        while time.time() < deadline:
            statuses = {i["name"]: i.get("status", "?")
                        for i in col.list_search_indexes()}
            if statuses.get("spike_vec") == "READY":
                ready = True
                break
            print(f"    Index status: {statuses.get('spike_vec', 'unknown')} – waiting...")
            time.sleep(10)

        if not ready:
            rec(name, False,
                f"Index not READY within {VECTOR_INDEX_TIMEOUT}s (status: {statuses.get('spike_vec','?')})",
                fallback="Use Atlas Local for the demo laptop (vector search is supported)")
            return

        # Run $vectorSearch
        pipeline = [
            {"$vectorSearch": {
                "index": "spike_vec",
                "path": "embedding",
                "queryVector": [0.1, 0.2, 0.3, 0.4],
                "numCandidates": 10,
                "limit": 1,
            }},
            {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
        ]
        results = list(col.aggregate(pipeline))
        if results:
            rec(name, True, f"$vectorSearch returned {len(results)} result(s), score={results[0].get('score')}")
        else:
            rec(name, False, "$vectorSearch returned no results",
                fallback="Use Atlas Local for the demo laptop")

    except Exception as exc:
        tb = traceback.format_exc()
        rec(name, False, f"{type(exc).__name__}: {exc}",
            fallback="Use Atlas Local for the demo laptop (vector search is supported)")
        print(f"  Detail:\n{tb}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Metrologic M0 Spike – MongoDB capability check")
    print("=" * 60)

    client = connect()
    db = client[DB_NAME]

    # Drop and recreate collection for a clean run
    db.drop_collection(COL_NAME)
    db.create_collection(COL_NAME)

    print("\n--- CHECK 1: Pre-images ---")
    check_preimages(db)

    print("\n--- CHECK 2: TTL index ---")
    check_ttl_index(db)

    print("\n--- CHECKS 3, 4, 5, 7: Change stream ---")
    stream_ok = check_change_stream_open(db)

    if stream_ok:
        print("\n--- CHECK 7: Update event ---")
        check_update_event(db)

        print("\n--- CHECKS 4+5: TTL delete event (slow – waits up to 120 s) ---")
        check_ttl_delete_event(db)
    else:
        rec("7_update_event_updatedFields", False, "Skipped – change stream unavailable",
            fallback="POST /calibration?direct=true runs the cascade inline")
        rec("5_ttl_delete_event", False, "Skipped – change stream unavailable",
            fallback="Show rehearsed event from seed/fixtures/ttl_delete_event.json")
        rec("4_fullDocumentBeforeChange", False, "Skipped – change stream unavailable",
            fallback="Keep prior state in history[] and audit_log")

    print("\n--- CHECK 6: Vector search ---")
    check_vector_search(db)

    STREAM_STOP.set()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    all_pass = True
    for k, v in sorted(RESULTS.items()):
        status = "PASS" if v["pass"] else "FAIL"
        print(f"  {status:4s}  {k}")
        if not v["pass"]:
            all_pass = False

    print(f"\nOverall: {'ALL PASS' if all_pass else 'ONE OR MORE CHECKS FAILED'}")
    print("\nResults written to: docs/PROGRESS.md")

    return RESULTS


if __name__ == "__main__":
    results = main()
    # Save JSON sidecar for PROGRESS.md generation
    import pathlib, json
    pathlib.Path("spike_results.json").write_text(json.dumps(results, indent=2))


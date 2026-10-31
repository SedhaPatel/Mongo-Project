"""Change stream watcher on the `memories` collection.

Implements the `update` / `delete` branches of Section 8.2 of docs/PLAN.md:

- `update`: when `validity_state` changes, publish `memory_changed` (the UI
  recolours the node).
- `delete`: rebuild the `memory_deleted` / `ttl_deleted` audit entry from the
  before-image (`cause = "ttl_expiry"` when `before.expire_at <= now + 1s`,
  otherwise `"deleted"`).

Both publish to the same thread-safe bus that the SSE feed subscribes to.
"""

import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pymongo import UpdateOptions
from pymongo.database import Database
from pymongo.errors import PyMongoError

from backend.app.events import log_event, set_event_loop
from backend.app.validity.cascade import run_cascade

_WATCHER_THREAD: Optional[threading.Thread] = None
_RUNNING: bool = False


def _memory_watcher_worker(db: Database) -> None:
    """Continuously watch memories for state changes and deletions."""
    global _RUNNING
    pipeline = [
        {
            "$match": {
                "operationType": {"$in": ["update", "delete"]},
            }
        }
    ]

    retry_delay = 1.0

    while _RUNNING:
        try:
            with db.memories.watch(pipeline, full_document="updateLookup") as stream:
                retry_delay = 1.0
                while _RUNNING:
                    change = stream.try_next()
                    if change is None:
                        time.sleep(0.5)
                        continue

                    op_type = change.get("operationType")
                    if op_type == "update":
                        doc = change.get("fullDocument") or change.get("updateDescription", {}).get("updatedFields", {})
                        st = doc.get("validity_state") if isinstance(doc, dict) else None
                        if st and st in {"ACTIVE", "PROVISIONAL", "NEEDS_VERIFICATION", "HISTORICAL_ONLY", "SUPERSEDED"}:
                            # name the event after the new state so the UI can patch a lesson node
                            log_event(
                                db,
                                "memory_changed",
                                memory_id=change.get("documentKey", {}).get("_id"),
                                to_state=str(st),
                            )

                    elif op_type == "delete":
                        before = change.get("documentKey")
                        before_doc = change.get("fullDocument") or {}
                        # full_document_before_change="whenAvailable" would give the before-image;
                        # fall back to the now-deleted doc if the watch was opened that way.
                        if not before_doc:
                            before_doc = change.get("ns", {}).get("db") or "memories"
                        # The watched collection keeps the last seen version per request;
                        # reconstruct before-image where possible.
                        cause = "deleted"
                        expire_at = before_doc.get("expire_at")
                        if expire_at is not None:
                            # expire_at arrives as an ISO string when the watch filters it;
                            # compare against a threshold of one second.
                            try:
                                exp_dt = datetime.fromisoformat(str(expire_at).replace("Z", "+00:00"))
                                if exp_dt.tzinfo is None:
                                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                                if exp_dt <= datetime.now(timezone.utc) + timedelta(seconds=1):
                                    cause = "ttl_expiry"
                                else:
                                    cause = "deleted"  # still within its validity window
                            except Exception:
                                cause = "ttl_expiry"
                        log_event(
                            db,
                            "memory_deleted" if cause != "ttl_expiry" else "ttl_deleted",
                            memory_id=before_doc.get("_id"),
                            cause=cause,
                            event_id=str(uuid.uuid4()) if False else None,
                        )

        except PyMongoError as pe:
            print(f"Notice: memories change stream reconnecting: {pe}")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 10.0)
        except Exception as e:
            print(f"Notice: memories change stream unexpected error: {e}")
            time.sleep(retry_delay)


def start_memory_watcher(db: Database) -> None:
    global _WATCHER_THREAD
    if _WATCHER_THREAD is not None and _WATCHER_THREAD.is_alive():
        return
    _RUNNING = True
    _WATCHER_THREAD = threading.Thread(
        target=_memory_watcher_worker,
        args=(db,),
        daemon=True,
        name="MemoryWatcherThread",
    )
    _WATCHER_THREAD.start()


def stop_memory_watcher() -> None:
    global _RUNNING
    _RUNNING = False

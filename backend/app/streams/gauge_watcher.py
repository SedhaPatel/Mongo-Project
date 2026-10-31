"""MongoDB Change Stream watcher on gauges collection.

Implements Section 8.2 of docs/PLAN.md:
- Watches updates to gauges.cal_status using change streams.
- Triggers run_cascade() when cal_status becomes OUT_OF_TOLERANCE.
- Stores resume tokens in stream_state collection for fault tolerance.
- Supports direct inline execution fallback (POST /calibration?direct=true).
"""

import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pymongo.database import Database
from pymongo.errors import PyMongoError

from backend.app.events import log_event
from backend.app.validity.cascade import run_cascade

_WATCHER_THREAD: Optional[threading.Thread] = None
_RUNNING: bool = False


def load_resume_token(db: Database) -> Optional[Dict[str, Any]]:
    """Loads the stored change stream resume token from stream_state."""
    try:
        doc = db.stream_state.find_one({"_id": "gauge_watcher"})
        if doc and "resume_token" in doc:
            return doc["resume_token"]
    except Exception as e:
        print(f"Notice: Failed to load resume token: {e}")
    return None


def save_resume_token(db: Database, token: Dict[str, Any]) -> None:
    """Persists change stream resume token to stream_state collection."""
    try:
        db.stream_state.update_one(
            {"_id": "gauge_watcher"},
            {
                "$set": {
                    "resume_token": token,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
    except Exception as e:
        print(f"Notice: Failed to save resume token: {e}")


def post_calibration_event(
    db: Database,
    gauge_id: str,
    as_found_error_mm: float,
    as_found_u_mm: float,
    direct: bool = False,
    event_id: Optional[str] = None,
    event_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Writes an out-of-tolerance calibration check to the gauges collection.

    If direct=True, executes the calibration cascade inline rather than waiting
    for the change stream worker.
    """
    ev_id = event_id or f"ev-{gauge_id.lower()}-{uuid.uuid4().hex[:8]}"
    ev_time = event_time or datetime.now(timezone.utc)

    # 1. Update gauge document in database
    update_res = db.gauges.update_one(
        {"_id": gauge_id},
        {
            "$set": {
                "cal_status": "OUT_OF_TOLERANCE",
                "as_found_error_mm": as_found_error_mm,
                "as_found_u_mm": as_found_u_mm,
                "event_id": ev_id,
                "event_time": ev_time,
            }
        },
    )

    # 2. Log event to audit log and event bus
    log_event(
        db,
        "calibration_posted",
        gauge_id=gauge_id,
        event_id=ev_id,
        as_found_error_mm=as_found_error_mm,
        as_found_u_mm=as_found_u_mm,
        details={"direct": direct, "matched_count": update_res.matched_count},
    )

    # 3. Direct execution fallback
    cascade_summary = None
    if direct:
        cascade_summary = run_cascade(
            db=db,
            gauge_id=gauge_id,
            event_id=ev_id,
            e=as_found_error_mm,
            U=as_found_u_mm,
            event_time=ev_time,
        )

    return {
        "status": "success",
        "event_id": ev_id,
        "gauge_id": gauge_id,
        "as_found_error_mm": as_found_error_mm,
        "as_found_u_mm": as_found_u_mm,
        "direct": direct,
        "cascade_summary": cascade_summary,
    }


def _gauge_watcher_worker(db: Database) -> None:
    """Background worker monitoring gauge change streams."""
    global _RUNNING
    pipeline = [
        {
            "$match": {
                "operationType": "update",
                "updateDescription.updatedFields.cal_status": {"$exists": True},
            }
        }
    ]

    retry_delay = 1.0

    while _RUNNING:
        try:
            saved_token = load_resume_token(db)
            watch_kwargs: Dict[str, Any] = {
                "full_document": "updateLookup",
            }
            if saved_token:
                watch_kwargs["resume_after"] = saved_token

            with db.gauges.watch(pipeline, **watch_kwargs) as stream:
                retry_delay = 1.0
                while _RUNNING:
                    change = stream.try_next()
                    if change is None:
                        time.sleep(0.5)
                        continue

                    gauge = change.get("fullDocument")
                    if gauge and gauge.get("cal_status") == "OUT_OF_TOLERANCE":
                        ev_id = gauge.get("event_id") or f"ev-{gauge['_id'].lower()}-stream"
                        run_cascade(
                            db=db,
                            gauge_id=gauge["_id"],
                            event_id=ev_id,
                            e=gauge.get("as_found_error_mm", 0.0),
                            U=gauge.get("as_found_u_mm", 0.0),
                            event_time=gauge.get("event_time"),
                        )

                    if stream.resume_token:
                        save_resume_token(db, stream.resume_token)

        except PyMongoError as pe:
            print(f"Notice: Gauge change stream reconnecting after error: {pe}")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 10.0)
        except Exception as e:
            print(f"Notice: Gauge change stream unexpected error: {e}")
            time.sleep(retry_delay)


def start_gauge_watcher(db: Database) -> None:
    """Starts the gauge change stream watcher in a daemon thread."""
    global _WATCHER_THREAD, _RUNNING
    if _WATCHER_THREAD is not None and _WATCHER_THREAD.is_alive():
        return
    _RUNNING = True
    _WATCHER_THREAD = threading.Thread(
        target=_gauge_watcher_worker,
        args=(db,),
        daemon=True,
        name="GaugeWatcherThread",
    )
    _WATCHER_THREAD.start()


def stop_gauge_watcher() -> None:
    """Stops the gauge change stream watcher."""
    global _RUNNING
    _RUNNING = False


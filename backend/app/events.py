"""Thread-safe event bus and audit logger for Metrologic.

Implements Section 7.1 of docs/PLAN.md:
- log_event(db, event, **fields): inserts into audit_log and broadcasts to listeners.
- Bounded in-memory replay buffer (200 events) for UI catch-up on connect.
- Thread-safe queues for Server-Sent Events (SSE).
"""

import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pymongo.database import Database

# In-memory circular replay buffer (latest 200 events)
_REPLAY_BUFFER: deque = deque(maxlen=200)
_SUBSCRIBERS: List[asyncio.Queue] = []
_EVENT_LOOP: Optional[asyncio.AbstractEventLoop] = None


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _EVENT_LOOP
    _EVENT_LOOP = loop


def get_replay_events(limit: int = 200) -> List[Dict[str, Any]]:
    """Returns the most recent events from the in-memory circular buffer."""
    events = list(_REPLAY_BUFFER)
    return events[-limit:]


def clear_events() -> None:
    """Clears the replay buffer (called by ``POST /demo/reset``)."""
    _REPLAY_BUFFER.clear()


def subscribe_events() -> asyncio.Queue:
    """Subscribes an SSE connection queue."""
    q: asyncio.Queue = asyncio.Queue()
    _SUBSCRIBERS.append(q)
    return q


def unsubscribe_events(q: asyncio.Queue) -> None:
    """Unsubscribes an SSE connection queue."""
    if q in _SUBSCRIBERS:
        _SUBSCRIBERS.remove(q)


def log_event(db: Optional[Database], event: str, **fields: Any) -> Dict[str, Any]:
    """Records an event into audit_log and broadcasts it to all active event streams."""
    ts = fields.pop("ts", None) or datetime.now(timezone.utc)
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            pass

    event_doc: Dict[str, Any] = {
        "ts": ts,
        "event": event,
        **fields,
    }

    # 1. Insert into MongoDB audit_log if db is provided
    if db is not None:
        try:
            db.audit_log.insert_one(dict(event_doc))
        except Exception as e:
            print(f"Warning: Failed to insert audit_log entry: {e}")

    # Format event for listeners (serialize datetime to ISO string)
    broadcast_doc = dict(event_doc)
    if isinstance(broadcast_doc.get("ts"), datetime):
        broadcast_doc["ts"] = broadcast_doc["ts"].isoformat()

    # 2. Append to circular replay buffer
    _REPLAY_BUFFER.append(broadcast_doc)

    # 3. Broadcast to active SSE listeners thread-safely
    for sub in list(_SUBSCRIBERS):
        try:
            if _EVENT_LOOP and _EVENT_LOOP.is_running():
                _EVENT_LOOP.call_soon_threadsafe(sub.put_nowait, broadcast_doc)
            else:
                sub.put_nowait(broadcast_doc)
        except Exception:
            pass

    return broadcast_doc


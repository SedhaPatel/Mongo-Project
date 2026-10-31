"""Server-Sent Events (SSE) feed for the Metrologic frontend.

Exposes GET /events?replay=1, which first replays the last 200 audit_log
entries (bounded circular buffer) and then streams live `audit_log`
entries published by the change stream watchers.  Each connection owns an
asyncio.Queue; publishers (in watcher threads) drive the queue with
loop.call_soon_threadsafe so there is no lock contention on the hot path.
"""

import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import Deque, List, Optional

from pymongo.database import Database

# Bounded circular replay buffer (latest 200 events) - mirrors the in-process
# bus so a brand-new UI connection can catch up immediately.
_REPLAY: Deque[dict] = deque(maxlen=200)
_SUBSCRIBERS: List[asyncio.Queue] = []
_EVENT_LOOP: Optional[asyncio.AbstractEventLoop] = None


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _EVENT_LOOP
    _EVENT_LOOP = loop


def subscribe() -> asyncio.Queue:
    q = asyncio.Queue()
    _SUBSCRIBERS.append(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    if q in _SUBSCRIBERS:
        _SUBSCRIBERS.remove(q)


def push(event: dict) -> None:
    """Publish an audit event to every live SSE listener, thread-safely."""
    _REPLAY.append(event)
    if _EVENT_LOOP and _EVENT_LOOP.is_running():
        _EVENT_LOOP.call_soon_threadsafe(_broadcast, event)
    else:
        _broadcast(event)


def _broadcast(event: dict) -> None:
    for q in list(_SUBSCRIBERS):
        try:
            q.put_nowait(event)
        except Exception:
            pass


def get_replay(limit: int = 200) -> List[dict]:
    return list(_REPLAY)[-limit:]

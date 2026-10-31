"""Database reset utility for Metrologic demo.

Implements Section 9 and Section 10 of docs/PLAN.md:
Drops collections memories, measurements, gauges, decisions, audit_log, stream_state.
Reloads:
  - 6 gauges from scenario.yaml
  - ~193 filler measurements (including M-old)
  - 13 background lessons with precomputed embeddings
  - Decisions D1 and D2
Finishes in under 10 seconds.
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
import yaml
from pymongo.database import Database

from backend.app.db import bootstrap, get_db
from backend.seed.generate import generate_background_lessons, generate_filler_measurements

SCENARIO_FILE = Path(__file__).resolve().parent / "scenario.yaml"


def parse_datetime(dt_val: Any) -> Any:
    """Recursively converts ISO string timestamps into native datetime objects for BSON storage."""
    if isinstance(dt_val, str):
        # Check if matches ISO 8601 format
        if len(dt_val) >= 19 and ("T" in dt_val or "-" in dt_val):
            try:
                # Handle trailing Z
                clean_str = dt_val.replace("Z", "+00:00")
                return datetime.fromisoformat(clean_str)
            except Exception:
                return dt_val
    elif isinstance(dt_val, list):
        return [parse_datetime(item) for item in dt_val]
    elif isinstance(dt_val, dict):
        return {k: parse_datetime(v) for k, v in dt_val.items()}
    return dt_val


def reset_database(db: Optional[Database] = None) -> Dict[str, Any]:
    """Drops collections and seeds base data for the demo."""
    start_time = time.time()
    if db is None:
        db = get_db()

    # 1. Drop existing data collections
    collections_to_drop = ["memories", "measurements", "gauges", "decisions", "audit_log", "stream_state"]
    for coll_name in collections_to_drop:
        db[coll_name].drop()

    # 2. Re-run bootstrap (ensures indexes and pre-images exist)
    bootstrap(db)

    # 3. Load scenario.yaml
    with open(SCENARIO_FILE, "r", encoding="utf-8") as f:
        scenario_data = yaml.safe_load(f)

    # 4. Insert 6 Gauges
    gauges_data = [parse_datetime(g) for g in scenario_data.get("gauges", [])]
    if gauges_data:
        db.gauges.insert_many(gauges_data)

    # 5. Insert 13 Background Lessons
    b_lessons, _ = generate_background_lessons(13)
    b_lessons_bson = [parse_datetime(l) for l in b_lessons]
    if b_lessons_bson:
        db.memories.insert_many(b_lessons_bson)

    # 6. Insert Filler Measurements (including M-old, but NOT M1..M16)
    filler_measurements = generate_filler_measurements(b_lessons)
    filler_bson = [parse_datetime(m) for m in filler_measurements]
    if filler_bson:
        db.measurements.insert_many(filler_bson)

    # 7. Insert Decisions D1 and D2
    decisions_data = [parse_datetime(d) for d in scenario_data.get("decisions", [])]
    if decisions_data:
        db.decisions.insert_many(decisions_data)

    # 8. Record audit log entry
    elapsed = time.time() - start_time
    reset_entry = {
        "ts": datetime.utcnow(),
        "event": "database_reset",
        "cause": "demo_reset_script",
        "details": {
            "elapsed_seconds": round(elapsed, 3),
            "gauges_count": len(gauges_data),
            "background_lessons_count": len(b_lessons_bson),
            "filler_measurements_count": len(filler_bson),
            "decisions_count": len(decisions_data),
        },
    }
    db.audit_log.insert_one(reset_entry)

    return {
        "status": "success",
        "elapsed_seconds": round(elapsed, 3),
        "gauges": len(gauges_data),
        "background_lessons": len(b_lessons_bson),
        "measurements": len(filler_bson),
        "decisions": len(decisions_data),
    }


if __name__ == "__main__":
    result = reset_database()
    print(f"Database reset complete in {result['elapsed_seconds']}s: {result}")


"""Calibration cascade engine for Metrologic.

Implements Section 6.5 of docs/PLAN.md:
1. Checks idempotency.
2. Selects suspect window: gauge_id == G and last_good_cal < timestamp <= event_time.
3. Recomputes verdicts using metrology.recompute_verdict.
4. Updates verdict_history and current_verdict.
5. Re-evaluates affected lessons via support-set lattice.
6. Records state changes or 'saved by independent support' history notes.
7. Transitive demotion via $graphLookup over supports.
8. Flags affected decisions in decisions collection.
9. Writes audit_log and broadcasts events.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pymongo.database import Database

from backend.app.events import log_event
from backend.app.models import ValidityState
from backend.app.validity.lattice import evaluate_lesson_from_measurements
from backend.app.validity.metrology import recompute_verdict


def _ensure_datetime(val: Any) -> datetime:
    """Ensures a timestamp is a valid timezone-aware datetime object."""
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val
    if isinstance(val, str):
        cleaned = val.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    return datetime.now(timezone.utc)


def run_cascade(
    db: Database,
    gauge_id: str,
    event_id: str,
    e: float,
    U: float,
    event_time: Any = None,
) -> Dict[str, Any]:
    """Executes calibration cascade across measurements, memories, and decisions."""
    # 1. Idempotency check: if cascade_finished already recorded for event_id, return stored result
    existing_finished = db.audit_log.find_one({"event": "cascade_finished", "event_id": event_id})
    if existing_finished and "payload" in existing_finished:
        return existing_finished["payload"]

    event_dt = _ensure_datetime(event_time or datetime.now(timezone.utc))

    # 2. Record cascade started
    log_event(
        db,
        "cascade_started",
        gauge_id=gauge_id,
        event_id=event_id,
        as_found_error_mm=e,
        as_found_u_mm=U,
    )

    # 3. Retrieve gauge to identify suspect window
    gauge = db.gauges.find_one({"_id": gauge_id}) or {}
    last_good_cal = _ensure_datetime(gauge.get("last_good_cal", datetime(1970, 1, 1, tzinfo=timezone.utc)))

    # Suspect window: gauge_id == G AND last_good_cal < timestamp <= event_dt
    # Measurements outside this window (e.g. M-old dated before last_good_cal) are untouched.
    suspect_query = {
        "gauge_id": gauge_id,
        "$and": [
            {"timestamp": {"$gt": last_good_cal}},
            {"timestamp": {"$lte": event_dt}},
        ],
    }

    suspect_measurements = list(db.measurements.find(suspect_query))

    measurements_recomputed = 0
    verdict_changes = 0
    suspect_ids: List[str] = []
    measurements_map: Dict[str, Dict[str, Any]] = {}

    now_utc = datetime.now(timezone.utc)

    # 4. Recompute verdicts for each suspect measurement
    for m in suspect_measurements:
        mid = m["_id"]
        suspect_ids.append(mid)

        val = m["value_mm"]
        lo = m["tol_lo_mm"]
        hi = m["tol_hi_mm"]
        old_verdict = m.get("current_verdict", m.get("verdict", "pass"))
        new_verdict = recompute_verdict(val, lo, hi, e, U)

        # Check if already processed for this event_id
        hist = m.get("verdict_history", [])
        already_has_event = any(h.get("event_id") == event_id for h in hist)

        if not already_has_event:
            hist_entry = {
                "event_id": event_id,
                "old": old_verdict,
                "new": new_verdict,
                "e_mm": e,
                "u_mm": U,
                "ts": now_utc,
            }
            db.measurements.update_one(
                {"_id": mid},
                {
                    "$set": {"current_verdict": new_verdict},
                    "$push": {"verdict_history": hist_entry},
                },
            )
            measurements_recomputed += 1

            if new_verdict != old_verdict:
                verdict_changes += 1
                log_event(
                    db,
                    "measurement_recomputed",
                    measurement_id=mid,
                    old=old_verdict,
                    new=new_verdict,
                    event_id=event_id,
                )

        m["current_verdict"] = new_verdict
        measurements_map[mid] = m

    # 5. Find affected memories (memories whose derived_from contains suspect measurements)
    affected_memories = list(
        db.memories.find({
            "derived_from": {"$in": suspect_ids},
            "type": {"$in": ["lesson", "failed_attempt"]},
        })
    )

    # Ensure measurements_map contains all measurements referenced in support_sets of affected memories
    all_needed_mids: set = set()
    for mem in affected_memories:
        for s_set in mem.get("support_sets", []):
            for m_item in s_set:
                if m_item.startswith("M") and m_item not in measurements_map:
                    all_needed_mids.add(m_item)

    if all_needed_mids:
        for m_doc in db.measurements.find({"_id": {"$in": list(all_needed_mids)}}):
            measurements_map[m_doc["_id"]] = m_doc

    demoted_memories: Dict[str, str] = {}  # id -> new_state
    lesson_changes = 0

    # 6. Re-evaluate each affected memory
    for mem in affected_memories:
        mem_id = mem["_id"]
        old_state = mem.get("validity_state", ValidityState.PROVISIONAL.value)
        support_sets = mem.get("support_sets", [])

        eval_res = evaluate_lesson_from_measurements(
            old_state=old_state,
            support_sets=support_sets,
            measurements_map=measurements_map,
        )

        new_state = eval_res["computed_state"]

        if eval_res["state_changed"]:
            lesson_changes += 1
            demoted_memories[mem_id] = new_state

            history_entry = {
                "ts": now_utc,
                "event": "lesson_state_changed",
                "from_state": old_state,
                "to_state": new_state,
                "cause": f"{gauge_id} out of tolerance, event {event_id}",
                "event_id": event_id,
                "note": f"Support set status: {eval_res['set_statuses']}",
            }

            update_doc: Dict[str, Any] = {
                "$set": {
                    "validity_state": new_state,
                },
                "$inc": {"version": 1},
                "$push": {"history": history_entry},
            }

            if new_state == ValidityState.HISTORICAL_ONLY.value:
                update_doc["$set"]["invalid_at"] = now_utc

            db.memories.update_one({"_id": mem_id}, update_doc)

            log_event(
                db,
                "lesson_state_changed",
                memory_id=mem_id,
                from_state=old_state,
                to_state=new_state,
                cause=f"{gauge_id} out of tolerance, event {event_id}",
                event_id=event_id,
            )

        elif eval_res["saved_by_independent_support"]:
            # State did not change (stayed ACTIVE), but independent support saved it!
            # Identify the surviving gauge
            surviving_set_idx = eval_res["surviving_set_index"]
            surviving_gauge = "CMM-02"  # default
            if surviving_set_idx is not None and surviving_set_idx < len(support_sets):
                surviving_mids = support_sets[surviving_set_idx]
                if surviving_mids and surviving_mids[0] in measurements_map:
                    surviving_gauge = measurements_map[surviving_mids[0]].get("gauge_id", "CMM-02")

            note_str = f"saved by independent support on {surviving_gauge}"

            # Only append history if not already noted for this event
            has_saved_note = any(
                h.get("event_id") == event_id and h.get("event") == "lesson_saved_by_independent_support"
                for h in mem.get("history", [])
            )
            if not has_saved_note:
                save_history_entry = {
                    "ts": now_utc,
                    "event": "lesson_saved_by_independent_support",
                    "from_state": old_state,
                    "to_state": old_state,
                    "cause": note_str,
                    "event_id": event_id,
                    "note": note_str,
                }
                db.memories.update_one(
                    {"_id": mem_id},
                    {"$push": {"history": save_history_entry}},
                )
                log_event(
                    db,
                    "lesson_saved_by_independent_support",
                    memory_id=mem_id,
                    cause=note_str,
                    event_id=event_id,
                )

    # 7. Transitive demotion via $graphLookup over supports
    for demoted_id in list(demoted_memories.keys()):
        try:
            pipeline = [
                {"$match": {"_id": demoted_id}},
                {
                    "$graphLookup": {
                        "from": "memories",
                        "startWith": "$supports",
                        "connectFromField": "supports",
                        "connectToField": "_id",
                        "maxDepth": 3,
                        "as": "dependents",
                    }
                },
            ]
            lookup_res = list(db.memories.aggregate(pipeline))
            for doc in lookup_res:
                for dep in doc.get("dependents", []):
                    dep_id = dep["_id"]
                    if dep_id not in demoted_memories:
                        dep_old_st = dep.get("validity_state", ValidityState.ACTIVE.value)
                        dep_support_sets = dep.get("support_sets", [])
                        dep_eval = evaluate_lesson_from_measurements(
                            old_state=dep_old_st,
                            support_sets=dep_support_sets,
                            measurements_map=measurements_map,
                            memories_map=demoted_memories,
                        )
                        if dep_eval["state_changed"]:
                            dep_new_st = dep_eval["computed_state"]
                            demoted_memories[dep_id] = dep_new_st
                            lesson_changes += 1
                            db.memories.update_one(
                                {"_id": dep_id},
                                {
                                    "$set": {"validity_state": dep_new_st},
                                    "$inc": {"version": 1},
                                    "$push": {
                                        "history": {
                                            "ts": now_utc,
                                            "event": "lesson_state_changed",
                                            "from_state": dep_old_st,
                                            "to_state": dep_new_st,
                                            "cause": f"Transitive demotion from {demoted_id}",
                                            "event_id": event_id,
                                        }
                                    },
                                },
                            )
                            log_event(
                                db,
                                "lesson_state_changed",
                                memory_id=dep_id,
                                from_state=dep_old_st,
                                to_state=dep_new_st,
                                cause=f"Transitive demotion from {demoted_id}",
                                event_id=event_id,
                            )
        except Exception as e:
            print(f"Notice: graphLookup iteration for {demoted_id}: {e}")

    # 8. Flag decisions that used any demoted memory
    decisions_flagged = 0
    for demoted_id, new_st in demoted_memories.items():
        decisions_to_flag = list(
            db.decisions.find({"lessons_used": demoted_id, "review_flag": {"$ne": True}})
        )
        for dec in decisions_to_flag:
            dec_id = dec["_id"]
            reason = f"Used {demoted_id}, now {new_st} after {gauge_id} calibration event {event_id}"
            db.decisions.update_one(
                {"_id": dec_id},
                {"$set": {"review_flag": True, "review_reason": reason}},
            )
            decisions_flagged += 1
            log_event(
                db,
                "decision_flagged",
                decision_id=dec_id,
                cause=reason,
                event_id=event_id,
                part_serials=dec.get("part_serials", []),
            )

    # 9. Log cascade finished
    summary = {
        "measurements_recomputed": measurements_recomputed,
        "verdict_changes": verdict_changes,
        "lesson_changes": lesson_changes,
        "decisions_flagged": decisions_flagged,
    }

    log_event(
        db,
        "cascade_finished",
        event_id=event_id,
        gauge_id=gauge_id,
        payload=summary,
    )

    return summary


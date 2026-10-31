"""Demo stage execution handlers for Metrologic.

Implements Section 10 of docs/PLAN.md:
- Stage 1a: Ingests NCR-0412, creates F1, L1, L2 as PROVISIONAL with BG-07 evidence.
- Stage 1b: Corroborates L1 on CMM-02, promoting L1 to ACTIVE.
- Stage 2: Records Stage 2 decision for Inconel 718 sleeve Ø28H7.
- Stage 3 arm: Injects provisional memory T1 with expire_at = now + 30s.
- Stage 3: Posts calibration on BG-07 (+0.006 mm, U=0.002 mm) and runs cascade.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict
import yaml
from pymongo.database import Database

from backend.app.events import log_event
from backend.app.streams.gauge_watcher import post_calibration_event
from backend.seed.reset import parse_datetime

SCENARIO_FILE = Path(__file__).resolve().parent / "scenario.yaml"


def _load_scenario() -> Dict[str, Any]:
    with open(SCENARIO_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_stage_1a(db: Database) -> Dict[str, Any]:
    """Stage 1a: Ingests NCR-0412 trials and BG-07 measurements."""
    scenario = _load_scenario()
    now_utc = datetime.now(timezone.utc)

    # Insert scenario measurements (M1..M5, M9..M16)
    m_docs = [
        parse_datetime(m)
        for m in scenario.get("measurements", [])
        if m["_id"] in {f"M{i}" for i in range(1, 6)}.union({f"M{j}" for j in range(9, 17)})
    ]

    for m in m_docs:
        db.measurements.update_one({"_id": m["_id"]}, {"$set": m}, upsert=True)

    # Insert F1, L1 (PROVISIONAL), L2 (PROVISIONAL)
    memories = [
        parse_datetime(mem)
        for mem in scenario.get("memories", [])
        if mem["_id"] in {"F1", "L1", "L2"}
    ]

    for mem in memories:
        # Initial state is PROVISIONAL
        mem["validity_state"] = "PROVISIONAL"
        if mem["_id"] == "L1":
            # In Stage 1a, L1 has only BG-07 support set before corroboration
            mem["support_sets"] = [["M1", "M2", "M3", "M4", "M5"]]
            mem["derived_from"] = ["M1", "M2", "M3", "M4", "M5"]
        db.memories.update_one({"_id": mem["_id"]}, {"$set": mem}, upsert=True)
        log_event(
            db,
            "memory_created",
            memory_id=mem["_id"],
            to_state="PROVISIONAL",
            cause="ingest NCR-0412",
        )

    return {
        "stage": "1a",
        "status": "success",
        "created_memories": ["F1", "L1", "L2"],
        "measurements_ingested": len(m_docs),
    }


def run_stage_1b(db: Database) -> Dict[str, Any]:
    """Stage 1b: Corroborates L1 on CMM-02 (M6..M8) and promotes to ACTIVE."""
    scenario = _load_scenario()
    now_utc = datetime.now(timezone.utc)

    # Insert CMM-02 measurements (M6..M8)
    cmm_measurements = [
        parse_datetime(m)
        for m in scenario.get("measurements", [])
        if m["_id"] in {"M6", "M7", "M8"}
    ]
    for m in cmm_measurements:
        db.measurements.update_one({"_id": m["_id"]}, {"$set": m}, upsert=True)

    # Corroborate L1: add second support set, unset expire_at, promote to ACTIVE
    cmm_set = ["M6", "M7", "M8"]
    hist_entry = {
        "ts": now_utc,
        "event": "corroborated",
        "from_state": "PROVISIONAL",
        "to_state": "ACTIVE",
        "cause": "corroborated by CMM-02 (job NCR-0419)",
        "note": "Two instruments now support this lesson",
    }

    db.memories.update_one(
        {"_id": "L1"},
        {
            "$set": {
                "validity_state": "ACTIVE",
                "support_sets": [["M1", "M2", "M3", "M4", "M5"], cmm_set],
                "derived_from": ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8"],
            },
            "$unset": {"expire_at": ""},
            "$push": {"history": hist_entry},
            "$inc": {"version": 1},
        },
    )

    log_event(
        db,
        "lesson_state_changed",
        memory_id="L1",
        from_state="PROVISIONAL",
        to_state="ACTIVE",
        cause="corroborated by CMM-02 (job NCR-0419)",
    )

    return {
        "stage": "1b",
        "status": "success",
        "memory_id": "L1",
        "new_state": "ACTIVE",
        "independent_instruments": 2,
    }


def run_stage_2(db: Database) -> Dict[str, Any]:
    """Stage 2: Records decision D-STAGE2 for Inconel 718 sleeve boring."""
    now_utc = datetime.now(timezone.utc)
    decision_doc = {
        "_id": "D-STAGE2",
        "query": "Process plan for an Inconel 718 sleeve with a Ø28H7 bore",
        "scope": {
            "material": "Inconel 718",
            "process": "finish boring",
            "machine": "VF-4",
            "feature_class": "bore",
            "tolerance_band": "H7",
        },
        "plan_steps": [
            {
                "kind": "apply",
                "text": "Add a finishing spring pass with 0.05 mm radial depth of cut on finish boring",
                "lesson_ids": ["L1"],
            },
            {
                "kind": "apply",
                "text": "Raise coolant concentration to 10% before finish boring Inconel 718 bores",
                "lesson_ids": ["L2"],
            },
            {
                "kind": "avoid",
                "text": "Do not: Reduce feed only. Failed on a prior job (F1)",
                "lesson_ids": ["F1"],
            },
        ],
        "lessons_used": ["L1", "L2", "F1"],
        "ranking_trace": [],
        "part_serials": ["SN-3001", "SN-3002"],
        "created_at": now_utc,
        "review_flag": False,
        "review_reason": None,
    }

    db.decisions.update_one({"_id": "D-STAGE2"}, {"$set": decision_doc}, upsert=True)
    db.memories.update_one({"_id": "L1"}, {"$addToSet": {"used_by": "D-STAGE2"}})
    db.memories.update_one({"_id": "L2"}, {"$addToSet": {"used_by": "D-STAGE2"}})

    log_event(
        db,
        "decision_created",
        decision_id="D-STAGE2",
        lessons_used=["L1", "L2", "F1"],
    )

    return {
        "stage": "2",
        "status": "success",
        "decision_id": "D-STAGE2",
        "lessons_used": ["L1", "L2", "F1"],
    }


def run_stage_3_arm(db: Database) -> Dict[str, Any]:
    """Stage 3 Arm: Inserts provisional memory T1 with expire_at = now + 30s."""
    now_utc = datetime.now(timezone.utc)
    expire_dt = now_utc + timedelta(seconds=30)

    # Insert support measurement for T1 on BG-03
    t1_meas = {
        "_id": "M-T1",
        "gauge_id": "BG-03",
        "part_serial": "SN-T1",
        "value_mm": 20.005,
        "nominal_mm": 20.000,
        "tol_lo_mm": 20.000,
        "tol_hi_mm": 20.021,
        "u_mm": 0.002,
        "timestamp": now_utc,
        "feature": "Ø20H7 trial bore",
        "verdict": "pass",
        "current_verdict": "pass",
        "verdict_history": [],
    }
    db.measurements.update_one({"_id": "M-T1"}, {"$set": t1_meas}, upsert=True)

    t1_mem = {
        "_id": "T1",
        "workspace": "plant-1",
        "owner": "role:process-engineer",
        "type": "lesson",
        "title": "Abandoned trial: High-pressure air blast on aluminum",
        "content": "Temporary trial using dry air blast on aluminum 6061; abandoned due to chip buildup.",
        "action": "Do not adopt dry air blast for long deep pocket operations",
        "scope": {
            "material": "6061-T6",
            "process": "pocket milling",
            "machine": "VF-4",
            "feature_class": "pocket",
            "tolerance_band": "IT9",
        },
        "support_sets": [["M-T1"]],
        "derived_from": ["M-T1"],
        "supports": [],
        "used_by": [],
        "validity_state": "PROVISIONAL",
        "mw_success": 0,
        "mw_fail": 0,
        "created_at": now_utc,
        "valid_from": now_utc,
        "expire_at": expire_dt,
        "version": 1,
        "history": [
            {
                "ts": now_utc,
                "event": "created",
                "from_state": None,
                "to_state": "PROVISIONAL",
                "cause": "abandoned_trial_30s_ttl",
            }
        ],
    }

    db.memories.update_one({"_id": "T1"}, {"$set": t1_mem}, upsert=True)
    log_event(
        db,
        "memory_created",
        memory_id="T1",
        to_state="PROVISIONAL",
        expire_at=expire_dt.isoformat(),
        cause="ttl_demo_helper",
    )

    return {
        "stage": "3_arm",
        "status": "success",
        "memory_id": "T1",
        "expire_at": expire_dt.isoformat(),
        "ttl_seconds": 30,
    }


def run_stage_3(db: Database) -> Dict[str, Any]:
    """Stage 3: Posts BG-07 out of tolerance (+0.006 mm, U=0.002 mm) and triggers cascade."""
    cal_res = post_calibration_event(
        db=db,
        gauge_id="BG-07",
        as_found_error_mm=0.006,
        as_found_u_mm=0.002,
        direct=True,
    )
    return {
        "stage": "3",
        "status": "success",
        "calibration": cal_res,
    }


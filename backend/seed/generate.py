"""Scripted synthetic dataset generator for Metrologic.

Implements Section 9.3 of docs/PLAN.md:
Generates ~190 filler measurements far from limits across 6 gauges,
and 13 background lessons with independent support sets on non-suspect gauges.
Uses a deterministic random seed for complete reproducibility.
"""

import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

SEED = 42
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
EMBEDDINGS_FILE = FIXTURES_DIR / "embeddings.json"


def _make_unit_vector(dim: int, seed_val: int) -> List[float]:
    """Generates a deterministic pseudo-random unit vector."""
    rng = random.Random(seed_val)
    vec = [rng.gauss(0.0, 1.0) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in vec))
    return [round(x / norm, 6) for x in vec]


def generate_background_lessons(num_lessons: int = 13) -> Tuple[List[Dict[str, Any]], Dict[str, List[float]]]:
    """Generates 13 background lessons (B1 to B13) on independent non-suspect gauges."""
    materials = [
        "Al 7075-T6", "316L", "Ti-6Al-4V", "Inconel 718", "4140", "Copper C110",
        "PEEK", "6061-T6", "17-4 PH", "Monel 400", "D2 Tool Steel", "Brass C360", "Hastelloy X"
    ]
    processes = [
        "face milling", "OD turning", "deep hole drilling", "thread milling",
        "reaming", "wire EDM", "grooving", "finish boring", "chamfering",
        "slotting", "surface grinding", "parting", "contouring"
    ]
    machines = ["VF-4", "ST-20", "DMG-50", "Brother-R450", "Okuma-LB3000"]
    non_suspect_gauges = ["BG-03", "CMM-05", "MIC-11", "HG-04"]

    lessons: List[Dict[str, Any]] = []
    embeddings_map: Dict[str, List[float]] = {}

    rng = random.Random(SEED)
    base_time = datetime(2026, 8, 15, 8, 0, 0, tzinfo=timezone.utc)

    for i in range(1, num_lessons + 1):
        b_id = f"B{i}"
        mat = materials[(i - 1) % len(materials)]
        proc = processes[(i - 1) % len(processes)]
        mach = machines[(i - 1) % len(machines)]
        gauge1 = non_suspect_gauges[(i - 1) % len(non_suspect_gauges)]
        gauge2 = non_suspect_gauges[i % len(non_suspect_gauges)]

        # Two independent support sets from non-suspect gauges
        s1 = [f"F-{b_id}-1", f"F-{b_id}-2"]
        s2 = [f"F-{b_id}-3", f"F-{b_id}-4"]

        emb = _make_unit_vector(1024, SEED + i * 100)
        embeddings_map[b_id] = emb

        lesson = {
            "_id": b_id,
            "workspace": "plant-1",
            "owner": "role:process-engineer",
            "type": "lesson",
            "title": f"Optimized {proc} parameters for {mat}",
            "content": f"Standardized feed, speed, and tooling clearance for {mat} under {proc} operations on {mach}.",
            "action": f"Apply calibrated feed rate of 0.12 mm/tooth for {mat} {proc}",
            "scope": {
                "material": mat,
                "process": proc,
                "machine": mach,
                "feature_class": "general",
                "tolerance_band": "IT8",
            },
            "source": {
                "ncr_id": f"NCR-B{i:03d}",
                "author_role": "manufacturing-engineer",
                "session_id": f"s-bg-{i}",
            },
            "support_sets": [s1, s2],
            "derived_from": s1 + s2,
            "supports": [],
            "used_by": [],
            "validity_state": "ACTIVE",
            "mw_success": rng.randint(2, 8),
            "mw_fail": rng.randint(0, 1),
            "embedding": emb,
            "created_at": (base_time + timedelta(days=i)).isoformat(),
            "valid_from": (base_time + timedelta(days=i)).isoformat(),
            "invalid_at": None,
            "expire_at": None,
            "version": 1,
            "history": [
                {
                    "ts": (base_time + timedelta(days=i)).isoformat(),
                    "event": "created",
                    "from_state": None,
                    "to_state": "ACTIVE",
                    "cause": "Historical standard operating lesson",
                    "note": f"Validated across {gauge1} and {gauge2}",
                }
            ],
        }
        lessons.append(lesson)

    return lessons, embeddings_map


def generate_filler_measurements(background_lessons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Generates ~190 filler measurements far from limits, plus M-old."""
    measurements: List[Dict[str, Any]] = []
    rng = random.Random(SEED + 999)

    # 1. First, create the measurements explicitly referenced by background lessons (13 * 4 = 52)
    non_suspect_gauges = ["BG-03", "CMM-05", "MIC-11", "HG-04"]
    b_time = datetime(2026, 8, 10, 8, 0, 0, tzinfo=timezone.utc)

    for idx, b_lesson in enumerate(background_lessons):
        g1 = non_suspect_gauges[idx % len(non_suspect_gauges)]
        g2 = non_suspect_gauges[(idx + 1) % len(non_suspect_gauges)]

        for s_idx, (mid, g_id) in enumerate([
            (b_lesson["support_sets"][0][0], g1),
            (b_lesson["support_sets"][0][1], g1),
            (b_lesson["support_sets"][1][0], g2),
            (b_lesson["support_sets"][1][1], g2),
        ]):
            measurements.append({
                "_id": mid,
                "gauge_id": g_id,
                "part_serial": f"SN-BG-{idx+1}-{s_idx+1}",
                "value_mm": 50.010,
                "nominal_mm": 50.000,
                "tol_lo_mm": 50.000,
                "tol_hi_mm": 50.030,
                "u_mm": 0.002,
                "timestamp": (b_time + timedelta(days=idx, hours=s_idx)).isoformat(),
                "feature": "Standard feature",
                "verdict": "pass",
                "current_verdict": "pass",
                "verdict_history": [],
            })

    # 2. Add ~40 filler measurements on BG-07 inside the suspect window (2026-08-02 to 2026-10-30)
    # Mid-band values (e.g. nominal 40.000, tol 40.000 to 40.030, values 40.015 to 40.018)
    # Even under +0.006 shift and U=0.002, interval remains [40.007, 40.014] inside [40.000, 40.030] -> pass!
    bg07_start = datetime(2026, 8, 5, 8, 0, 0, tzinfo=timezone.utc)
    for k in range(1, 41):
        val = round(40.014 + rng.uniform(-0.002, 0.002), 4)
        measurements.append({
            "_id": f"FILL-BG07-{k:02d}",
            "gauge_id": "BG-07",
            "part_serial": f"SN-F07-{k:02d}",
            "value_mm": val,
            "nominal_mm": 40.000,
            "tol_lo_mm": 40.000,
            "tol_hi_mm": 40.030,
            "u_mm": 0.002,
            "timestamp": (bg07_start + timedelta(days=k * 2, minutes=k * 15)).isoformat(),
            "feature": "Ø40H8 sleeve bore",
            "verdict": "pass",
            "current_verdict": "pass",
            "verdict_history": [],
        })

    # 3. Add ~100 additional filler measurements across other gauges (BG-03, CMM-02, CMM-05, MIC-11, HG-04)
    other_gauges = ["BG-03", "CMM-02", "CMM-05", "MIC-11", "HG-04"]
    other_start = datetime(2026, 8, 10, 9, 0, 0, tzinfo=timezone.utc)
    for m in range(1, 101):
        g_choice = other_gauges[m % len(other_gauges)]
        measurements.append({
            "_id": f"FILL-OTHER-{m:03d}",
            "gauge_id": g_choice,
            "part_serial": f"SN-FO-{m:03d}",
            "value_mm": round(25.012 + rng.uniform(-0.003, 0.003), 4),
            "nominal_mm": 25.000,
            "tol_lo_mm": 25.000,
            "tol_hi_mm": 25.025,
            "u_mm": 0.002,
            "timestamp": (other_start + timedelta(days=(m % 60), hours=(m % 12))).isoformat(),
            "feature": "Ø25H7 journal pin",
            "verdict": "pass",
            "current_verdict": "pass",
            "verdict_history": [],
        })

    # 4. Add M-old: BG-07 measurement before last_good_cal (2026-07-20 < 2026-08-01)
    measurements.append({
        "_id": "M-old",
        "gauge_id": "BG-07",
        "part_serial": "SN-2050",
        "value_mm": 32.003,
        "nominal_mm": 32.000,
        "tol_lo_mm": 32.000,
        "tol_hi_mm": 32.025,
        "u_mm": 0.002,
        "timestamp": "2026-07-20T10:00:00Z",
        "feature": "Ø32H7 bore",
        "verdict": "pass",
        "current_verdict": "pass",
        "verdict_history": [],
    })

    return measurements


def save_fixtures() -> None:
    """Generates and writes fixtures to seed/fixtures/embeddings.json."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    lessons, embeddings_map = generate_background_lessons(13)
    with open(EMBEDDINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(embeddings_map, f, indent=2)
    print(f"Saved {len(embeddings_map)} background embeddings to {EMBEDDINGS_FILE}")


if __name__ == "__main__":
    save_fixtures()


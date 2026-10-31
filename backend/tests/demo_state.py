"""Shared in-memory demo state for Track A tests.

Builds the same synthetic base data the demo reset loads (gauges, scenario
measurements, background lessons, filler, past decisions) and writes the
NCR-0412 lessons through the real ``write_lesson`` path so embeddings and
support sets match production.  No MongoDB, no API server, no LLM.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

import yaml

from backend.app.memory.writer import write_lesson
from backend.seed.generate import generate_background_lessons, generate_filler_measurements
from backend.seed.reset import parse_datetime
from backend.tests.mock_db import MockDatabase

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
SCENARIO_FILE = SEED_DIR / "scenario.yaml"
NCR_FIXTURE = SEED_DIR / "fixtures" / "ncr_0412_lessons.json"

STAGE2_QUERY = "Process plan for an Inconel 718 sleeve with a Ø28H7 bore"
STAGE2_SCOPE: Dict[str, str] = {
    "material": "Inconel 718",
    "process": "finish boring",
    "machine": "VF-4",
    "feature_class": "bore",
    "tolerance_band": "H7",
}


def load_scenario() -> Dict[str, Any]:
    with open(SCENARIO_FILE, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_ncr_fixture() -> Dict[str, Any]:
    return json.loads(NCR_FIXTURE.read_text(encoding="utf-8"))


NCR_TRIALS: List[Dict[str, Any]] = [
    {
        "id": "A",
        "description": "Reduce feed only",
        "outcome": "fail",
        "measurement_ids": ["M14", "M15", "M16"],
    },
    {
        "id": "B",
        "description": "Spring pass plus lower radial engagement",
        "outcome": "pass",
        "measurement_ids": ["M1", "M2", "M3", "M4", "M5"],
    },
    {
        "id": "C",
        "description": "Coolant concentration 8% to 10% on Inconel 718",
        "outcome": "pass",
        "measurement_ids": ["M9", "M10", "M11", "M12", "M13"],
    },
]


def demo_ncr_measurements() -> List[Dict[str, Any]]:
    """The M1..M16 documents exactly as the Stage 1a request sends them."""
    scenario = load_scenario()
    wanted = {f"M{i}" for i in range(1, 17)}
    return [m for m in scenario.get("measurements", []) if m["_id"] in wanted]


def ncr_payload(ncr_id: str = "NCR-0412") -> Dict[str, Any]:
    """Build the Stage 1a ``POST /ncr`` body (PLAN 7.3 / Section 10)."""
    return {
        "ncr_id": ncr_id,
        "workspace": "plant-1",
        "summary": (
            "Ti-6Al-4V housing, Ø32H7 bore tapered after finish boring. "
            "Separate chatter on Inconel 718 sleeve."
        ),
        "trials": [dict(trial) for trial in NCR_TRIALS],
        "measurements": demo_ncr_measurements(),
    }


def seed_base_data(db: MockDatabase) -> MockDatabase:
    """Gauges + M1..M16 + M-old + B1..B13 + filler + D1/D2."""
    scenario = load_scenario()

    for gauge in scenario.get("gauges", []):
        db.gauges.insert_one(parse_datetime(gauge))

    for measurement in scenario.get("measurements", []):
        db.measurements.insert_one(parse_datetime(measurement))

    background, _ = generate_background_lessons(13)
    for lesson in background:
        db.memories.insert_one(parse_datetime(lesson))

    for measurement in generate_filler_measurements(background):
        if measurement["_id"] == "M-old":
            continue  # already inserted with the scenario measurements
        db.measurements.insert_one(parse_datetime(measurement))

    for decision in scenario.get("decisions", []):
        db.decisions.insert_one(parse_datetime(decision))

    return db


def seed_ncr_lessons(db: MockDatabase) -> List[Dict[str, Any]]:
    """Write the NCR-0412 lessons in fixture order: L1, L2, F1."""
    fixture = load_ncr_fixture()
    created = []
    for lesson in fixture["lessons"]:
        created.append(
            write_lesson(
                db,
                type=lesson["kind"],
                title=lesson["title"],
                content=lesson["content"],
                action=lesson["action"],
                scope=lesson["scope"],
                measurement_ids=lesson["measurement_ids"],
                source={
                    "ncr_id": fixture["ncr_id"],
                    "author_role": "manufacturing-engineer",
                    "session_id": "s-001",
                },
            )
        )
    return created


def build_demo_db() -> MockDatabase:
    db = MockDatabase("test_metrologic")
    seed_base_data(db)
    seed_ncr_lessons(db)
    return db

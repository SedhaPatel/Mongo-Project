"""Shared domain models for Metrologic (Data Contract v1).

This file represents the frozen data contract across Track A, Track B, and Track C
as detailed in Section 5 of docs/PLAN.md.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ValidityState(str, Enum):
    ACTIVE = "ACTIVE"
    PROVISIONAL = "PROVISIONAL"
    NEEDS_VERIFICATION = "NEEDS_VERIFICATION"
    HISTORICAL_ONLY = "HISTORICAL_ONLY"
    SUPERSEDED = "SUPERSEDED"


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INDETERMINATE = "indeterminate"


class MemoryType(str, Enum):
    EPISODE = "episode"
    LESSON = "lesson"
    FAILED_ATTEMPT = "failed_attempt"
    DECISION_NOTE = "decision_note"
    CONSTRAINT = "constraint"
    FEEDBACK = "feedback"


class GaugeCalStatus(str, Enum):
    OK = "OK"
    OUT_OF_TOLERANCE = "OUT_OF_TOLERANCE"
    EXPIRED = "EXPIRED"


class Scope(BaseModel):
    material: str
    process: str
    machine: Optional[str] = None
    feature_class: Optional[str] = None
    tolerance_band: Optional[str] = None

    model_config = {
        "extra": "ignore",
    }


class Source(BaseModel):
    ncr_id: Optional[str] = None
    author_role: Optional[str] = "manufacturing-engineer"
    session_id: Optional[str] = None


class MemoryHistoryEntry(BaseModel):
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event: str = "state_change"
    from_state: Optional[str] = None
    to_state: str
    cause: str = ""
    event_id: Optional[str] = None
    note: str = ""


class Memory(BaseModel):
    id: str = Field(alias="_id")
    workspace: str = "plant-1"
    owner: Optional[str] = "role:process-engineer"
    type: MemoryType = MemoryType.LESSON
    title: str = ""
    content: str = ""
    action: str = ""
    scope: Scope
    source: Optional[Source] = None
    support_sets: List[List[str]] = Field(default_factory=list)
    derived_from: List[str] = Field(default_factory=list)
    supports: List[str] = Field(default_factory=list)
    used_by: List[str] = Field(default_factory=list)
    validity_state: ValidityState = ValidityState.PROVISIONAL
    mw_success: int = 0
    mw_fail: int = 0
    embedding: Optional[List[float]] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valid_from: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    invalid_at: Optional[datetime] = None
    expire_at: Optional[datetime] = None
    version: int = 1
    history: List[MemoryHistoryEntry] = Field(default_factory=list)

    model_config = {
        "populate_by_name": True,
        "use_enum_values": True,
    }


class MeasurementVerdictHistoryEntry(BaseModel):
    event_id: str
    old: str
    new: str
    e_mm: float
    u_mm: float
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "use_enum_values": True,
    }


class Measurement(BaseModel):
    id: str = Field(alias="_id")
    gauge_id: str
    part_serial: str
    value_mm: float
    nominal_mm: float
    tol_lo_mm: float
    tol_hi_mm: float
    u_mm: float
    timestamp: datetime
    feature: Optional[str] = None
    verdict: Verdict = Verdict.PASS
    current_verdict: Verdict = Verdict.PASS
    verdict_history: List[MeasurementVerdictHistoryEntry] = Field(default_factory=list)

    model_config = {
        "populate_by_name": True,
        "use_enum_values": True,
    }


class Gauge(BaseModel):
    id: str = Field(alias="_id")
    type: str
    cal_status: str = "OK"
    last_good_cal: datetime
    as_found_error_mm: Optional[float] = None
    as_found_u_mm: Optional[float] = None
    event_id: Optional[str] = None
    event_time: Optional[datetime] = None

    model_config = {
        "populate_by_name": True,
        "use_enum_values": True,
    }


class RankingTrace(BaseModel):
    memory_id: str
    vector_score: float = 0.0
    state: str = ""
    state_bias: float = 0.0
    mw: float = 0.0
    mw_term: float = 0.0
    recency: float = 0.0
    recency_term: float = 0.0
    scope_match: float = 0.0
    scope_term: float = 0.0
    final: float = 0.0


class Decision(BaseModel):
    id: str = Field(alias="_id")
    query: str
    scope: Dict[str, Any] = Field(default_factory=dict)
    plan_steps: List[Dict[str, Any]] = Field(default_factory=list)
    lessons_used: List[str] = Field(default_factory=list)
    ranking_trace: List[RankingTrace] = Field(default_factory=list)
    part_serials: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    review_flag: bool = False
    review_reason: Optional[str] = None

    model_config = {
        "populate_by_name": True,
        "use_enum_values": True,
    }


class AuditLog(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event: str
    memory_id: Optional[str] = None
    gauge_id: Optional[str] = None
    decision_id: Optional[str] = None
    from_state: Optional[str] = None
    to_state: Optional[str] = None
    cause: Optional[str] = None
    event_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    payload: Optional[Dict[str, Any]] = None

    model_config = {
        "populate_by_name": True,
        "use_enum_values": True,
    }


class StreamState(BaseModel):
    id: str = Field(alias="_id")
    resume_token: Optional[Dict[str, Any]] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "populate_by_name": True,
    }


class CalibrationEventRequest(BaseModel):
    gauge_id: str
    as_found_error_mm: float
    as_found_u_mm: float
    result: str = "OUT_OF_TOLERANCE"
    event_id: Optional[str] = None
    event_time: Optional[datetime] = None

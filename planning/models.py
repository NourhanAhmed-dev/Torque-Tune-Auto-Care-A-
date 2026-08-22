from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class PlanningRequest:
    request: str
    client_id: int
    vehicle_id: int
    tech_id: int
    appointment_id: int


class PlanningDecision(str, Enum):
    RELEASE = "RELEASE"
    HOLD = "HOLD"
    ESCALATE = "ESCALATE"


@dataclass(frozen=True)
class PlanningResult:
    decision: PlanningDecision
    reasons: list[str]
    evidence: list[str]
    next_actions: list[str]
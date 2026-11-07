"""초안 점검과 사람 관문에 사용하는 값 객체."""

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class Rule:
    id: str
    pattern: str
    severity: str
    reason: str
    ref: str


@dataclass(frozen=True)
class RulePack:
    name: str
    rules: list[Rule]


@dataclass(frozen=True)
class DraftSpec:
    min_chars: int
    max_chars: int
    headings: int
    min_sources: int
    min_human_slots: int
    human_slot_pattern: str


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    message: str
    line: int | None


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    findings: list[Finding]
    metrics: dict[str, int]


class GateLevel(str, Enum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    HUMAN_ONLY = "HUMAN_ONLY"


class Decision(str, Enum):
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"


@dataclass(frozen=True)
class GateDecision:
    gate: str
    run_id: str
    decision: Decision
    missed_by_machine: bool
    note: str
    ts: str


@dataclass(frozen=True)
class GateSpec:
    id: str
    name: str
    start: GateLevel
    max: GateLevel
    why: str

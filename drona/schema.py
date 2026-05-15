# drona/schema.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TypedDict, Literal, Any
from enum import Enum
import uuid


# ─── RAW EVENT ────────────────────────────────────────────────────────────────

Event = dict[str, Any]


# ─── INPUT SIGNAL ─────────────────────────────────────────────────────────────

@dataclass
class IncidentSignal:
    incident_id: str
    trigger:     str
    ts:          str
    service:     str | None = None


# ─── OUTPUT TYPES ─────────────────────────────────────────────────────────────

@dataclass
class CausalEdge:
    cause_id:     str
    effect_id:    str
    evidence:     list[Event]
    confidence:   float
    relationship: str = "causes"

@dataclass
class IncidentMatch:
    past_incident_id: str
    similarity:       float
    rationale:        str

@dataclass
class Remediation:
    action:             str
    target:             str
    historical_outcome: str
    confidence:         float

class Context(TypedDict):
    related_events:         list[Event]
    causal_chain:           list[CausalEdge]
    similar_past_incidents: list[IncidentMatch]
    suggested_remediations: list[Remediation]
    confidence:             float
    explain:                str


# ─── BEHAVIORAL SIGNATURE ─────────────────────────────────────────────────────

class TriggerType(str, Enum):
    DEPLOY             = "deploy"
    METRIC_ALERT       = "metric_alert"
    DEPENDENCY_FAILURE = "dependency_failure"
    UNKNOWN            = "unknown"

class SymptomType(str, Enum):
    LATENCY_SPIKE    = "latency_spike"
    ERROR_RATE_SPIKE = "error_rate_spike"
    UPSTREAM_TIMEOUT = "upstream_timeout"
    TRACE_SLOWDOWN   = "trace_slowdown"
    CONNECTION_DROP  = "connection_drop"

class PropagationDir(str, Enum):
    UPSTREAM   = "upstream"
    DOWNSTREAM = "downstream"
    ISOLATED   = "isolated"

@dataclass
class BehaviorPattern:
    """Service-name-agnostic incident signature. No canonical_ids inside."""
    trigger_type:            TriggerType
    symptom_sequence:        list[SymptomType]
    affected_service_count:  int
    propagation_direction:   PropagationDir
    time_to_first_symptom_s: float

    def similarity(self, other: BehaviorPattern) -> float:
        """4-component weighted similarity. Returns 0.0–1.0."""
        score = 0.0
        if self.trigger_type == other.trigger_type:
            score += 0.30
        score += 0.40 * _lcs_ratio(self.symptom_sequence, other.symptom_sequence)
        if self.propagation_direction == other.propagation_direction:
            score += 0.20
        a, b = self.time_to_first_symptom_s, other.time_to_first_symptom_s
        if a > 0 and b > 0:
            ratio = max(a, b) / min(a, b)
            if ratio < 3.0:
                score += 0.10 * max(0.0, 1 - (ratio - 1) / 2)
        return round(min(1.0, score), 4)


def _lcs_ratio(a: list, b: list) -> float:
    """Order-aware longest common subsequence ratio."""
    if not a or not b:
        return 0.0
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            dp[i][j] = (
                dp[i-1][j-1] + 1 if a[i-1] == b[j-1]
                else max(dp[i-1][j], dp[i][j-1])
            )
    return dp[m][n] / max(m, n)


# ─── INCIDENT MEMORY ──────────────────────────────────────────────────────────

@dataclass
class IncidentMemory:
    incident_id:            str
    signature:              BehaviorPattern
    epicentre_canonical_id: str
    remediation_action:     str
    remediation_target_cid: str
    outcome:                str
    opened_at:              str
    closed_at:              str
    context_events:         list[Event]

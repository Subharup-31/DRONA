# drona/signatures.py
from __future__ import annotations
from drona.schema import BehaviorPattern, TriggerType, SymptomType, PropagationDir
from drona.identity import IdentityLayer
from datetime import datetime
from dateutil.parser import parse as parse_dt
import re


def extract_signature(
    events: list[dict],
    anomalies: list[dict],
    identity_layer: IdentityLayer,
    deploy_ts: str | None = None,
) -> BehaviorPattern:
    """Extract a service-name-agnostic behavioral signature from events and anomalies."""

    # Step 1 — trigger_type
    trigger_type = _detect_trigger(events)

    # Step 2 — symptom_sequence (ordered by anomaly timestamp, dedup consecutive)
    symptom_sequence = _build_symptom_sequence(anomalies)

    # Step 3 — affected_service_count
    affected_service_count = _count_affected_services(events, anomalies, identity_layer)

    # Step 4 — propagation_direction
    if affected_service_count == 1:
        propagation_direction = PropagationDir.ISOLATED
    else:
        propagation_direction = PropagationDir.DOWNSTREAM

    # Step 5 — time_to_first_symptom_s
    time_to_first_symptom_s = _compute_time_to_first_symptom(anomalies, deploy_ts)

    return BehaviorPattern(
        trigger_type=trigger_type,
        symptom_sequence=symptom_sequence,
        affected_service_count=affected_service_count,
        propagation_direction=propagation_direction,
        time_to_first_symptom_s=time_to_first_symptom_s,
    )


def _detect_trigger(events: list[dict]) -> TriggerType:
    """Determine trigger type from events."""
    for e in events:
        if e.get("kind") == "deploy":
            return TriggerType.DEPLOY

    for e in events:
        trigger = e.get("trigger", "")
        if isinstance(trigger, str) and "alert" in trigger.lower():
            return TriggerType.METRIC_ALERT

    for e in events:
        if e.get("kind") == "log":
            msg = str(e.get("msg", "")).lower()
            if any(w in msg for w in ("timeout", "connection refused", "unavailable")):
                return TriggerType.DEPENDENCY_FAILURE

    return TriggerType.UNKNOWN


def _build_symptom_sequence(anomalies: list[dict]) -> list[SymptomType]:
    """Build ordered, deduplicated symptom sequence from anomalies."""
    sorted_anomalies = sorted(
        anomalies,
        key=lambda a: a.get("event", {}).get("ts", ""),
    )

    raw_symptoms: list[SymptomType] = []
    for a in sorted_anomalies:
        atype = a.get("type", "")
        event = a.get("event", {})

        if atype == "metric_spike":
            name = str(event.get("name", "")).lower()
            if "latency" in name:
                raw_symptoms.append(SymptomType.LATENCY_SPIKE)
            elif "error" in name:
                raw_symptoms.append(SymptomType.ERROR_RATE_SPIKE)
            else:
                raw_symptoms.append(SymptomType.LATENCY_SPIKE)
        elif atype == "error_log":
            msg = str(event.get("msg", "")).lower()
            if "timeout" in msg:
                raw_symptoms.append(SymptomType.UPSTREAM_TIMEOUT)
            else:
                raw_symptoms.append(SymptomType.ERROR_RATE_SPIKE)
        elif atype == "trace_slowdown":
            raw_symptoms.append(SymptomType.TRACE_SLOWDOWN)

    # Dedup consecutive duplicates
    deduped: list[SymptomType] = []
    for s in raw_symptoms:
        if not deduped or deduped[-1] != s:
            deduped.append(s)

    return deduped


def _count_affected_services(
    events: list[dict],
    anomalies: list[dict],
    identity_layer: IdentityLayer,
) -> int:
    """Count unique canonical_ids across all events and anomalies. Cap at 10."""
    cids: set[str] = set()

    for e in events:
        svc = e.get("service") or e.get("svc")
        if svc:
            cids.add(identity_layer.resolve(svc))

    for a in anomalies:
        event = a.get("event", {})
        svc = event.get("service") or event.get("svc")
        if svc:
            cids.add(identity_layer.resolve(svc))

    return min(len(cids), 10) if cids else 1


def _compute_time_to_first_symptom(
    anomalies: list[dict], deploy_ts: str | None
) -> float:
    """Compute seconds from deploy to first anomaly."""
    if deploy_ts is None or not anomalies:
        return 0.0
    try:
        sorted_anomalies = sorted(
            anomalies,
            key=lambda a: a.get("event", {}).get("ts", ""),
        )
        first_anomaly_ts = parse_dt(sorted_anomalies[0]["event"]["ts"])
        deploy_dt = parse_dt(deploy_ts)
        delta = (first_anomaly_ts - deploy_dt).total_seconds()
        return max(0.0, delta)
    except Exception:
        return 0.0

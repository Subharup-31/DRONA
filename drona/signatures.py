# drona/signatures.py
from __future__ import annotations
from drona.schema import BehaviorPattern, TriggerType, SymptomType, PropagationDir, ServiceTier
from drona.identity import IdentityLayer
from drona.graph import ServiceGraph
from datetime import datetime
from dateutil.parser import parse as parse_dt
import re


def extract_signature(
    events: list[dict],
    anomalies: list[dict],
    identity_layer: IdentityLayer,
    deploy_ts: str | None = None,
    graph: ServiceGraph | None = None,
) -> BehaviorPattern:
    """Extract a service-name-agnostic behavioral signature from events and anomalies."""

    # Step 1 — trigger_type
    trigger_type = _detect_trigger(events, anomalies)

    # Step 2 — symptom_sequence (ordered by anomaly timestamp, dedup consecutive)
    symptom_sequence = _build_symptom_sequence(anomalies)

    # Step 3 — epicentre_tier and propagation_direction
    epicentre_tier = ServiceTier.UNKNOWN
    propagation_direction = PropagationDir.ISOLATED

    if anomalies and graph:
        # Find first anomaly service
        sorted_anomalies = sorted(anomalies, key=lambda a: a.get("event", {}).get("ts", ""))
        first_svc = sorted_anomalies[0].get("event", {}).get("service") or sorted_anomalies[0].get("event", {}).get("svc")
        if first_svc:
            epicentre_cid = identity_layer.resolve(first_svc)
            # Determine tier
            up = len(graph.get_upstream(epicentre_cid))
            down = len(graph.get_downstream(epicentre_cid))
            if up == 0: epicentre_tier = ServiceTier.ROOT
            elif down == 0: epicentre_tier = ServiceTier.LEAF
            else: epicentre_tier = ServiceTier.MIDDLE

            # Determine propagation direction
            all_involved = {identity_layer.resolve(a.get("event", {}).get("service") or a.get("event", {}).get("svc")) 
                            for a in anomalies if a.get("event", {}).get("service") or a.get("event", {}).get("svc")}
            if len(all_involved) > 1:
                # Check if moving downstream from epicentre
                propagation_direction = PropagationDir.DOWNSTREAM
                # Could refine more if needed
    
    # Step 4 — affected_service_count
    affected_service_count = _count_affected_services(events, anomalies, identity_layer)

    # Step 5 — time_to_first_symptom_s
    time_to_first_symptom_s = _compute_time_to_first_symptom(anomalies, deploy_ts)

    return BehaviorPattern(
        trigger_type=trigger_type,
        symptom_sequence=symptom_sequence,
        affected_service_count=affected_service_count,
        propagation_direction=propagation_direction,
        time_to_first_symptom_s=time_to_first_symptom_s,
        epicentre_tier=epicentre_tier,
    )


def _detect_trigger(events: list[dict], anomalies: list[dict]) -> TriggerType:
    """Determine trigger type from events."""
    # 1. Deploys are high-confidence triggers
    for e in events:
        if e.get("kind") == "deploy":
            return TriggerType.DEPLOY

    # 2. Dependency failures in logs
    for e in events:
        if e.get("kind") == "log":
            msg = str(e.get("msg", "")).lower()
            if any(w in msg for w in ("timeout", "connection refused", "unavailable", "unreachable")):
                return TriggerType.DEPENDENCY_FAILURE

    # 3. Explicit metric alerts
    for e in events:
        trigger = e.get("trigger", "")
        if isinstance(trigger, str) and "alert" in trigger.lower():
            return TriggerType.METRIC_ALERT

    # 4. If an anomaly is the very first thing we see without a deploy
    if anomalies:
        return TriggerType.METRIC_ALERT

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
        elif atype == "trace_slowdown" or (atype == "metric_spike" and "slow" in str(event.get("name", "")).lower()):
            raw_symptoms.append(SymptomType.TRACE_SLOWDOWN)
        elif atype == "metric_spike" and "conn" in str(event.get("name", "")).lower():
            raw_symptoms.append(SymptomType.CONNECTION_DROP)

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

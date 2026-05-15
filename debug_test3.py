#!/usr/bin/env python3
"""Debug Test 3 — check similarity score between INC-714 and INC-715."""
from drona.engine import Engine
from drona.schema import IncidentSignal
from drona.signatures import extract_signature

SAMPLE_EVENTS = [
    {"ts": "2026-05-10T14:21:30Z", "kind": "deploy", "service": "payments-svc", "version": "v2.14.0", "actor": "ci"},
    {"ts": "2026-05-10T14:22:01Z", "kind": "metric", "service": "payments-svc", "name": "latency_p99_ms", "value": 4820},
    {"ts": "2026-05-10T14:22:15Z", "kind": "log", "service": "checkout-api", "level": "error", "msg": "timeout calling payments-svc"},
    {"ts": "2026-05-10T14:23:00Z", "kind": "metric", "service": "checkout-api", "name": "error_rate_5xx", "value": 12.5},
    {"ts": "2026-05-10T14:25:00Z", "kind": "trace", "service": "checkout-api", "trace_id": "abc-123",
     "spans": [{"svc": "checkout-api", "op": "POST /checkout", "dur_ms": 5200}, {"svc": "payments-svc", "op": "charge", "dur_ms": 4900}]},
    {"ts": "2026-05-10T14:32:11Z", "kind": "incident_signal", "incident_id": "INC-714", "trigger": "alert:checkout-api/error-rate>5%", "service": "checkout-api"},
    {"ts": "2026-05-10T14:45:00Z", "kind": "remediation", "incident_id": "INC-714", "action": "rollback", "target": "payments-svc", "outcome": "resolved"},
]

SECOND_WAVE = [
    {"ts": "2026-05-11T10:00:00Z", "kind": "topology", "change": "rename", "from": "payments-svc", "to": "billing-svc"},
    {"ts": "2026-05-11T10:00:05Z", "kind": "deploy", "service": "billing-svc", "version": "v2.15.0", "actor": "ci"},
    {"ts": "2026-05-11T10:00:30Z", "kind": "metric", "service": "billing-svc", "name": "latency_p99_ms", "value": 5100},
    {"ts": "2026-05-11T10:01:00Z", "kind": "log", "service": "checkout-api", "level": "error", "msg": "timeout calling billing-svc"},
    {"ts": "2026-05-11T10:01:30Z", "kind": "incident_signal", "incident_id": "INC-715", "trigger": "alert:checkout-api/error-rate>5%", "service": "checkout-api"},
]

engine = Engine()
engine.ingest(SAMPLE_EVENTS)
engine.ingest(SECOND_WAVE[:3])

# Check what INC-714's stored signature looks like
print(f"Stored incidents: {len(engine._memory._incidents)}")
for mem in engine._memory._incidents:
    print(f"  {mem.incident_id}: trigger={mem.signature.trigger_type}, symptoms={mem.signature.symptom_sequence}, prop={mem.signature.propagation_direction}")

# Build current signal's signature
signal2 = IncidentSignal("INC-715", "alert:checkout-api/error-rate>5%", "2026-05-11T10:01:30Z")
ctx2 = engine.reconstruct_context(signal2, mode="fast")

print(f"\nRelated events: {len(ctx2['related_events'])}")
print(f"Similar past: {ctx2['similar_past_incidents']}")

# Manual similarity check
if engine._memory._incidents:
    mem714 = engine._memory._incidents[0]
    from drona.signatures import extract_signature
    from dateutil.parser import parse as parse_dt
    from datetime import timedelta
    
    ts = parse_dt(signal2.ts)
    window_start = ts - timedelta(minutes=15)
    window_end = ts + timedelta(minutes=2)
    raw_events = engine._index.query_window_all(window_start, window_end)
    anomalies = engine._index.get_anomalies(ts - timedelta(minutes=30), ts + timedelta(minutes=5))
    
    svc_raw = signal2.service or "__unknown__"
    primary_cid = engine._identity.resolve(svc_raw)
    deploy_ts = next((e["ts"] for e in raw_events if e.get("kind") == "deploy"), None)
    
    sig2 = extract_signature(raw_events, anomalies, engine._identity, deploy_ts, engine._graph, primary_cid)
    print(f"\nCurrent sig: trigger={sig2.trigger_type}, symptoms={sig2.symptom_sequence}, prop={sig2.propagation_direction}")
    
    base_sim = sig2.similarity(mem714.signature)
    print(f"Base similarity: {base_sim}")

engine.close()

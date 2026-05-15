#!/usr/bin/env python3
# self_check.py — Drona local test harness. 6 tests. No bench repo required.
from __future__ import annotations
import sys
import time
import random

from drona.engine import Engine
from drona.schema import IncidentSignal
from drona.identity import IdentityLayer


# ─── SAMPLE EVENTS ────────────────────────────────────────────────────────────

SAMPLE_EVENTS = [
    {
        "ts": "2026-05-10T14:21:30Z",
        "kind": "deploy",
        "service": "payments-svc",
        "version": "v2.14.0",
        "actor": "ci",
    },
    {
        "ts": "2026-05-10T14:22:01Z",
        "kind": "metric",
        "service": "payments-svc",
        "name": "latency_p99_ms",
        "value": 4820,
    },
    {
        "ts": "2026-05-10T14:22:15Z",
        "kind": "log",
        "service": "checkout-api",
        "level": "error",
        "msg": "timeout calling payments-svc",
    },
    {
        "ts": "2026-05-10T14:23:00Z",
        "kind": "metric",
        "service": "checkout-api",
        "name": "error_rate_5xx",
        "value": 12.5,
    },
    {
        "ts": "2026-05-10T14:25:00Z",
        "kind": "trace",
        "service": "checkout-api",
        "trace_id": "abc-123",
        "spans": [
            {"svc": "checkout-api", "op": "POST /checkout", "dur_ms": 5200},
            {"svc": "payments-svc", "op": "charge", "dur_ms": 4900},
        ],
    },
    {
        "ts": "2026-05-10T14:32:11Z",
        "kind": "incident_signal",
        "incident_id": "INC-714",
        "trigger": "alert:checkout-api/error-rate>5%",
        "service": "checkout-api",
    },
    {
        "ts": "2026-05-10T14:45:00Z",
        "kind": "remediation",
        "incident_id": "INC-714",
        "action": "rollback",
        "target": "payments-svc",
        "outcome": "resolved",
    },
]

# Second wave: same pattern but service renamed to billing-svc
SECOND_WAVE = [
    {
        "ts": "2026-05-11T10:00:00Z",
        "kind": "topology",
        "change": "rename",
        "from": "payments-svc",
        "to": "billing-svc",
    },
    {
        "ts": "2026-05-11T10:00:05Z",
        "kind": "deploy",
        "service": "billing-svc",
        "version": "v2.15.0",
        "actor": "ci",
    },
    {
        "ts": "2026-05-11T10:00:30Z",
        "kind": "metric",
        "service": "billing-svc",
        "name": "latency_p99_ms",
        "value": 5100,
    },
    {
        "ts": "2026-05-11T10:01:00Z",
        "kind": "log",
        "service": "checkout-api",
        "level": "error",
        "msg": "timeout calling billing-svc",
    },
    {
        "ts": "2026-05-11T10:01:30Z",
        "kind": "incident_signal",
        "incident_id": "INC-715",
        "trigger": "alert:checkout-api/error-rate>5%",
        "service": "checkout-api",
    },
]


# ─── TEST RUNNER ──────────────────────────────────────────────────────────────

def main() -> None:
    """Run all 6 self-check tests."""
    passed = 0
    failed = 0
    total = 6

    print("═══ DRONA SELF CHECK ═══")
    print()

    # TEST 1 — Identity rename
    try:
        il = IdentityLayer()
        cid1 = il.resolve("payments-svc")
        il.handle_rename("payments-svc", "billing-svc")
        cid2 = il.resolve("billing-svc")
        assert cid1 == cid2, "rename broke canonical_id"
        assert il.current_name(cid1) == "billing-svc"
        print("TEST 1  PASS  Identity rename")
        passed += 1
    except Exception as exc:
        print(f"TEST 1  FAIL  Identity rename — {exc}")
        failed += 1

    # TEST 2 — Canonical context reconstruction
    try:
        engine = Engine()
        engine.ingest(SAMPLE_EVENTS[:5])  # everything before incident_signal
        signal = IncidentSignal(
            "INC-714", "alert:checkout-api/error-rate>5%", "2026-05-10T14:32:11Z"
        )
        t0 = time.time()
        ctx = engine.reconstruct_context(signal, mode="fast")
        latency_ms = (time.time() - t0) * 1000
        assert len(ctx["related_events"]) > 0, "no related events"
        assert any(
            e.get("kind") == "deploy" for e in ctx["related_events"]
        ), "deploy not in related_events"
        assert len(ctx["causal_chain"]) > 0, "no causal chain"
        assert ctx["causal_chain"][0].confidence >= 0.5, (
            f"low confidence: {ctx['causal_chain'][0].confidence}"
        )
        assert latency_ms < 2000, f"fast mode {latency_ms:.0f}ms > 2000ms"
        assert "_provenance" in ctx["related_events"][0], "missing provenance"
        print(f"TEST 2  PASS  Context reconstruction ({latency_ms:.0f}ms)")
        passed += 1
        engine.close()
    except Exception as exc:
        print(f"TEST 2  FAIL  Context reconstruction — {exc}")
        failed += 1

    # TEST 3 — Rename robustness (THE KEY TEST)
    try:
        engine2 = Engine()
        engine2.ingest(SAMPLE_EVENTS)  # full first wave including remediation
        engine2.ingest(SECOND_WAVE[:3])  # second wave up to but not including incident
        signal2 = IncidentSignal(
            "INC-715", "alert:checkout-api/error-rate>5%", "2026-05-11T10:01:30Z"
        )
        ctx2 = engine2.reconstruct_context(signal2, mode="fast")
        matched = [m.past_incident_id for m in ctx2["similar_past_incidents"]]
        assert "INC-714" in matched, f"rename robustness. Got: {matched}"
        print(f"TEST 3  PASS  Rename robustness — INC-714 found in {matched}")
        passed += 1
        engine2.close()
    except Exception as exc:
        print(f"TEST 3  FAIL  Rename robustness — {exc}")
        failed += 1

    # TEST 4 — Ingest throughput ≥ 1000/sec
    try:
        events_load = [
            {
                "ts": f"2026-05-10T12:{i // 60:02d}:{i % 60:02d}Z",
                "kind": "metric",
                "service": f"svc-{i % 8}",
                "name": "latency_p99_ms",
                "value": random.randint(100, 6000),
            }
            for i in range(1000)
        ]
        engine3 = Engine()
        t0 = time.time()
        engine3.ingest(events_load)
        elapsed = time.time() - t0
        rate = 1000 / elapsed if elapsed > 0 else float("inf")
        assert rate >= 1000, f"{rate:.0f} events/sec < 1000"
        print(f"TEST 4  PASS  Throughput: {rate:.0f} events/sec")
        passed += 1
        engine3.close()
    except Exception as exc:
        print(f"TEST 4  FAIL  Throughput — {exc}")
        failed += 1

    # TEST 5 — Window expansion on empty
    try:
        engine4 = Engine()
        engine4.ingest(
            [
                {
                    "ts": "2026-05-10T14:00:00Z",
                    "kind": "deploy",
                    "service": "orphan-svc",
                    "version": "v1.0",
                    "actor": "ci",
                }
            ]
        )
        signal3 = IncidentSignal(
            "INC-999", "alert:orphan-svc/latency", "2026-05-10T18:00:00Z"
        )
        ctx3 = engine4.reconstruct_context(signal3, mode="fast")
        assert isinstance(ctx3["related_events"], list)
        assert isinstance(ctx3["explain"], str) and len(ctx3["explain"]) > 0
        print("TEST 5  PASS  Window expansion on empty")
        passed += 1
        engine4.close()
    except Exception as exc:
        print(f"TEST 5  FAIL  Window expansion — {exc}")
        failed += 1

    # TEST 6 — Dependency shift topology
    try:
        engine5 = Engine()
        engine5.ingest(
            [
                {
                    "ts": "2026-05-10T10:00:00Z",
                    "kind": "topology",
                    "change": "dependency_add",
                    "from": "checkout-api",
                    "to": "payments-svc",
                },
                {
                    "ts": "2026-05-10T11:00:00Z",
                    "kind": "topology",
                    "change": "rename",
                    "from": "payments-svc",
                    "to": "billing-svc",
                },
            ]
        )
        cid_pay = engine5._identity.resolve("payments-svc")
        cid_bill = engine5._identity.resolve("billing-svc")
        assert cid_pay == cid_bill, "rename not tracked after dependency_add"
        print("TEST 6  PASS  Dependency shift topology")
        passed += 1
        engine5.close()
    except Exception as exc:
        print(f"TEST 6  FAIL  Dependency shift — {exc}")
        failed += 1

    # Summary
    print()
    print(f"═══ {passed}/{total} passed ═══")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()

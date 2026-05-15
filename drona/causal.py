# drona/causal.py
from __future__ import annotations
from drona.schema import CausalEdge, Event
from drona.identity import IdentityLayer
from dateutil.parser import parse as parse_dt
import re


def build_causal_chain(
    events: list[dict],
    anomalies: list[dict],
    identity_layer: IdentityLayer,
) -> list[CausalEdge]:
    """Build causal chain using 3 deterministic rules. No LLM."""
    edges: list[CausalEdge] = []

    # RULE 1 — Deploy → Metric/Trace Anomaly within 5 minutes
    _rule_deploy_to_anomaly(events, anomalies, identity_layer, edges)

    # RULE 2 — Upstream Timeout Log → Caller
    _rule_timeout_log(events, identity_layer, edges)

    # RULE 3 — Trace Span Slowdown → Caller
    _rule_trace_slowdown(events, identity_layer, edges)

    # POST-PROCESSING: deduplicate, remove self-loops, sort by confidence
    return _deduplicate(edges)


def _rule_deploy_to_anomaly(
    events: list[dict],
    anomalies: list[dict],
    identity_layer: IdentityLayer,
    edges: list[CausalEdge],
) -> None:
    """Deploy → Metric/Trace Anomaly within 5 minutes (confidence 0.85–0.95)."""
    deploys = [e for e in events if e.get("kind") == "deploy"]
    for d in deploys:
        svc = d.get("service") or d.get("svc", "")
        if not svc:
            continue
        deploy_cid = identity_layer.resolve(svc)
        try:
            deploy_ts = parse_dt(d["ts"])
        except Exception:
            continue

        for a in anomalies:
            if a.get("type") not in ("metric_spike", "trace_slowdown"):
                continue
            try:
                a_ts = parse_dt(a["event"]["ts"])
            except Exception:
                continue
            delta = (a_ts - deploy_ts).total_seconds()
            if 0 < delta < 300:
                confidence = min(0.95, 0.85 + (1 - delta / 300) * 0.10)
                a_svc = a["event"].get("service") or a["event"].get("svc", "")
                effect_cid = identity_layer.resolve(a_svc) if a_svc else deploy_cid
                edges.append(
                    CausalEdge(
                        cause_id=deploy_cid,
                        effect_id=effect_cid,
                        evidence=[d, a["event"]],
                        confidence=round(confidence, 4),
                        relationship="causes",
                    )
                )


def _rule_timeout_log(
    events: list[dict],
    identity_layer: IdentityLayer,
    edges: list[CausalEdge],
) -> None:
    """Upstream Timeout Log → Caller (confidence 0.75)."""
    logs = [
        e for e in events
        if e.get("kind") == "log" and e.get("level") == "error"
    ]
    for log_event in logs:
        msg = str(log_event.get("msg", "")).lower()
        if not any(w in msg for w in ("timeout", "connection refused", "unavailable", "unreachable")):
            continue
        svc = log_event.get("service") or log_event.get("svc", "")
        if not svc:
            continue
        caller_cid = identity_layer.resolve(svc)
        callee_name = _extract_callee_from_msg(log_event.get("msg", ""))
        if callee_name:
            callee_cid = identity_layer.resolve(callee_name)
            if callee_cid != caller_cid:
                edges.append(
                    CausalEdge(
                        cause_id=callee_cid,
                        effect_id=caller_cid,
                        evidence=[log_event],
                        confidence=0.75,
                        relationship="causes",
                    )
                )


def _rule_trace_slowdown(
    events: list[dict],
    identity_layer: IdentityLayer,
    edges: list[CausalEdge],
) -> None:
    """Trace Span Slowdown → Caller (confidence 0.80)."""
    traces = [e for e in events if e.get("kind") == "trace"]
    for trace in traces:
        spans = trace.get("spans", [])
        for i in range(len(spans) - 1):
            downstream = spans[i + 1]
            upstream = spans[i]
            if downstream.get("dur_ms", 0) > 3000:
                cause_svc = downstream.get("svc", "")
                effect_svc = upstream.get("svc", "")
                if not cause_svc or not effect_svc:
                    continue
                cause_cid = identity_layer.resolve(cause_svc)
                effect_cid = identity_layer.resolve(effect_svc)
                if cause_cid != effect_cid:
                    edges.append(
                        CausalEdge(
                            cause_id=cause_cid,
                            effect_id=effect_cid,
                            evidence=[trace],
                            confidence=0.80,
                            relationship="causes",
                        )
                    )


def _deduplicate(edges: list[CausalEdge]) -> list[CausalEdge]:
    """Deduplicate by (cause_id, effect_id) — keep highest confidence. Remove self-loops."""
    best: dict[tuple[str, str], CausalEdge] = {}
    for edge in edges:
        if edge.cause_id == edge.effect_id:
            continue
        key = (edge.cause_id, edge.effect_id)
        if key not in best or edge.confidence > best[key].confidence:
            best[key] = edge
    result = sorted(best.values(), key=lambda e: e.confidence, reverse=True)
    return result


def _extract_callee_from_msg(msg: str) -> str | None:
    """Try to find service names embedded in error messages."""
    patterns = [
        r"calling ([a-z][a-z0-9\-]+(?:-svc|-api|-service|-gateway))",
        r"connect(?:ion)? to ([a-z][a-z0-9\-]+(?:-svc|-api|-service|-gateway))",
        r"([a-z][a-z0-9\-]+(?:-svc|-api|-service|-gateway)) (?:timed out|unreachable|unavailable)",
    ]
    for p in patterns:
        m = re.search(p, msg, re.IGNORECASE)
        if m:
            return m.group(1)
    # Fallback: any token with service-like suffix
    tokens = re.findall(
        r"[a-z][a-z0-9\-]+(?:-svc|-api|-service|-gateway)", msg, re.IGNORECASE
    )
    return tokens[0].lower() if tokens else None

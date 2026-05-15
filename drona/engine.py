# drona/engine.py
from __future__ import annotations
from drona.schema import (
    Event, IncidentSignal, Context, CausalEdge,
    IncidentMatch, Remediation, BehaviorPattern,
)
from drona.identity import IdentityLayer
from drona.temporal_index import TemporalIndex
from drona.memory import MemoryStore
from drona.causal import build_causal_chain
from drona.signatures import extract_signature
from drona.graph import ServiceGraph
from drona.explainer import generate_explain
from datetime import datetime, timedelta
from dateutil.parser import parse as parse_dt
from typing import Iterable, Literal
import threading
import re


class Engine:
    """Main Drona engine. Thread-safe. One instance per benchmark seed."""

    def __init__(self) -> None:
        self._identity = IdentityLayer()
        self._index = TemporalIndex()
        self._memory = MemoryStore()
        self._graph = ServiceGraph()
        self._lock = threading.RLock()
        self._batch_buffer: list[tuple] = []
        self._BATCH_SIZE = 50

    def ingest(self, events: Iterable[Event]) -> None:
        """Consume event stream. Batch-inserts to DuckDB every 50 events."""
        for event in events:
            row = self._process_event(event)
            if row is not None:
                self._batch_buffer.append(row)
                if len(self._batch_buffer) >= self._BATCH_SIZE:
                    self._index.insert_batch(self._batch_buffer)
                    self._batch_buffer.clear()
        if self._batch_buffer:
            self._index.insert_batch(self._batch_buffer)
            self._batch_buffer.clear()

    def _flush_buffer(self) -> None:
        """Flush pending events to DuckDB so queries see them."""
        if self._batch_buffer:
            self._index.insert_batch(self._batch_buffer)
            self._batch_buffer.clear()

    def _process_event(self, event: Event) -> tuple | None:
        """Process one event. Returns DuckDB row tuple or None."""
        kind = event.get("kind", "")

        # G1: Handle ALL topology event types, not just rename
        if kind == "topology":
            change = event.get("change", "")
            if change == "rename":
                self._identity.handle_rename(
                    event.get("from", ""), event.get("to", "")
                )
            elif change in ("dependency_add", "link", "add"):
                src = event.get("from") or event.get("source", "")
                dst = event.get("to") or event.get("target", "")
                if src and dst:
                    src_cid, dst_cid = self._identity.handle_dependency_shift(
                        src, dst, change, event.get("ts", "")
                    )
                    self._graph.record_call(src_cid, dst_cid, event.get("ts", ""))
            elif change in ("dependency_remove", "unlink", "remove"):
                src = event.get("from") or event.get("source", "")
                dst = event.get("to") or event.get("target", "")
                if src and dst:
                    src_cid = self._identity.resolve(src)
                    dst_cid = self._identity.resolve(dst)
                    self._graph.remove_dependency(src_cid, dst_cid)
            return None  # topology events never stored in temporal index

        # Resolve service to canonical_id
        svc_raw = (
            event.get("service")
            or event.get("svc")
            or self._extract_svc_from_trigger(event.get("trigger", ""))
            or "__unknown__"
        )
        cid = self._identity.resolve(svc_raw)
        ts = parse_dt(event["ts"])

        # Track deploy windows
        if kind == "deploy":
            pass  # temporal index stores it; memory store reads it from query

        # Open incident
        elif kind == "incident_signal":
            self._flush_buffer()
            window_start = ts - timedelta(minutes=15)
            pre_events = self._index.query_window_all(window_start, ts)
            # Find most recent deploy in pre-window
            deploy_ts = None
            for e in pre_events:
                if e.get("kind") == "deploy":
                    deploy_ts = e["ts"]
                    break
            self._memory.open_incident(
                event.get("incident_id", ""), event["ts"], pre_events, cid
            )
            if deploy_ts:
                with self._lock:
                    iid = event.get("incident_id", "")
                    if iid in self._memory._open:
                        self._memory._open[iid]["deploy_ts"] = deploy_ts

        # Close incident
        elif kind == "remediation":
            self._flush_buffer()
            iid = event.get("incident_id", "")
            if iid in self._memory._open:
                state = self._memory._open[iid]
                opened_ts = parse_dt(state["opened_at"])
                anomalies = self._index.get_anomalies(
                    opened_ts - timedelta(minutes=10), ts
                )
                self._memory.close_incident(iid, event, anomalies, self._identity, self._graph)

        return self._index.build_row(cid, event, ts)

    def reconstruct_context(
        self,
        signal: IncidentSignal,
        mode: Literal["fast", "deep"] = "fast",
    ) -> Context:
        """Reconstruct incident context. fast < 2s p95. deep < 6s p95."""
        ts = parse_dt(signal.ts)
        window_start = ts - timedelta(minutes=15)
        window_end = ts + timedelta(minutes=2)

        # 1. Collect window events
        raw_events = self._index.query_window_all(window_start, window_end)

        # G2: Expand window if empty
        if not raw_events:
            raw_events = self._index.query_window_all(
                ts - timedelta(minutes=30),
                ts + timedelta(minutes=5),
            )

        anomalies = self._index.get_anomalies(
            ts - timedelta(minutes=30), ts + timedelta(minutes=5)
        )

        # 2. Rank + deduplicate related events, add provenance (G3)
        related = self._rank_related(raw_events, anomalies, signal)

        # 3. Causal chain
        chain = build_causal_chain(related, anomalies, self._identity)
        self._graph.add_causal_edges(chain)

        # 4. Behavioral signature — uses topology roles, not service names
        svc_raw = (
            signal.service
            or self._extract_svc_from_trigger(signal.trigger)
            or "__unknown__"
        )
        primary_cid = self._identity.resolve(svc_raw)
        deploy_ts = next(
            (e["ts"] for e in related if e.get("kind") == "deploy"), None
        )
        sig = extract_signature(
            related, anomalies, self._identity, deploy_ts,
            self._graph, primary_cid,
        )

        # 5. Similar past incidents (topology-independent) — G4: query_ts for recency decay
        scored = self._memory.find_similar(sig, top_k=5, query_ts=signal.ts)
        similar = [
            IncidentMatch(
                past_incident_id=mem.incident_id,
                similarity=score,
                rationale=self._explain_match(sig, mem.signature),
            )
            for score, mem in scored
        ]

        # 6. Remediation suggestions
        remediations = list(
            self._memory.get_remediation_suggestions(scored, self._identity)
        )

        # 7. Confidence
        confidence = self._compute_confidence(chain, similar)

        # 8. Explain
        explain = generate_explain(related, chain, similar, mode, self._identity)

        return Context(
            related_events=related,
            causal_chain=chain,
            similar_past_incidents=similar,
            suggested_remediations=remediations,
            confidence=confidence,
            explain=explain,
        )

    def _rank_related(
        self, events: list, anomalies: list, signal: IncidentSignal
    ) -> list[Event]:
        """Rank by relevance, deduplicate, add _provenance field. (G3)"""
        anomaly_ts_set = {a["event"]["ts"] for a in anomalies}

        def score(e: dict) -> int:
            """Score an event by relevance."""
            s = 0
            k = e.get("kind", "")
            if k == "deploy":
                s += 10
            if k == "metric" and e.get("ts") in anomaly_ts_set:
                s += 9
            if k == "log" and e.get("level") == "error":
                s += 8
            if k == "trace":
                s += 6
            if k == "metric":
                s += 3
            if k == "log":
                s += 2
            return s

        seen: set = set()
        deduped: list = []
        for e in sorted(events, key=score, reverse=True):
            key = f"{e.get('ts', '')}:{e.get('service', '')}{e.get('svc', '')}:{e.get('kind', '')}"
            if key not in seen:
                seen.add(key)
                e["_provenance"] = {
                    "relevance_score": score(e),
                    "is_anomaly": e.get("ts", "") in anomaly_ts_set,
                    "source_ts": e.get("ts", ""),
                }
                deduped.append(e)
        return deduped

    def _explain_match(
        self, current: BehaviorPattern, past: BehaviorPattern
    ) -> str:
        """Human-readable rationale for why two incidents matched."""
        parts = []
        if current.trigger_type == past.trigger_type:
            parts.append(f"same trigger ({current.trigger_type.value})")
        overlap = set(current.symptom_sequence) & set(past.symptom_sequence)
        if overlap:
            parts.append(
                f"shared symptoms: {', '.join(sorted(overlap))}"
            )
        if current.propagation_direction == past.propagation_direction:
            parts.append(
                f"same propagation ({current.propagation_direction.value})"
            )
        return "; ".join(parts) if parts else "behavioral pattern similarity"

    def _compute_confidence(
        self, chain: list, similar: list
    ) -> float:
        """Overall confidence: 0.0–1.0."""
        c = 0.0
        if chain:
            c += min(0.4, len(chain) * 0.12)
            c += chain[0].confidence * 0.2
        if similar:
            c += similar[0].similarity * 0.4
        return round(min(1.0, c), 3)

    def _extract_svc_from_trigger(self, trigger: str) -> str | None:
        """G5: Robust service extraction from trigger strings."""
        if not trigger:
            return None
        patterns = [
            r"alert:([^/\[\]]+)/",
            r"alert\[([^\]]+)\]",
            r"^([a-z][a-z0-9\-]+):",
        ]
        for p in patterns:
            m = re.search(p, trigger, re.IGNORECASE)
            if m:
                return m.group(1)
        tokens = re.findall(
            r"[a-z][a-z0-9\-]+(?:-svc|-api|-service|-gateway)",
            trigger,
            re.IGNORECASE,
        )
        return tokens[0].lower() if tokens else None

    def close(self) -> None:
        """Release DuckDB connection."""
        self._index.close()

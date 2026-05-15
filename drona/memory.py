# drona/memory.py
from __future__ import annotations
from drona.schema import (
    IncidentMemory, BehaviorPattern, IncidentMatch, Remediation
)
from drona.signatures import extract_signature
from drona.identity import IdentityLayer
from dateutil.parser import parse as parse_dt
import threading


class MemoryStore:
    """Incident lifecycle manager with recency-decayed similarity search."""

    def __init__(self) -> None:
        self._incidents: list[IncidentMemory] = []
        self._open: dict[str, dict] = {}
        self._lock = threading.RLock()

    def open_incident(
        self,
        incident_id: str,
        ts: str,
        initial_events: list,
        primary_cid: str,
    ) -> None:
        """Open a new incident with initial event context."""
        with self._lock:
            state = {
                "opened_at": ts,
                "events": list(initial_events),
                "deploy_ts": None,
                "primary_cid": primary_cid,
            }
            self._open[incident_id] = state

    def update_open(self, incident_id: str, events: list[dict]) -> None:
        """Append events to an open incident."""
        with self._lock:
            if incident_id in self._open:
                self._open[incident_id]["events"].extend(events)
                for event in events:
                    if (
                        event.get("kind") == "deploy"
                        and self._open[incident_id]["deploy_ts"] is None
                    ):
                        self._open[incident_id]["deploy_ts"] = event["ts"]

    def close_incident(
        self,
        incident_id: str,
        remediation_event: dict,
        anomalies: list[dict],
        identity_layer: IdentityLayer,
    ) -> IncidentMemory | None:
        """Close an incident and store it as memory."""
        with self._lock:
            state = self._open.pop(incident_id, None)
            if state is None:
                return None

            sig = extract_signature(
                state["events"], anomalies, identity_layer, state["deploy_ts"]
            )
            target_svc = remediation_event.get("target", "")
            target_cid = (
                identity_layer.resolve(target_svc)
                if target_svc
                else state["primary_cid"]
            )

            mem = IncidentMemory(
                incident_id=incident_id,
                signature=sig,
                epicentre_canonical_id=state["primary_cid"],
                remediation_action=remediation_event.get("action", "unknown"),
                remediation_target_cid=target_cid,
                outcome=remediation_event.get("outcome", "unknown"),
                opened_at=state["opened_at"],
                closed_at=remediation_event.get("ts", ""),
                context_events=state["events"],
            )
            self._incidents.append(mem)
            return mem

    def find_similar(
        self,
        signature: BehaviorPattern,
        top_k: int = 5,
        query_ts: str | None = None,
    ) -> list[tuple[float, IncidentMemory]]:
        """Find similar past incidents with recency decay (G4)."""
        with self._lock:
            scored: list[tuple[float, IncidentMemory]] = []
            for mem in self._incidents:
                base_sim = signature.similarity(mem.signature)
                if base_sim <= 0.25:
                    continue

                # G4: recency decay — half-life 3 simulated days, affects 30% of score
                sim = base_sim
                if query_ts and mem.closed_at:
                    try:
                        age_days = (
                            parse_dt(query_ts) - parse_dt(mem.closed_at)
                        ).total_seconds() / 86400
                        decay = 0.5 ** (age_days / 3.0)
                        sim = base_sim * (0.70 + 0.30 * decay)
                    except Exception:
                        sim = base_sim

                scored.append((round(sim, 4), mem))

            scored.sort(key=lambda x: x[0], reverse=True)
            return scored[:top_k]

    def get_remediation_suggestions(
        self,
        similar: list[tuple[float, IncidentMemory]],
        identity_layer: IdentityLayer,
    ) -> list[Remediation]:
        """Generate remediation suggestions from similar past incidents."""
        results: list[Remediation] = []
        for score, mem in similar[:3]:
            try:
                target_name = identity_layer.current_name(mem.remediation_target_cid)
            except Exception:
                target_name = mem.remediation_target_cid
            outcome_mult = 0.9 if mem.outcome == "resolved" else 0.4
            confidence = round(score * outcome_mult, 3)
            results.append(
                Remediation(
                    action=mem.remediation_action,
                    target=target_name,
                    historical_outcome=mem.outcome,
                    confidence=confidence,
                )
            )
        return results

    def incident_count(self) -> int:
        """Number of closed incidents in memory."""
        return len(self._incidents)

    def open_count(self) -> int:
        """Number of currently open incidents."""
        return len(self._open)

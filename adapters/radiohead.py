# adapters/radiohead.py — Anvil P·02 bench adapter for team radiohead
from __future__ import annotations
import sys
import os

# Add project root to path so drona package is importable
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from drona.engine import Engine as _Engine
from drona.schema import IncidentSignal as _DronaSignal

# Import bench harness base class — available when running inside bench repo
try:
    from adapter import Adapter
except ImportError:
    # Fallback: define minimal base if running outside bench repo
    class Adapter:  # type: ignore[no-redef]
        """Minimal stub for standalone testing."""
        def ingest(self, events):
            raise NotImplementedError
        def reconstruct_context(self, signal, mode="fast"):
            raise NotImplementedError
        def close(self):
            pass


class Engine(Adapter):
    """Thin shim mapping bench harness interface to drona Engine."""

    def __init__(self) -> None:
        self._e = _Engine()

    def ingest(self, events) -> None:
        """Ingest events — convert bench Event dicts to drona format."""
        # Bench events are dicts or Event dataclass instances
        converted = []
        for ev in events:
            if isinstance(ev, dict):
                converted.append(ev)
            else:
                # Convert dataclass/namedtuple to dict
                converted.append(
                    ev.__dict__ if hasattr(ev, "__dict__") else dict(ev)
                )
        self._e.ingest(converted)

    def reconstruct_context(self, signal, mode: str = "fast") -> dict:
        """Map bench IncidentSignal to drona IncidentSignal, return Context."""
        # Build drona signal — handle both dict and dataclass inputs
        if isinstance(signal, dict):
            drona_signal = _DronaSignal(
                incident_id=signal.get("incident_id", ""),
                trigger=signal.get("trigger", ""),
                ts=signal.get("ts", ""),
                service=signal.get("service"),
            )
        else:
            drona_signal = _DronaSignal(
                incident_id=getattr(signal, "incident_id", ""),
                trigger=getattr(signal, "trigger", ""),
                ts=getattr(signal, "ts", ""),
                service=getattr(signal, "service", None),
            )

        ctx = self._e.reconstruct_context(drona_signal, mode)

        # Convert Context TypedDict to plain dict for bench harness
        # Map causal_chain CausalEdge dataclasses to dicts
        causal_chain = []
        for edge in ctx.get("causal_chain", []):
            if hasattr(edge, "__dict__"):
                causal_chain.append({
                    "cause_id": edge.cause_id,
                    "effect_id": edge.effect_id,
                    "evidence": edge.evidence,
                    "confidence": edge.confidence,
                    "relationship": edge.relationship,
                })
            else:
                causal_chain.append(edge)

        # Map similar_past_incidents IncidentMatch dataclasses to dicts
        similar = []
        for m in ctx.get("similar_past_incidents", []):
            if hasattr(m, "__dict__"):
                similar.append({
                    "past_incident_id": m.past_incident_id,
                    "similarity": m.similarity,
                    "rationale": m.rationale,
                })
            else:
                similar.append(m)

        # Map suggested_remediations Remediation dataclasses to dicts
        remediations = []
        for r in ctx.get("suggested_remediations", []):
            if hasattr(r, "__dict__"):
                remediations.append({
                    "action": r.action,
                    "target": r.target,
                    "historical_outcome": r.historical_outcome,
                    "confidence": r.confidence,
                })
            else:
                remediations.append(r)

        return {
            "related_events": ctx.get("related_events", []),
            "causal_chain": causal_chain,
            "similar_past_incidents": similar,
            "suggested_remediations": remediations,
            "confidence": ctx.get("confidence", 0.0),
            "explain": ctx.get("explain", ""),
        }

    def close(self) -> None:
        """Release resources."""
        self._e.close()

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
    # pyrefly: ignore [missing-import]
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
    """Thin shim mapping bench harness interface to drona Engine.

    Key translations:
    - Bench topology events use `from_` (with underscore); drona uses `from`.
    - Bench CausalEdge uses `cause_event_id`/`effect_event_id` (str);
      drona uses `cause_id`/`effect_id`.
    - Bench CausalEdge.evidence is str; drona stores list[Event].
    - Bench IncidentMatch uses `incident_id`; drona uses `past_incident_id`.
    """

    def __init__(self) -> None:
        self._e = _Engine()

    def ingest(self, events) -> None:
        """Ingest events — normalize bench field names to drona format."""
        converted = []
        for ev in events:
            if isinstance(ev, dict):
                d = dict(ev)
            else:
                d = ev.__dict__ if hasattr(ev, "__dict__") else dict(ev)

            # Bench topology events use `from_` (with underscore)
            # Drona engine expects `from` (without underscore)
            if d.get("kind") == "topology" and "from_" in d:
                d["from"] = d.pop("from_")

            converted.append(d)
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

        # Convert causal_chain to bench schema:
        #   bench expects: cause_event_id (str), effect_event_id (str),
        #                  evidence (str), confidence (float)
        causal_chain = []
        for edge in ctx.get("causal_chain", []):
            if hasattr(edge, "cause_id"):
                # Convert evidence list to a summary string
                ev_str = ""
                if edge.evidence:
                    parts = []
                    for e in edge.evidence[:2]:
                        if isinstance(e, dict):
                            parts.append(
                                f"{e.get('kind', '?')}@{e.get('ts', '?')}"
                            )
                    ev_str = "; ".join(parts)
                causal_chain.append({
                    "cause_event_id": edge.cause_id,
                    "effect_event_id": edge.effect_id,
                    "evidence": ev_str,
                    "confidence": edge.confidence,
                })
            else:
                causal_chain.append(edge)

        # Convert similar_past_incidents to bench schema:
        #   bench expects: incident_id (str), similarity (float), rationale (str)
        similar = []
        for m in ctx.get("similar_past_incidents", []):
            if hasattr(m, "past_incident_id"):
                similar.append({
                    "incident_id": m.past_incident_id,
                    "similarity": m.similarity,
                    "rationale": m.rationale,
                })
            else:
                similar.append(m)

        # Convert suggested_remediations to bench schema
        remediations = []
        for r in ctx.get("suggested_remediations", []):
            if hasattr(r, "action"):
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

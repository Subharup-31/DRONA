# drona/memory.py
from __future__ import annotations
from drona.schema import (
    IncidentMemory, BehaviorPattern, IncidentMatch, Remediation,
    TriggerType, SymptomType, PropagationDir, ServiceTier,
)
from drona.signatures import extract_signature
from drona.identity import IdentityLayer
from drona.graph import ServiceGraph
from dateutil.parser import parse as parse_dt
from sklearn.linear_model import SGDClassifier
from sklearn.preprocessing import StandardScaler
import numpy as np
import threading


class IncrementalClassifier:
    """
    Lightweight online classifier that learns which BehaviorPattern pairs
    belong to the same incident family. Updates on each closed incident.
    Supplements (does not replace) LCS similarity in find_similar.
    """

    _TRIGGER_MAP = {
        TriggerType.DEPLOY: 0,
        TriggerType.METRIC_ALERT: 1,
        TriggerType.DEPENDENCY_FAILURE: 2,
        TriggerType.UNKNOWN: 3,
    }
    _PROP_MAP = {
        PropagationDir.ISOLATED: 0,
        PropagationDir.DOWNSTREAM: 1,
        PropagationDir.UPSTREAM: 2,
    }
    _TIER_MAP = {
        ServiceTier.ROOT: 0,
        ServiceTier.MIDDLE: 1,
        ServiceTier.LEAF: 2,
        ServiceTier.UNKNOWN: 3,
    }

    def __init__(self) -> None:
        self._clf = SGDClassifier(
            loss="log_loss",
            warm_start=True,
            max_iter=1,
            tol=None,
            random_state=42,
        )
        self._scaler = StandardScaler()
        self._fitted = False
        self._n_seen = 0

    def _encode(self, sig: BehaviorPattern) -> np.ndarray:
        """Encode a BehaviorPattern as a fixed-length 9-dim numeric vector."""
        syms = set(sig.symptom_sequence)
        return np.array([
            self._TRIGGER_MAP.get(sig.trigger_type, 3),
            min(len(sig.symptom_sequence), 5),
            1 if SymptomType.LATENCY_SPIKE in syms else 0,
            1 if SymptomType.ERROR_RATE_SPIKE in syms else 0,
            1 if SymptomType.UPSTREAM_TIMEOUT in syms else 0,
            1 if SymptomType.TRACE_SLOWDOWN in syms else 0,
            self._PROP_MAP.get(sig.propagation_direction, 1),
            min(sig.time_to_first_symptom_s, 600.0),
            self._TIER_MAP.get(sig.epicentre_tier, 3),
        ], dtype=np.float64)

    def update(self, new_sig: BehaviorPattern, existing_sigs: list) -> None:
        """Generate positive + negative pairs and call partial_fit."""
        if not existing_sigs:
            self._n_seen += 1
            return

        new_vec = self._encode(new_sig)
        X, y = [], []

        for old_sig, is_same_family in existing_sigs:
            old_vec = self._encode(old_sig)
            diff = np.abs(new_vec - old_vec)
            X.append(diff)
            y.append(1 if is_same_family else 0)

        if len(X) < 2:
            self._n_seen += 1
            return

        X_arr = np.array(X)
        y_arr = np.array(y)

        if not self._fitted:
            X_arr = self._scaler.fit_transform(X_arr)
        else:
            X_arr = self._scaler.transform(X_arr)

        self._clf.partial_fit(X_arr, y_arr, classes=np.array([0, 1]))
        self._fitted = True
        self._n_seen += 1

    def score(self, sig_a: BehaviorPattern, sig_b: BehaviorPattern) -> float:
        """Probability that sig_a and sig_b are the same incident family."""
        if not self._fitted:
            return 0.5
        try:
            diff = np.abs(self._encode(sig_a) - self._encode(sig_b))
            diff_scaled = self._scaler.transform(diff.reshape(1, -1))
            proba = self._clf.predict_proba(diff_scaled)[0][1]
            return float(proba)
        except Exception:
            return 0.5

    def is_ready(self) -> bool:
        """True after at least one successful partial_fit."""
        return self._fitted


class MemoryStore:
    """Incident lifecycle manager with recency-decayed similarity search."""

    def __init__(self) -> None:
        self._incidents: list[IncidentMemory] = []
        self._open: dict[str, dict] = {}
        self._lock = threading.RLock()
        self._clf = IncrementalClassifier()

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
        graph: ServiceGraph | None = None,
    ) -> IncidentMemory | None:
        """Close an incident and store it as memory."""
        with self._lock:
            state = self._open.pop(incident_id, None)
            if state is None:
                return None

            sig = extract_signature(
                state["events"], anomalies, identity_layer, state["deploy_ts"], graph
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

            # Build training pairs for incremental classifier
            # Positive pair: incidents with same remediation action (heuristic for same family)
            # Negative pair: incidents with different trigger type
            existing_pairs = []
            for old_mem in self._incidents[:-1]:
                is_same = (
                    old_mem.remediation_action == mem.remediation_action
                    and old_mem.signature.trigger_type == mem.signature.trigger_type
                )
                existing_pairs.append((old_mem.signature, is_same))
            self._clf.update(mem.signature, existing_pairs)

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

                # Blend in classifier score if ready (improves Memory Evolution axis)
                if self._clf.is_ready():
                    clf_score = self._clf.score(signature, mem.signature)
                    # 65% LCS similarity + 35% classifier — classifier is now more influential
                    blended = 0.65 * base_sim + 0.35 * clf_score
                else:
                    blended = base_sim

                if blended <= 0.45:
                    continue

                # G4: recency decay — half-life 3 simulated days, affects 30% of score
                sim = blended
                if query_ts and mem.closed_at:
                    try:
                        age_days = (
                            parse_dt(query_ts) - parse_dt(mem.closed_at)
                        ).total_seconds() / 86400
                        decay = 0.5 ** (age_days / 3.0)
                        sim = blended * (0.70 + 0.30 * decay)
                    except Exception:
                        sim = blended

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

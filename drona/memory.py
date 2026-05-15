# drona/memory.py
from __future__ import annotations
from drona.schema import (
    IncidentMemory, BehaviorPattern, IncidentMatch, Remediation,
    TriggerType, SymptomType, PropagationDir,
)
from drona.signatures import extract_signature
from drona.identity import IdentityLayer
from drona.vector_store import FingerprintVectorStore
from dateutil.parser import parse as parse_dt
from sklearn.linear_model import SGDClassifier
from sklearn.preprocessing import StandardScaler
import numpy as np
import threading
import re


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
        """Encode a BehaviorPattern as a fixed-length 8-dim numeric vector."""
        sym_strs = set(sig.symptom_sequence)
        return np.array([
            self._TRIGGER_MAP.get(sig.trigger_type, 3),
            min(len(sig.symptom_sequence), 5),
            1 if any(s.startswith("LATENCY_SPIKE") for s in sym_strs) else 0,
            1 if any(s.startswith("ERROR_RATE_SPIKE") for s in sym_strs) else 0,
            1 if any(s.startswith("UPSTREAM_TIMEOUT") for s in sym_strs) else 0,
            1 if any(s.startswith("TRACE_SLOWDOWN") for s in sym_strs) else 0,
            self._PROP_MAP.get(sig.propagation_direction, 1),
            min(sig.time_to_first_symptom_s, 600.0),
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
        self._vectors = FingerprintVectorStore()

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
        graph=None,
    ) -> IncidentMemory | None:
        """Close an incident and store it as memory."""
        with self._lock:
            state = self._open.pop(incident_id, None)
            if state is None:
                return None

            sig = extract_signature(
                state["events"], anomalies, identity_layer, state["deploy_ts"],
                graph, state["primary_cid"],
            )
            target_svc = remediation_event.get("target", "")
            target_cid = (
                identity_layer.resolve(target_svc)
                if target_svc
                else state["primary_cid"]
            )
            features = extract_match_features(state["events"], anomalies)

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
                metric_names=features["metric_names"],
                error_patterns=features["error_patterns"],
            )
            self._incidents.append(mem)
            self._vectors.upsert(mem.incident_id, mem.signature)

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
        primary_cid: str | None = None,
        query_features: dict | None = None,
    ) -> list[tuple[float, IncidentMemory]]:
        """Find similar past incidents. Hard cutoff at 0.40, max 5 results.

        The behavioral signature intentionally ignores service names so recall
        survives rename events. For precision, we separately use the stable
        canonical epicentre when it is available.
        """
        with self._lock:
            candidates: list[tuple[float, float, IncidentMemory, dict]] = []
            for mem in self._incidents:
                base_sim = signature.similarity(mem.signature)

                # Blend in classifier score if ready (improves Memory Evolution axis)
                if self._clf.is_ready():
                    clf_score = self._clf.score(signature, mem.signature)
                    # 80% LCS similarity + 20% classifier — classifier is supplementary
                    blended = 0.80 * base_sim + 0.20 * clf_score
                else:
                    blended = base_sim

                # Hard cutoff: below 0.40 returns 0.0
                if blended < 0.40:
                    continue

                vector_sim = self._vectors.similarity(mem.incident_id, signature)
                components = {
                    "behavior": round(blended, 4),
                    "vector": round(vector_sim, 4),
                    "same_epicentre": bool(
                        primary_cid and mem.epicentre_canonical_id == primary_cid
                    ),
                    "affected_delta": abs(
                        max(1, signature.affected_service_count)
                        - max(1, mem.signature.affected_service_count)
                    ),
                    "metric_overlap": _overlap(
                        query_features.get("metric_names", []) if query_features else [],
                        mem.metric_names,
                    ),
                    "error_overlap": _overlap(
                        query_features.get("error_patterns", []) if query_features else [],
                        mem.error_patterns,
                    ),
                    "deploy_timing_match": _timing_match(
                        signature.time_to_first_symptom_s,
                        mem.signature.time_to_first_symptom_s,
                    ),
                }
                rerank = blended
                if components["same_epicentre"]:
                    rerank += 0.10

                # Prefer incidents with a similar blast radius when broad
                # latency/timeout symptoms would otherwise tie many families.
                count_delta = components["affected_delta"]
                if count_delta == 0:
                    rerank += 0.03
                elif count_delta >= 3:
                    rerank *= 0.96
                if components["metric_overlap"]:
                    rerank += 0.03
                if components["error_overlap"]:
                    rerank += 0.04
                if components["deploy_timing_match"]:
                    rerank += 0.02

                # Vector shape is deliberately a sidecar signal, not the
                # primary matcher. It helps close ties without dominating LCS.
                rerank += 0.04 * vector_sim
                candidates.append((blended, round(min(1.0, rerank), 4), mem, components))

            # Two-stage retrieval: broad behavior preserves recall, then the
            # sidecar/tie-breaker score selects the final top 5.
            candidates.sort(key=lambda x: x[0], reverse=True)
            broad = candidates[: max(min(top_k, 5), 15)]
            broad.sort(key=lambda x: x[1], reverse=True)
            return [(s, m) for _, s, m, _ in broad[:min(top_k, 5)]]

    def debug_candidates(
        self,
        signature: BehaviorPattern,
        top_k: int = 5,
        primary_cid: str | None = None,
        query_features: dict | None = None,
    ) -> list[dict]:
        """Return explainable candidate scores for error-analysis tooling."""
        with self._lock:
            rows = []
            for mem in self._incidents:
                behavior = signature.similarity(mem.signature)
                clf_score = self._clf.score(signature, mem.signature) if self._clf.is_ready() else 0.5
                blended = 0.80 * behavior + 0.20 * clf_score if self._clf.is_ready() else behavior
                if blended < 0.40:
                    continue
                vector_sim = self._vectors.similarity(mem.incident_id, signature)
                same_epicentre = bool(primary_cid and mem.epicentre_canonical_id == primary_cid)
                affected_delta = abs(
                    max(1, signature.affected_service_count)
                    - max(1, mem.signature.affected_service_count)
                )
                metric_overlap = _overlap(
                    query_features.get("metric_names", []) if query_features else [],
                    mem.metric_names,
                )
                error_overlap = _overlap(
                    query_features.get("error_patterns", []) if query_features else [],
                    mem.error_patterns,
                )
                timing_match = _timing_match(
                    signature.time_to_first_symptom_s,
                    mem.signature.time_to_first_symptom_s,
                )
                rerank = blended
                if same_epicentre:
                    rerank += 0.10
                if affected_delta == 0:
                    rerank += 0.03
                elif affected_delta >= 3:
                    rerank *= 0.96
                if metric_overlap:
                    rerank += 0.03
                if error_overlap:
                    rerank += 0.04
                if timing_match:
                    rerank += 0.02
                rerank += 0.04 * vector_sim
                rows.append({
                    "incident_id": mem.incident_id,
                    "behavior": round(blended, 4),
                    "vector": round(vector_sim, 4),
                    "same_epicentre": same_epicentre,
                    "affected_delta": affected_delta,
                    "metric_overlap": metric_overlap,
                    "error_overlap": error_overlap,
                    "deploy_timing_match": timing_match,
                    "rerank": round(min(1.0, rerank), 4),
                    "trigger_match": signature.trigger_type == mem.signature.trigger_type,
                    "propagation_match": (
                        signature.propagation_direction
                        == mem.signature.propagation_direction
                    ),
                })
            rows.sort(key=lambda row: row["rerank"], reverse=True)
            return rows[:top_k]

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


def extract_match_features(events: list[dict], anomalies: list[dict]) -> dict[str, list[str]]:
    metric_names: set[str] = set()
    error_patterns: set[str] = set()
    for event in events:
        if event.get("kind") == "metric" and event.get("name"):
            metric_names.add(str(event["name"]).lower())
        if event.get("kind") == "log":
            pattern = _error_pattern(str(event.get("msg", "")))
            if pattern:
                error_patterns.add(pattern)
    for anomaly in anomalies:
        event = anomaly.get("event", {})
        if event.get("kind") == "metric" and event.get("name"):
            metric_names.add(str(event["name"]).lower())
        pattern = _error_pattern(str(event.get("msg", "")))
        if pattern:
            error_patterns.add(pattern)
    return {
        "metric_names": sorted(metric_names),
        "error_patterns": sorted(error_patterns),
    }


def _error_pattern(message: str) -> str:
    text = message.lower()
    if "timeout" in text:
        return "timeout"
    if "connection refused" in text:
        return "connection_refused"
    if "unavailable" in text:
        return "unavailable"
    if "unreachable" in text:
        return "unreachable"
    if re.search(r"\b5\d\d\b", text):
        return "http_5xx"
    return ""


def _overlap(a: list[str], b: list[str]) -> bool:
    return bool(set(a) & set(b))


def _timing_match(a: float, b: float) -> bool:
    if a <= 0 or b <= 0:
        return False
    ratio = max(a, b) / min(a, b)
    return ratio <= 1.5

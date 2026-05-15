# drona/vector_store.py
from __future__ import annotations

from math import sqrt
from drona.schema import BehaviorPattern, TriggerType, PropagationDir


class FingerprintVectorStore:
    """Tiny in-memory vector sidecar for behavioral fingerprint retrieval.

    DuckDB remains the temporal event store. This sidecar stores only compact
    incident-shape vectors so it can answer "similar causal shape" questions
    without becoming the primary benchmark matcher.
    """

    def __init__(self) -> None:
        self._vectors: dict[str, list[float]] = {}

    def upsert(self, incident_id: str, signature: BehaviorPattern) -> None:
        self._vectors[incident_id] = fingerprint_vector(signature)

    def similarity(self, incident_id: str, signature: BehaviorPattern) -> float:
        stored = self._vectors.get(incident_id)
        if stored is None:
            return 0.0
        return cosine_similarity(fingerprint_vector(signature), stored)

    def top_k(
        self,
        signature: BehaviorPattern,
        k: int = 5,
    ) -> list[tuple[str, float]]:
        query = fingerprint_vector(signature)
        scored = [
            (incident_id, cosine_similarity(query, vec))
            for incident_id, vec in self._vectors.items()
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]


def fingerprint_vector(sig: BehaviorPattern) -> list[float]:
    symptoms = set(sig.symptom_sequence)
    bases = {_symptom_base(s) for s in symptoms}
    return [
        1.0 if sig.trigger_type == TriggerType.DEPLOY else 0.0,
        1.0 if sig.trigger_type == TriggerType.METRIC_ALERT else 0.0,
        1.0 if sig.trigger_type == TriggerType.DEPENDENCY_FAILURE else 0.0,
        1.0 if "LATENCY_SPIKE" in bases else 0.0,
        1.0 if "ERROR_RATE_SPIKE" in bases else 0.0,
        1.0 if "UPSTREAM_TIMEOUT" in bases else 0.0,
        1.0 if "TRACE_SLOWDOWN" in bases else 0.0,
        1.0 if sig.propagation_direction == PropagationDir.ISOLATED else 0.0,
        1.0 if sig.propagation_direction == PropagationDir.DOWNSTREAM else 0.0,
        1.0 if sig.propagation_direction == PropagationDir.UPSTREAM else 0.0,
        min(sig.affected_service_count, 10) / 10.0,
        min(sig.time_to_first_symptom_s, 600.0) / 600.0,
        min(len(sig.symptom_sequence), 8) / 8.0,
    ]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sqrt(sum(x * x for x in a))
    nb = sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def _symptom_base(symptom: str) -> str:
    return symptom.split(":", 1)[0] if ":" in symptom else symptom

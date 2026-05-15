# drona/graph.py
from __future__ import annotations
import networkx as nx
from datetime import datetime
from drona.schema import CausalEdge
import threading


class ServiceGraph:
    """NetworkX DiGraph where nodes = canonical_ids, edges = observed relationships."""

    def __init__(self) -> None:
        self._g = nx.DiGraph()
        self._lock = threading.RLock()

    def add_service(self, canonical_id: str, aliases: list[str]) -> None:
        """Add a service node to the graph."""
        with self._lock:
            self._g.add_node(
                canonical_id,
                aliases=aliases,
                first_seen=datetime.utcnow().isoformat(),
            )

    def record_call(self, caller_cid: str, callee_cid: str, ts: str) -> None:
        """Record a call from caller to callee."""
        with self._lock:
            if self._g.has_edge(caller_cid, callee_cid):
                self._g[caller_cid][callee_cid]["count"] += 1
                self._g[caller_cid][callee_cid]["last_seen"] = ts
            else:
                self._g.add_edge(caller_cid, callee_cid, count=1, last_seen=ts)

    def add_causal_edges(self, edges: list[CausalEdge]) -> None:
        """Add causal edges to the graph."""
        with self._lock:
            for edge in edges:
                if self._g.has_edge(edge.cause_id, edge.effect_id):
                    existing_conf = self._g[edge.cause_id][edge.effect_id].get(
                        "confidence", 0
                    )
                    self._g[edge.cause_id][edge.effect_id]["confidence"] = max(
                        existing_conf, edge.confidence
                    )
                else:
                    self._g.add_edge(
                        edge.cause_id,
                        edge.effect_id,
                        confidence=edge.confidence,
                        relationship=edge.relationship,
                    )

    def remove_dependency(self, source_cid: str, target_cid: str) -> None:
        """Remove an edge if it exists."""
        with self._lock:
            if self._g.has_edge(source_cid, target_cid):
                self._g.remove_edge(source_cid, target_cid)

    def get_upstream(self, canonical_id: str) -> list[str]:
        """Get list of upstream service canonical_ids."""
        with self._lock:
            if canonical_id in self._g:
                return list(self._g.predecessors(canonical_id))
            return []

    def get_downstream(self, canonical_id: str) -> list[str]:
        """Get list of downstream service canonical_ids."""
        with self._lock:
            if canonical_id in self._g:
                return list(self._g.successors(canonical_id))
            return []

    def propagation_direction(self, canonical_ids: list[str]) -> str:
        """Determine propagation direction among a set of services."""
        with self._lock:
            if len(canonical_ids) <= 1:
                return "isolated"
            for a in canonical_ids:
                for b in canonical_ids:
                    if a != b and self._g.has_edge(a, b):
                        return "downstream"
            return "downstream"  # safe default

    def node_count(self) -> int:
        """Number of nodes in the graph."""
        return self._g.number_of_nodes()

    def edge_count(self) -> int:
        """Number of edges in the graph."""
        return self._g.number_of_edges()

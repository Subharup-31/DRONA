# drona/identity.py
from __future__ import annotations
from dataclasses import dataclass, field
import uuid
import threading


@dataclass
class ServiceNode:
    """Represents a single logical service with a stable canonical ID."""
    canonical_id: str
    aliases: list[str]
    first_seen: str
    last_seen: str


class IdentityLayer:
    """UUID canonical_id per service + alias dict. Renames add aliases, canonical_id never changes."""

    def __init__(self) -> None:
        self._alias_to_cid: dict[str, str] = {}
        self._nodes: dict[str, ServiceNode] = {}
        self._lock = threading.RLock()

    def resolve(self, name: str) -> str:
        """Creates new ServiceNode on first sight. Returns canonical_id."""
        with self._lock:
            if name in self._alias_to_cid:
                cid = self._alias_to_cid[name]
                self._nodes[cid].last_seen = _now()
                return cid
            cid = str(uuid.uuid4())
            ts = _now()
            node = ServiceNode(
                canonical_id=cid,
                aliases=[name],
                first_seen=ts,
                last_seen=ts,
            )
            self._nodes[cid] = node
            self._alias_to_cid[name] = cid
            return cid

    def handle_rename(self, old_name: str, new_name: str) -> str:
        """Adds new_name as alias to existing node. canonical_id unchanged."""
        with self._lock:
            if old_name not in self._alias_to_cid:
                self.resolve(old_name)
            cid = self._alias_to_cid[old_name]
            node = self._nodes[cid]
            if new_name not in node.aliases:
                node.aliases.append(new_name)
            self._alias_to_cid[new_name] = cid
            node.last_seen = _now()
            return cid

    def handle_dependency_shift(
        self, source: str, target: str, change: str, ts: str
    ) -> tuple[str, str]:
        """Resolves both services to canonical_ids. Returns (source_cid, target_cid)."""
        with self._lock:
            src_cid = self.resolve(source)
            tgt_cid = self.resolve(target)
            return src_cid, tgt_cid

    def current_name(self, canonical_id: str) -> str:
        """Returns last alias in the list. Falls back to canonical_id if not found."""
        with self._lock:
            node = self._nodes.get(canonical_id)
            if node and node.aliases:
                return node.aliases[-1]
            return canonical_id

    def all_aliases(self, canonical_id: str) -> list[str]:
        """Returns copy of aliases list."""
        with self._lock:
            node = self._nodes.get(canonical_id)
            if node:
                return list(node.aliases)
            return []

    def known_services(self) -> list[str]:
        """Returns all canonical_ids currently tracked."""
        with self._lock:
            return list(self._nodes.keys())


def _now() -> str:
    """Current UTC timestamp as ISO string."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    il = IdentityLayer()
    cid1 = il.resolve("payments-svc")
    il.handle_rename("payments-svc", "billing-svc")
    cid2 = il.resolve("billing-svc")
    assert cid1 == cid2, f"FAIL: rename broke canonical_id: {cid1} != {cid2}"
    assert il.current_name(cid1) == "billing-svc", f"FAIL: current_name is {il.current_name(cid1)}"
    assert "payments-svc" in il.all_aliases(cid1), "FAIL: payments-svc not in aliases"
    assert "billing-svc" in il.all_aliases(cid1), "FAIL: billing-svc not in aliases"

    cid3 = il.resolve("checkout-api")
    assert cid3 != cid1, "FAIL: different services got same canonical_id"
    src, dst = il.handle_dependency_shift(
        "checkout-api", "billing-svc", "add", "2026-05-10T14:00:00Z"
    )
    assert src == cid3, f"FAIL: src={src} != cid3={cid3}"
    assert dst == cid1, f"FAIL: dst={dst} != cid1={cid1}"
    print("identity: all tests passed")

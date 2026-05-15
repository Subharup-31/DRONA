# drona/temporal_index.py
from __future__ import annotations
import duckdb
import json
import threading
from datetime import datetime, timezone


def _to_naive_utc(dt: datetime) -> datetime:
    """Convert tz-aware datetime to naive UTC for DuckDB TIMESTAMP comparison."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


class TemporalIndex:
    """DuckDB in-process temporal index. Batch inserts, pre-computed anomaly flags."""

    def __init__(self) -> None:
        self.db = duckdb.connect(":memory:")
        self._baselines: dict[str, float] = {}
        self._lock = threading.RLock()
        self._create_schema()

    def _create_schema(self) -> None:
        """Create events table and indexes."""
        self.db.execute("""
            CREATE TABLE events (
                ts           TIMESTAMP,
                canonical_id VARCHAR,
                kind         VARCHAR,
                raw          JSON,
                is_anomaly   BOOLEAN DEFAULT FALSE,
                anomaly_type VARCHAR DEFAULT ''
            )
        """)
        self.db.execute("CREATE INDEX idx_cid_ts ON events(canonical_id, ts)")
        self.db.execute("CREATE INDEX idx_ts ON events(ts)")

    def build_row(
        self, canonical_id: str, event: dict, ts: datetime
    ) -> tuple | None:
        """Computes is_anomaly + anomaly_type inline. Returns row tuple or None."""
        kind = event.get("kind", "")

        # Topology events never stored
        if kind == "topology":
            return None

        is_anomaly = False
        anomaly_type = ""

        if kind == "metric":
            metric_name = event.get("name", "")
            value = float(event.get("value", 0))
            key = f"{canonical_id}:{metric_name}"
            baseline = self._baselines.get(key)
            if baseline is None:
                self._baselines[key] = value
            else:
                if baseline > 0 and value > 2.5 * baseline:
                    is_anomaly = True
                    anomaly_type = "metric_spike"
                self._baselines[key] = 0.9 * baseline + 0.1 * value

        elif kind == "log" and event.get("level") == "error":
            is_anomaly = True
            anomaly_type = "error_log"

        elif kind == "trace":
            spans = event.get("spans", [])
            for span in spans:
                if span.get("dur_ms", 0) > 3000:
                    is_anomaly = True
                    anomaly_type = "trace_slowdown"
                    break

        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if isinstance(ts, datetime) else str(ts)
        return (ts_str, canonical_id, kind, json.dumps(event), is_anomaly, anomaly_type)

    def insert_batch(self, rows: list[tuple]) -> None:
        """Batch-insert rows into DuckDB. Thread-safe."""
        if not rows:
            return
        with self._lock:
            self.db.executemany(
                "INSERT INTO events VALUES (?,?,?,?,?,?)", rows
            )

    def query_window_all(
        self, start: datetime, end: datetime
    ) -> list[dict]:
        """SELECT raw FROM events WHERE ts BETWEEN start AND end ORDER BY ts."""
        with self._lock:
            result = self.db.execute(
                "SELECT raw FROM events WHERE ts BETWEEN ? AND ? ORDER BY ts",
                [_to_naive_utc(start), _to_naive_utc(end)],
            ).fetchall()
        return [json.loads(row[0]) for row in result]

    def query_window(
        self, canonical_id: str, start: datetime, end: datetime
    ) -> list[dict]:
        """SELECT raw FROM events WHERE canonical_id=? AND ts BETWEEN ? AND ? ORDER BY ts."""
        with self._lock:
            result = self.db.execute(
                "SELECT raw FROM events WHERE canonical_id=? AND ts BETWEEN ? AND ? ORDER BY ts",
                [canonical_id, _to_naive_utc(start), _to_naive_utc(end)],
            ).fetchall()
        return [json.loads(row[0]) for row in result]

    def get_anomalies(
        self, start: datetime, end: datetime
    ) -> list[dict]:
        """Returns list of {\"event\": dict, \"type\": str} for anomalies in window."""
        with self._lock:
            result = self.db.execute(
                "SELECT raw, anomaly_type FROM events "
                "WHERE is_anomaly=TRUE AND ts BETWEEN ? AND ? ORDER BY ts",
                [_to_naive_utc(start), _to_naive_utc(end)],
            ).fetchall()
        return [
            {"event": json.loads(row[0]), "type": row[1]}
            for row in result
        ]

    def close(self) -> None:
        """Release DuckDB connection."""
        self.db.close()

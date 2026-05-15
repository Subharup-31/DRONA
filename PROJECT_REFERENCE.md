# Drona — Complete Project Reference

**Anvil Hackathon · P·02 · Team radiohead · May 2026**
**Last updated:** 2026-05-15

---

## 1. Project Overview

Drona is a **Persistent Context Engine for AI SRE** that:
- Ingests production telemetry (deploys, metrics, logs, traces, topology changes)
- Builds operational memory that **survives service renames and topology drift**
- At incident time, reconstructs causal context, surfaces similar past incidents using
  **topology-independent behavioral matching**, and suggests validated remediations

**Two public methods:**
```python
engine.ingest(events)                                  # consume telemetry stream
engine.reconstruct_context(signal, mode="fast")        # get incident context
```

---

## 2. File Inventory

| File | Lines | Bytes | Purpose |
|------|------:|------:|---------|
| `drona/schema.py` | 128 | 4,383 | All types: Event, Context, BehaviorPattern, enums |
| `drona/identity.py` | 111 | 3,996 | UUID canonical IDs + alias table for service identity |
| `drona/temporal_index.py` | 122 | 4,335 | DuckDB in-memory temporal storage with anomaly detection |
| `drona/signatures.py` | 141 | 4,658 | Service-name-agnostic behavioral pattern extraction |
| `drona/memory.py` | 267 | 9,671 | Incident lifecycle + similarity search + IncrementalClassifier |
| `drona/causal.py` | 163 | 5,987 | 3 deterministic causal rules (no LLM) |
| `drona/graph.py` | 90 | 3,431 | NetworkX DiGraph for service topology |
| `drona/engine.py` | 286 | 10,709 | Main Engine — orchestrates all components |
| `drona/explainer.py` | 220 | 7,175 | template / bedrock / openrouter LLM backends |
| `drona/__init__.py` | 1 | 54 | Package init |
| `adapters/__init__.py` | 1 | 51 | Package init |
| `adapters/radiohead.py` | 121 | 4,515 | Bench harness adapter for team radiohead |
| `self_check.py` | 271 | 8,819 | 6-test local validation harness |
| `requirements.txt` | 8 | 133 | Pinned dependencies |
| `Dockerfile` | 17 | 379 | Reproducible build for judges |
| `docker-compose.yml` | 8 | 157 | Docker compose config |
| `bench/run.sh` | 44 | 1,362 | Benchmark runner script |
| `.env.example` | 5 | 152 | Environment variable template |
| `.gitignore` | 8 | 68 | Git ignore rules |
| `README.md` | 222 | 8,695 | Project documentation |
| **TOTAL** | **~2,284** | **~79,000** | |

---

## 3. Dependencies

```
duckdb==0.10.3          # In-memory temporal index
networkx==3.3           # Service dependency graph
fastapi==0.111.0        # Available for API exposure
uvicorn==0.30.1         # Available for API exposure
boto3==1.34.0           # AWS Bedrock client (deep mode only)
python-dateutil==2.9.0  # Timestamp parsing
numpy==1.26.4           # Numeric operations
scikit-learn==1.5.0     # Incremental classifier for memory evolution
```

---

## 4. Complete API Reference

---

### 4.1 `drona/schema.py` — Types & Data Models

#### `Event`
```python
Event = dict[str, Any]  # Raw telemetry event — flexible schema
```

#### `@dataclass IncidentSignal`
```python
class IncidentSignal:
    incident_id: str          # e.g. "INC-714"
    trigger:     str          # e.g. "alert:checkout-api/error-rate>5%"
    ts:          str          # ISO 8601 timestamp
    service:     str | None   # Optional service hint
```

#### `@dataclass CausalEdge`
```python
class CausalEdge:
    cause_id:     str         # Canonical ID of cause service
    effect_id:    str         # Canonical ID of effect service
    evidence:     list[Event] # Supporting events
    confidence:   float       # 0.0–1.0
    relationship: str         # Default "causes"
```

#### `@dataclass IncidentMatch`
```python
class IncidentMatch:
    past_incident_id: str     # e.g. "INC-714"
    similarity:       float   # 0.0–1.0
    rationale:        str     # Human-readable explanation
```

#### `@dataclass Remediation`
```python
class Remediation:
    action:             str   # e.g. "rollback"
    target:             str   # Current service name
    historical_outcome: str   # e.g. "resolved"
    confidence:         float # 0.0–1.0
```

#### `Context` (TypedDict)
```python
class Context(TypedDict):
    related_events:         list[Event]
    causal_chain:           list[CausalEdge]
    similar_past_incidents: list[IncidentMatch]
    suggested_remediations: list[Remediation]
    confidence:             float  # 0.0–1.0
    explain:                str    # Human-readable narrative
```

#### Enums
```python
class TriggerType(str, Enum):
    DEPLOY             = "deploy"
    METRIC_ALERT       = "metric_alert"
    DEPENDENCY_FAILURE = "dependency_failure"
    UNKNOWN            = "unknown"

class SymptomType(str, Enum):
    LATENCY_SPIKE    = "latency_spike"
    ERROR_RATE_SPIKE = "error_rate_spike"
    UPSTREAM_TIMEOUT = "upstream_timeout"
    TRACE_SLOWDOWN   = "trace_slowdown"
    CONNECTION_DROP  = "connection_drop"

class PropagationDir(str, Enum):
    UPSTREAM   = "upstream"
    DOWNSTREAM = "downstream"
    ISOLATED   = "isolated"
```

#### `@dataclass BehaviorPattern`
```python
class BehaviorPattern:
    trigger_type:            TriggerType
    symptom_sequence:        list[SymptomType]
    affected_service_count:  int
    propagation_direction:   PropagationDir
    time_to_first_symptom_s: float

    def similarity(self, other: BehaviorPattern) -> float:
        """4-component weighted similarity. Returns 0.0–1.0.
        - 0.30: trigger_type match
        - 0.40: LCS ratio on symptom_sequence
        - 0.20: propagation_direction match
        - 0.10: time_to_first_symptom ratio (within 3x)
        """
```

#### `@dataclass IncidentMemory`
```python
class IncidentMemory:
    incident_id:            str
    signature:              BehaviorPattern
    epicentre_canonical_id: str
    remediation_action:     str
    remediation_target_cid: str
    outcome:                str
    opened_at:              str
    closed_at:              str
    context_events:         list[Event]
```

#### Helper
```python
def _lcs_ratio(a: list, b: list) -> float:
    """Order-aware longest common subsequence ratio."""
```

---

### 4.2 `drona/identity.py` — Service Identity Layer

#### `@dataclass ServiceNode`
```python
class ServiceNode:
    canonical_id: str    # UUID, never changes
    aliases:     list[str]
    first_seen:  str
    last_seen:   str
```

#### `class IdentityLayer`
```python
class IdentityLayer:
    """UUID canonical_id per service + alias dict.
    Renames add aliases, canonical_id never changes."""

    def resolve(self, name: str) -> str:
        """Creates new ServiceNode on first sight. Returns canonical_id."""

    def handle_rename(self, old_name: str, new_name: str) -> str:
        """Adds new_name as alias to existing node. canonical_id unchanged."""

    def handle_dependency_shift(self, source, target, change, ts) -> tuple[str, str]:
        """Resolves both services to canonical_ids. Returns (source_cid, target_cid)."""

    def current_name(self, canonical_id: str) -> str:
        """Returns last alias in the list. Falls back to canonical_id."""

    def all_aliases(self, canonical_id: str) -> list[str]:
        """Returns copy of aliases list."""

    def known_services(self) -> list[str]:
        """Returns all canonical_ids currently tracked."""
```

**Thread safety:** `threading.RLock` on all methods.

---

### 4.3 `drona/temporal_index.py` — DuckDB Temporal Storage

#### `class TemporalIndex`
```python
class TemporalIndex:
    """DuckDB in-process temporal index. Batch inserts, pre-computed anomaly flags."""

    def build_row(self, canonical_id, event, ts) -> tuple | None:
        """Computes is_anomaly + anomaly_type inline. Returns row tuple.
        Anomaly rules:
        - metric: value > 2.5x baseline → metric_spike (EMA baseline, α=0.1)
        - log: level == "error" → error_log
        - trace: any span dur_ms > 3000 → trace_slowdown
        """

    def insert_batch(self, rows: list[tuple]) -> None:
        """Batch-insert rows into DuckDB. Thread-safe."""

    def query_window_all(self, start, end) -> list[dict]:
        """SELECT raw FROM events WHERE ts BETWEEN start AND end ORDER BY ts."""

    def query_window(self, canonical_id, start, end) -> list[dict]:
        """SELECT raw WHERE canonical_id=? AND ts BETWEEN ? AND ? ORDER BY ts."""

    def get_anomalies(self, start, end) -> list[dict]:
        """Returns list of {"event": dict, "type": str} for anomalies in window."""

    def close(self) -> None:
        """Release DuckDB connection."""
```

**DuckDB schema:**
```sql
CREATE TABLE events (
    ts           TIMESTAMP,
    canonical_id VARCHAR,
    kind         VARCHAR,
    raw          JSON,
    is_anomaly   BOOLEAN DEFAULT FALSE,
    anomaly_type VARCHAR DEFAULT ''
);
CREATE INDEX idx_cid_ts ON events(canonical_id, ts);
CREATE INDEX idx_ts ON events(ts);
```

---

### 4.4 `drona/signatures.py` — Behavioral Pattern Extraction

```python
def extract_signature(events, anomalies, identity_layer, deploy_ts) -> BehaviorPattern:
    """Extract a service-name-agnostic behavioral signature.
    5 steps:
    1. _detect_trigger → TriggerType
    2. _build_symptom_sequence → list[SymptomType] (ordered, deduped consecutive)
    3. _count_affected_services → int (unique cids, capped at 10)
    4. propagation_direction → isolated if 1 service, else downstream
    5. _compute_time_to_first_symptom → float (seconds from deploy to first anomaly)
    """

def _detect_trigger(events) -> TriggerType:
    """Priority: deploy > metric_alert > dependency_failure > unknown."""

def _build_symptom_sequence(anomalies) -> list[SymptomType]:
    """Map anomaly types to symptoms. Dedup consecutive duplicates."""

def _count_affected_services(events, anomalies, identity_layer) -> int:
    """Count unique canonical_ids across events + anomalies. Cap at 10."""

def _compute_time_to_first_symptom(anomalies, deploy_ts) -> float:
    """Seconds from deploy to first anomaly. Returns 0.0 if no deploy."""
```

---

### 4.5 `drona/memory.py` — Incident Memory Store

#### `class IncrementalClassifier`
```python
class IncrementalClassifier:
    """Online SGDClassifier that learns BehaviorPattern pair similarity.
    Supplements (does not replace) LCS similarity in find_similar."""

    def _encode(self, sig: BehaviorPattern) -> np.ndarray:
        """8-dim feature vector: trigger ordinal, symptom count,
        4 symptom flags, propagation ordinal, time_to_first_symptom."""

    def update(self, new_sig, existing_sigs: list) -> None:
        """Generate positive+negative pairs, call partial_fit.
        Positive: same remediation_action + trigger_type.
        Negative: different trigger_type."""

    def score(self, sig_a, sig_b) -> float:
        """P(same family). Returns 0.5 if not yet fitted."""

    def is_ready(self) -> bool:
        """True after ≥1 successful partial_fit."""
```

#### `class MemoryStore`
```python
class MemoryStore:
    """Incident lifecycle manager with recency-decayed similarity search."""

    def open_incident(self, incident_id, ts, initial_events, primary_cid) -> None:
        """Open a new incident with initial event context."""

    def update_open(self, incident_id, events) -> None:
        """Append events to an open incident."""

    def close_incident(self, incident_id, remediation_event, anomalies, identity_layer) -> IncidentMemory | None:
        """Close incident, extract signature, store as memory,
        train IncrementalClassifier on the new incident."""

    def find_similar(self, signature, top_k=5, query_ts=None) -> list[tuple[float, IncidentMemory]]:
        """Find similar past incidents.
        - Base: BehaviorPattern.similarity() (LCS-based)
        - Blend: 80% LCS + 20% classifier (if ready)
        - Threshold: blended > 0.25
        - G4: Recency decay with half-life 3 days, affects 30% of score"""

    def get_remediation_suggestions(self, similar, identity_layer) -> list[Remediation]:
        """Generate remediation suggestions from top-3 similar incidents."""

    def incident_count(self) -> int:
    def open_count(self) -> int:
```

---

### 4.6 `drona/causal.py` — Causal Chain Builder

```python
def build_causal_chain(events, anomalies, identity_layer) -> list[CausalEdge]:
    """Build causal chain using 3 deterministic rules. No LLM.
    Post-processing: deduplicate by (cause, effect), remove self-loops,
    sort by confidence descending."""
```

| Rule | Pattern | Confidence |
|------|---------|-----------|
| Rule 1 | Deploy → Metric/Trace anomaly within 5 min | 0.85–0.95 |
| Rule 2 | Upstream timeout log → Caller | 0.75 |
| Rule 3 | Trace span slowdown (>3s) → Caller | 0.80 |

```python
def _extract_callee_from_msg(msg: str) -> str | None:
    """Extract service names from error messages.
    3 regex patterns + fallback on service-like suffixes (-svc, -api, etc.)."""
```

---

### 4.7 `drona/graph.py` — Service Topology Graph

```python
class ServiceGraph:
    """NetworkX DiGraph. Nodes = canonical_ids, edges = relationships."""

    def add_service(self, canonical_id, aliases) -> None:
    def record_call(self, caller_cid, callee_cid, ts) -> None:
    def add_causal_edges(self, edges: list[CausalEdge]) -> None:
    def remove_dependency(self, source_cid, target_cid) -> None:
    def get_upstream(self, canonical_id) -> list[str]:
    def get_downstream(self, canonical_id) -> list[str]:
    def propagation_direction(self, canonical_ids) -> str:
    def node_count(self) -> int:
    def edge_count(self) -> int:
```

---

### 4.8 `drona/engine.py` — Main Engine

```python
class Engine:
    """Main Drona engine. Thread-safe. One instance per benchmark seed.
    Components: IdentityLayer, TemporalIndex, MemoryStore, ServiceGraph.
    Batch buffer: 50 events before DuckDB flush."""

    def ingest(self, events: Iterable[Event]) -> None:
        """Consume event stream. Handles 7 event kinds:
        deploy, metric, log, trace, topology, incident_signal, remediation."""

    def reconstruct_context(self, signal, mode="fast") -> Context:
        """Full pipeline:
        1. Query window (±15min, G2 expands to ±30min if empty)
        2. Rank + deduplicate + add _provenance (G3)
        3. Build causal chain (3 rules)
        4. Extract behavioral signature
        5. Find similar past incidents (G4 recency decay)
        6. Generate remediation suggestions
        7. Compute confidence score
        8. Generate explanation (template or LLM)
        """

    def close(self) -> None:
```

**Gap fixes in engine.py:**

| Gap | Implementation |
|-----|---------------|
| G1 | `_process_event` handles rename, dependency_add, dependency_remove |
| G2 | Window expansion to ±30min when initial query returns empty |
| G3 | `_rank_related` adds `_provenance` dict to each event |
| G5 | `_extract_svc_from_trigger` — 3 regex patterns + fallback |

---

### 4.9 `drona/explainer.py` — Explanation Generator

```python
def generate_explain(related, chain, similar, mode, identity) -> str:
    """Generate incident explanation.
    mode="fast" → always uses template (zero cost).
    mode="deep" → uses DRONA_LLM_BACKEND env var."""

def _template(related, chain, similar, identity) -> str:
    """3-sentence template: what happened, likely cause, recommendation."""

def _build_prompt(related, chain, similar, identity) -> str:
    """Compact LLM prompt from context data."""

def _bedrock(user_prompt) -> str:
    """AWS Bedrock Claude 3 Haiku. 4.5s socket timeout (G6)."""

def _openrouter(user_prompt) -> str:
    """OpenRouter Llama 3.1 8B free. 4.5s socket timeout (G6)."""
```

**LLM System Prompt:** "You are a senior SRE analyzing a production incident. Respond in exactly 3 sentences..."

---

### 4.10 `adapters/radiohead.py` — Bench Harness Adapter

```python
class Engine(Adapter):
    """Thin shim mapping bench harness interface to drona Engine.
    Handles both dict and dataclass inputs.
    Converts all output dataclasses to plain dicts for bench harness."""

    def ingest(self, events) -> None:
    def reconstruct_context(self, signal, mode="fast") -> dict:
    def close(self) -> None:
```

---

### 4.11 `self_check.py` — Local Test Harness

| Test | What it validates | Pass criteria |
|------|-------------------|---------------|
| TEST 1 | Identity rename | canonical_id unchanged after rename |
| TEST 2 | Context reconstruction | deploy in events, causal chain exists, <2s, provenance present |
| TEST 3 | Rename robustness (KEY) | INC-714 found as match after payments-svc→billing-svc rename |
| TEST 4 | Ingest throughput | ≥1,000 events/sec |
| TEST 5 | Window expansion (G2) | Returns valid context even when deploy is 4h before signal |
| TEST 6 | Dependency shift (G1) | rename tracked correctly after dependency_add |

---

## 5. Gap Fixes (G1–G6) from PRD Section 19

| Gap | Problem | Fix | File |
|-----|---------|-----|------|
| G1 | Topology handler only handled rename | Handles rename, dependency_add/link/add, dependency_remove/unlink/remove | `engine.py` |
| G2 | Empty window returned empty context | Expands from ±15min to ±30min on empty | `engine.py` |
| G3 | No provenance on related events | `_provenance` dict added with relevance_score, is_anomaly, source_ts | `engine.py` |
| G4 | No recency decay in similarity | Half-life 3 simulated days, affects 30% of score | `memory.py` |
| G5 | Service extraction from trigger was fragile | 3 regex patterns + suffix-based fallback | `engine.py` |
| G6 | No timeout on LLM calls | 4.5s socket timeout + fallback to template | `explainer.py` |

---

## 6. How to Run

### First time setup
```bash
git clone git@github.com:Subharup-31/DRONA.git
cd DRONA
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Validate (must show 6/6)
```bash
python self_check.py
```

### Docker
```bash
docker build -t drona .
docker run drona              # runs self_check.py, no API keys needed
```

### Docker Compose
```bash
docker compose up --build
```

### Benchmark (when bench repo available)
```bash
bash bench/run.sh
```

### Environment Variables
```
DRONA_LLM_BACKEND=template    # template (default) | bedrock | openrouter
AWS_REGION=us-east-1           # for bedrock
AWS_ACCESS_KEY_ID=...          # for bedrock
AWS_SECRET_ACCESS_KEY=...      # for bedrock
OPENROUTER_API_KEY=...         # for openrouter
```

---

## 7. Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV DRONA_LLM_BACKEND=template
ENV PYTHONPATH=/app
CMD ["python", "self_check.py"]
```

---

## 8. Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                        Engine                           │
│                                                         │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────┐  │
│  │ IdentityLayer│   │TemporalIndex │   │ServiceGraph │  │
│  │ UUID + alias │   │ DuckDB :mem: │   │  NetworkX   │  │
│  │ O(1) resolve │   │ batch insert │   │  DiGraph    │  │
│  └──────┬───────┘   └──────┬───────┘   └─────┬──────┘  │
│         │                  │                  │         │
│  ┌──────▼──────────────────▼──────────────────▼──────┐  │
│  │              reconstruct_context()                │  │
│  │  ┌──────────┐ ┌──────────┐ ┌───────────────────┐  │  │
│  │  │  Causal  │ │Signatures│ │    MemoryStore     │  │  │
│  │  │ 3 rules  │ │  no svc  │ │ + IncrementalClf  │  │  │
│  │  │ no LLM   │ │  names   │ │ recency decay     │  │  │
│  │  └──────────┘ └──────────┘ └───────────────────┘  │  │
│  │                    │                               │  │
│  │              ┌─────▼─────┐                        │  │
│  │              │ Explainer │                        │  │
│  │              │ template  │                        │  │
│  │              │ bedrock   │                        │  │
│  │              │ openrouter│                        │  │
│  │              └───────────┘                        │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## 9. Egress Declaration

| Backend | Egress | Model | Cost |
|---------|--------|-------|------|
| template (default) | None | N/A | $0 |
| bedrock | AWS Bedrock | claude-3-haiku | ~$0.03 |
| openrouter | openrouter.ai | llama-3.1-8b-instruct:free | $0 |

Deep mode only affects the `explain` string. All scored metrics (recall, causal
chain accuracy, related events, remediations) are computed locally with no
network calls.

---

## 10. Git Log

```
5c7088c  chore: add pyrefly lint suppression for bench adapter import
9cb4698  docs: comprehensive README with architecture, quickstart, and gap fixes table
94bd252  feat: add IncrementalClassifier for Memory Evolution axis
d04a53c  feat: drona engine — anvil p02 team radiohead — all 6 self_check tests passing
```

---

## 11. Test Results

```
═══ DRONA SELF CHECK ═══

TEST 1  PASS  Identity rename
TEST 2  PASS  Context reconstruction (3ms)
TEST 3  PASS  Rename robustness — INC-714 found in ['INC-714']
TEST 4  PASS  Throughput: 7333 events/sec
TEST 5  PASS  Window expansion on empty
TEST 6  PASS  Dependency shift topology

═══ 6/6 passed ═══
```

---

**Team radiohead · Anuj Dwivedi, archzOS · MIT License**

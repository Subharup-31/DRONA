# DRONA — Persistent Context Engine for AI SRE
## Final PRD · Complete Build Guide · All Agent Prompts
### Anvil P·02 · Scaler School of Technology · May 15–16 2026

---

## 0. META-PROMPT — PASTE AT TOP OF EVERY NEW CLAUDE SESSION

```
You are a senior Python systems engineer building "Drona" — submitted to Anvil 
Hackathon P·02 (Persistent Context Engine for AI SRE) at Scaler School of 
Technology, Bengaluru, May 15–16 2026. Builder: Anuj Dwivedi, founder of archzOS.

═══ SYSTEM IDENTITY ═══
Project name: drona
Language: Python 3.11, strict typing throughout
License: MIT

═══ WHAT IT DOES ═══
Two public methods only:
  ingest(events: Iterable[Event]) -> None
  reconstruct_context(signal: IncidentSignal, mode="fast"|"deep") -> Context

Ingests production telemetry (deploy/log/metric/trace/topology/incident_signal/
remediation events), builds operational memory, and at incident time reconstructs
causal context — surviving service renames and topology drift.

═══ ARCHITECTURE (NON-NEGOTIABLE) ═══
1. IdentityLayer: UUID canonical_id per service + alias dict. Renames add aliases,
   canonical_id never changes. O(1) resolve(name)->cid, current_name(cid)->str.
2. TemporalIndex: DuckDB ":memory:" (in-process, no external DB, no ports).
   Batch inserts, pre-computed anomaly flags on write.
3. BehaviorPattern: NO service names inside. trigger_type + symptom_sequence 
   (ordered) + propagation_direction + time_to_first_symptom_s only.
   Similarity = LCS ratio (40%) + trigger match (30%) + propagation (20%) + 
   time-to-symptom (10%).
4. MemoryStore: list[IncidentMemory] for closed incidents + dict for open ones.
   find_similar uses BehaviorPattern.similarity() with recency decay.
5. CausalChain: 3 deterministic rules, no LLM. Deploy→spike within 5min (0.85-0.95
   confidence), timeout-log→upstream-caller (0.75), trace-span-slowdown (0.80).
6. ServiceGraph: NetworkX DiGraph, canonical_ids as nodes, edges accumulate.
7. Explainer: 3 backends via DRONA_LLM_BACKEND env var:
   - "template" = pure string template, zero cost, DEFAULT
   - "openrouter" = free Llama 3.1 8B via OpenRouter (dev/testing)
   - "bedrock" = Claude 3 Haiku via AWS Bedrock (final demo, ~$0.03 total)

═══ FIXED GAPS (ALL MUST BE IN IMPLEMENTATION) ═══
G1. Topology handler covers BOTH renames AND dependency shifts (add/remove edges)
G2. Window expansion fallback: if query returns empty, expand to ±30min
G3. related_events deduped + _provenance field added to each event
G4. find_similar has recency decay: half-life 3 simulated days, affects 30% of score
G5. Trigger service extraction uses 3 regex patterns + fallback, not naive split
G6. LLM calls have 4.5s socket timeout, fall back to template on any exception

═══ STORAGE (FINAL) ═══
- DuckDB ":memory:" — temporal index, no file on disk, no external service
- Python dicts/lists — identity layer, memory store, graph
- NO external DB needed. NO Neo4j. NO Postgres. NO Redis.
- Judge reproduces with: docker build + docker run. Zero infra setup.

═══ ENV VARS ═══
DRONA_LLM_BACKEND=template         # always default
AWS_REGION=us-east-1               # bedrock only
AWS_ACCESS_KEY_ID=                 # bedrock only  
AWS_SECRET_ACCESS_KEY=             # bedrock only
OPENROUTER_API_KEY=                # openrouter only

═══ RULES FOR ALL CODE YOU WRITE ═══
- No placeholder code. No TODOs. Complete, runnable implementations only.
- Strict typing: all function signatures have type annotations.
- Every method has a one-line docstring.
- Error handling: exceptions in LLM path always fall back gracefully, never raise.
- Thread-safe where shared state exists (threading.RLock).
- When I say "next" → produce the next component in sequence.
- When I say "fix [X]" → minimal diff, don't refactor other components.
- When I say "test" → trace through canonical scenario mentally, check all assertions.
```

---

## 1. HACKATHON RULES SUMMARY

| Rule | Value |
|---|---|
| Duration | 24 hours: May 15 11:00 AM → May 16 11:00 AM IST |
| Team size | 1–4 (solo allowed) |
| Language | Open (we use Python 3.11) |
| Hardware | Your laptop, Linux or macOS |
| Network | External LLM calls allowed for P02 (declare egress in README) |
| Bench repo | github.com/Sauhard74/Anvil-P-E (private until 11 AM, then public) |
| Version control | Git. Apache-2.0 or MIT preferred |
| Storage | Any (DuckDB in-memory is our choice) |
| LLM | Any provider, your cost (Bedrock Haiku ~$0.03 total) |
| Forbidden | Vector similarity as primary approach (auto-ranks bottom) |
| Submission | Git link + bench/run.sh → report.json + 5-min demo video + 3-page PDF |
| Reproducibility | Dockerfile required — judges run on their machines |

---

## 2. ENVIRONMENT — COMPLETE & FINAL

### `.env` (gitignored, never commit)
```bash
# ─── LLM BACKEND ──────────────────────────────────────────────────────────────
# template   = zero cost, zero egress, pure string template (DEFAULT — always safe)
# openrouter = free Llama 3.1 8B, use during dev/iteration
# bedrock    = Claude 3 Haiku on AWS, use for final demo only
DRONA_LLM_BACKEND=template

# ─── AWS BEDROCK (only when DRONA_LLM_BACKEND=bedrock) ───────────────────────
# Your existing account: 950119649691
# Model: anthropic.claude-3-haiku-20240307-v1:0
# Estimated total cost for 24hr hackathon: ~$0.03
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=

# ─── OPENROUTER (only when DRONA_LLM_BACKEND=openrouter) ─────────────────────
# Free model: meta-llama/llama-3.1-8b-instruct:free
# Cost: $0.00
OPENROUTER_API_KEY=
```

### `.env.example` (commit this)
```bash
DRONA_LLM_BACKEND=template
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_key_here
AWS_SECRET_ACCESS_KEY=your_secret_here
OPENROUTER_API_KEY=your_key_here
```

### Phase switching
```bash
# During coding (zero cost, fast feedback)
export DRONA_LLM_BACKEND=template

# During dev testing deep mode (free, real LLM output)
export DRONA_LLM_BACKEND=openrouter

# During final demo recording + when judges run
export DRONA_LLM_BACKEND=bedrock

# bench/run.sh and self_check.py — DRONA_LLM_BACKEND not set → defaults to template
# Judges never need to set any env var to get a passing run
```

### AWS Bedrock verify
```bash
# Confirm your account has Haiku access
aws bedrock list-foundation-models \
  --region us-east-1 \
  --query "modelSummaries[?contains(modelId,'haiku')].[modelId]" \
  --output table
```

---

## 3. ACCOUNTS & SETUP CHECKLIST

```
□ GitHub account         — repo hosting + bench clone at 11 AM
□ AWS Bedrock account    — 950119649691 (existing, verify Haiku enabled)
□ OpenRouter account     — openrouter.ai, get free API key now
□ Anthropic Console      — backup if Bedrock has issues (console.anthropic.com)
```

No other accounts needed. No Devpost. No Unstop portal submission found — submission is a Git link to the council directly.

---

## 4. FILE STRUCTURE — COMPLETE

```
drona/
├── .env                          # gitignored — real secrets
├── .env.example                  # committed — template
├── .gitignore
├── LICENSE                       # MIT
├── README.md                     # quickstart ≤5 min on clean machine
├── Dockerfile
├── docker-compose.yml
├── requirements.txt              # pinned versions
├── self_check.py                 # local harness — 6 tests, no bench repo needed
│
├── drona/
│   ├── __init__.py
│   ├── schema.py                 # all types: Event, BehaviorPattern, Context, etc
│   ├── identity.py               # IdentityLayer — UUID + alias table
│   ├── temporal_index.py         # DuckDB in-process — ingest + range queries
│   ├── signatures.py             # extract_signature + BehaviorPattern.similarity
│   ├── memory.py                 # MemoryStore — incident lifecycle + find_similar
│   ├── causal.py                 # build_causal_chain — 3 deterministic rules
│   ├── graph.py                  # NetworkX DiGraph wrapper
│   ├── engine.py                 # Engine class — ingest + reconstruct_context
│   └── explainer.py              # template / openrouter / bedrock backends
│
├── adapters/
│   ├── __init__.py
│   └── drona_adapter.py          # thin shim — written AFTER bench repo opens
│
├── bench/
│   └── run.sh                    # produces report.json
│
├── tests/
│   ├── test_identity.py
│   ├── test_signatures.py
│   ├── test_engine_canonical.py
│   └── test_engine_rename.py
│
└── writeup/
    ├── drona_writeup.md          # 3-page architectural defense
    └── drona_writeup.pdf         # convert from md before submission
```

---

## 5. REQUIREMENTS.TXT — PINNED

```
duckdb==0.10.3
networkx==3.3
fastapi==0.111.0
uvicorn==0.30.1
boto3==1.34.0
python-dateutil==2.9.0
numpy==1.26.4
```

No anthropic SDK — Bedrock uses `boto3`, OpenRouter uses `urllib.request` (stdlib). Zero extra deps for those two backends.

---

## 6. BUILD STEPS — 24-HOUR SCHEDULE

```
T+00:00  11:00 AM  Repo init + scaffold + self_check.py
T+00:30  11:30 AM  schema.py complete
T+01:00  12:00 PM  identity.py complete + TEST 1 passing
T+01:45  12:45 PM  temporal_index.py complete
T+02:45  01:45 PM  signatures.py complete
T+03:45  02:45 PM  memory.py complete
T+04:30  03:30 PM  causal.py complete
T+05:00  04:00 PM  graph.py complete
T+06:30  05:30 PM  engine.py complete + all 6 self_check tests passing
T+07:15  06:15 PM  explainer.py complete (all 3 backends)
T+07:30  06:30 PM  Bench repo clones + diff schema → drona_adapter.py (20 min)
T+08:00  07:00 PM  bench self_check.py --quick passing on their harness
T+09:00  08:00 PM  bench run.py full battery — report.json produced
T+10:00  09:00 PM  Dockerfile + README + bench/run.sh
T+11:00  10:00 PM  Buffer: fix any bench failures, tune similarity threshold
T+14:00  01:00 AM  Sleep (3 hours minimum)
T+17:00  04:00 AM  Writeup PDF — 3 pages, all 5 sections
T+20:00  07:00 AM  Demo recording — 5 minutes, one take
T+21:00  08:00 AM  Final git push, clean commit history
T+22:00  09:00 AM  Buffer — fix anything that breaks during demo prep
T+24:00  11:00 AM  SUBMISSION DEADLINE
```

---

## 7. COMPLETE SCHEMA — `drona/schema.py`

```python
# drona/schema.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TypedDict, Literal, Any
from enum import Enum
import uuid


# ─── RAW EVENT ────────────────────────────────────────────────────────────────

Event = dict[str, Any]


# ─── INPUT SIGNAL ─────────────────────────────────────────────────────────────

@dataclass
class IncidentSignal:
    incident_id: str
    trigger:     str
    ts:          str
    service:     str | None = None


# ─── OUTPUT TYPES ─────────────────────────────────────────────────────────────

@dataclass
class CausalEdge:
    cause_id:     str
    effect_id:    str
    evidence:     list[Event]
    confidence:   float
    relationship: str = "causes"

@dataclass
class IncidentMatch:
    past_incident_id: str
    similarity:       float
    rationale:        str

@dataclass
class Remediation:
    action:             str
    target:             str
    historical_outcome: str
    confidence:         float

class Context(TypedDict):
    related_events:         list[Event]
    causal_chain:           list[CausalEdge]
    similar_past_incidents: list[IncidentMatch]
    suggested_remediations: list[Remediation]
    confidence:             float
    explain:                str


# ─── BEHAVIORAL SIGNATURE ─────────────────────────────────────────────────────

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

@dataclass
class BehaviorPattern:
    """Service-name-agnostic incident signature. No canonical_ids inside."""
    trigger_type:            TriggerType
    symptom_sequence:        list[SymptomType]
    affected_service_count:  int
    propagation_direction:   PropagationDir
    time_to_first_symptom_s: float

    def similarity(self, other: BehaviorPattern) -> float:
        """4-component weighted similarity. Returns 0.0–1.0."""
        score = 0.0
        if self.trigger_type == other.trigger_type:
            score += 0.30
        score += 0.40 * _lcs_ratio(self.symptom_sequence, other.symptom_sequence)
        if self.propagation_direction == other.propagation_direction:
            score += 0.20
        a, b = self.time_to_first_symptom_s, other.time_to_first_symptom_s
        if a > 0 and b > 0:
            ratio = max(a, b) / min(a, b)
            if ratio < 3.0:
                score += 0.10 * max(0.0, 1 - (ratio - 1) / 2)
        return round(min(1.0, score), 4)


def _lcs_ratio(a: list, b: list) -> float:
    """Order-aware longest common subsequence ratio."""
    if not a or not b:
        return 0.0
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            dp[i][j] = (
                dp[i-1][j-1] + 1 if a[i-1] == b[j-1]
                else max(dp[i-1][j], dp[i][j-1])
            )
    return dp[m][n] / max(m, n)


# ─── INCIDENT MEMORY ──────────────────────────────────────────────────────────

@dataclass
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

---

## 8. IDENTITY LAYER — `drona/identity.py`

**Agent Prompt:**
```
Build drona/identity.py in full. Implements IdentityLayer.

Requirements — all mandatory:
- ServiceNode dataclass: canonical_id (UUID str), aliases (list[str]), 
  first_seen (str), last_seen (str)
- IdentityLayer class with threading.RLock for all state mutations
- _alias_to_cid: dict[str, str]  — name → canonical_id, O(1)
- _nodes: dict[str, ServiceNode] — canonical_id → node

Methods (all must be implemented, no stubs):
  resolve(name: str) -> str
    Creates new ServiceNode on first sight. Returns canonical_id.
  
  handle_rename(old_name: str, new_name: str) -> str
    Adds new_name as alias to existing node. canonical_id unchanged.
    If old_name not yet seen, creates node for it first.
    Returns canonical_id.
  
  handle_dependency_shift(source: str, target: str, 
                           change: str, ts: str) -> tuple[str, str]
    Resolves both services to canonical_ids.
    Returns (source_cid, target_cid). 
    Does NOT modify graph — graph.py handles that.

  current_name(canonical_id: str) -> str
    Returns last alias in the list. Falls back to canonical_id if not found.
  
  all_aliases(canonical_id: str) -> list[str]
    Returns copy of aliases list.
  
  known_services() -> list[str]
    Returns all canonical_ids currently tracked.

Inline test at bottom under if __name__ == "__main__":
  il = IdentityLayer()
  cid1 = il.resolve("payments-svc")
  il.handle_rename("payments-svc", "billing-svc")
  cid2 = il.resolve("billing-svc")
  assert cid1 == cid2
  assert il.current_name(cid1) == "billing-svc"
  assert "payments-svc" in il.all_aliases(cid1)
  assert "billing-svc" in il.all_aliases(cid1)
  
  cid3 = il.resolve("checkout-api")
  assert cid3 != cid1
  src, dst = il.handle_dependency_shift("checkout-api","billing-svc","add","2026-05-10T14:00:00Z")
  assert src == cid3
  assert dst == cid1
  print("identity: all tests passed")

No imports beyond stdlib (uuid, threading, dataclasses). Complete implementation.
```

---

## 9. TEMPORAL INDEX — `drona/temporal_index.py`

**Agent Prompt:**
```
Build drona/temporal_index.py in full. Implements TemporalIndex using DuckDB.

Imports: duckdb, json, datetime, threading
No other external imports.

Schema — single table:
  CREATE TABLE events (
    ts           TIMESTAMP,
    canonical_id VARCHAR,
    kind         VARCHAR,
    raw          JSON,
    is_anomaly   BOOLEAN DEFAULT FALSE,
    anomaly_type VARCHAR DEFAULT ''
  )
  CREATE INDEX idx_cid_ts ON events(canonical_id, ts)
  CREATE INDEX idx_ts ON events(ts)

State:
  self.db = duckdb.connect(":memory:")
  self._baselines: dict[str, float]   — f"{cid}:{metric_name}" → EMA value
  self._lock: threading.RLock

Methods:

build_row(canonical_id, event, ts) -> tuple | None
  Computes is_anomaly + anomaly_type inline.
  Returns a tuple (ts, canonical_id, kind, json.dumps(event), is_anomaly, anomaly_type)
  or None if event should not be stored (topology events).
  
  Anomaly rules:
    kind=="metric": value > 2.5 × baseline AND baseline > 0 → metric_spike
      Update baseline: _baselines[key] = 0.9*baseline + 0.1*value
      First time seeing a metric: set baseline = value, NOT anomaly
    kind=="log" AND level=="error": → error_log
    kind=="trace": any span dur_ms > 3000 → trace_slowdown
    Everything else: not anomaly

insert_batch(rows: list[tuple]) -> None
  self.db.executemany("INSERT INTO events VALUES (?,?,?,?,?,?)", rows)
  Thread-safe via lock.

query_window_all(start: datetime, end: datetime) -> list[dict]
  SELECT raw FROM events WHERE ts BETWEEN ? AND ? ORDER BY ts
  Returns list of parsed JSON dicts.

query_window(canonical_id: str, start: datetime, end: datetime) -> list[dict]
  SELECT raw FROM events WHERE canonical_id=? AND ts BETWEEN ? AND ? ORDER BY ts

get_anomalies(start: datetime, end: datetime) -> list[dict]
  SELECT raw, anomaly_type FROM events 
  WHERE is_anomaly=TRUE AND ts BETWEEN ? AND ?
  ORDER BY ts
  Returns list of {"event": dict, "type": str}

close() -> None
  self.db.close()

Throughput target: ≥ 1000 events/sec via batch inserts.
All threads share one DuckDB connection via the lock.
No placeholder code. Full implementation.
```

---

## 10. SIGNATURES — `drona/signatures.py`

**Agent Prompt:**
```
Build drona/signatures.py in full.

from drona.schema import (BehaviorPattern, TriggerType, SymptomType, PropagationDir)
from drona.identity import IdentityLayer
from datetime import datetime
from dateutil.parser import parse as parse_dt
import re

Single function: extract_signature(
    events: list[dict],
    anomalies: list[dict],
    identity_layer: IdentityLayer,
    deploy_ts: str | None = None
) -> BehaviorPattern

Step 1 — trigger_type:
  If any event["kind"] == "deploy": TriggerType.DEPLOY
  Elif any event["trigger"] string contains "alert": TriggerType.METRIC_ALERT  
  Elif any log event where "timeout" or "connection refused" or "unavailable" 
       in msg.lower(): TriggerType.DEPENDENCY_FAILURE
  Else: TriggerType.UNKNOWN

Step 2 — symptom_sequence (ordered by anomaly timestamp, dedup consecutive):
  For each anomaly in time-sorted order:
    "metric_spike" + "latency" in event["name"].lower() → LATENCY_SPIKE
    "metric_spike" + "error" in event["name"].lower() → ERROR_RATE_SPIKE
    "metric_spike" + anything else → LATENCY_SPIKE (default metric spike)
    "error_log" + "timeout" in msg → UPSTREAM_TIMEOUT
    "error_log" other → ERROR_RATE_SPIKE
    "trace_slowdown" → TRACE_SLOWDOWN
  Dedup: remove consecutive duplicates (keep first occurrence)

Step 3 — affected_service_count:
  Unique canonical_ids across all events.
  For each event: resolve svc = event.get("service") or event.get("svc")
  If svc: identity_layer.resolve(svc)
  affected_service_count = len(unique canonical_ids)
  Cap at 10 to prevent outlier distortion.

Step 4 — propagation_direction:
  If affected_service_count == 1: PropagationDir.ISOLATED
  Else: PropagationDir.DOWNSTREAM (default for multi-service)

Step 5 — time_to_first_symptom_s:
  If deploy_ts is not None AND len(anomalies) > 0:
    first_anomaly_ts = parse_dt(anomalies[0]["event"]["ts"])
    deploy_dt = parse_dt(deploy_ts)
    delta = (first_anomaly_ts - deploy_dt).total_seconds()
    return max(0.0, delta)
  Else: 0.0

Return BehaviorPattern with all 5 fields populated.
No placeholder code. Full implementation.
```

---

## 11. MEMORY STORE — `drona/memory.py`

**Agent Prompt:**
```
Build drona/memory.py in full.

from drona.schema import (IncidentMemory, BehaviorPattern, IncidentMatch, 
                           Remediation)
from drona.signatures import extract_signature
from drona.identity import IdentityLayer
from dateutil.parser import parse as parse_dt
import threading

class MemoryStore:
  State:
    _incidents: list[IncidentMemory]          — closed incidents
    _open: dict[str, dict]                    — incident_id → state dict
    _lock: threading.RLock

  open_incident(incident_id, ts, initial_events, primary_cid) -> None
    state = {
      "opened_at": ts,
      "events": list(initial_events),
      "deploy_ts": None,
      "primary_cid": primary_cid
    }
    _open[incident_id] = state

  update_open(incident_id, events: list[dict]) -> None
    If incident_id in _open:
      _open[incident_id]["events"].extend(events)
      For each event: if kind=="deploy" and deploy_ts is None:
        _open[incident_id]["deploy_ts"] = event["ts"]

  close_incident(incident_id, remediation_event, anomalies, identity_layer) -> IncidentMemory | None
    Pop from _open. If not present: return None.
    sig = extract_signature(state["events"], anomalies, identity_layer, state["deploy_ts"])
    target_svc = remediation_event.get("target", "")
    target_cid = identity_layer.resolve(target_svc) if target_svc else state["primary_cid"]
    mem = IncidentMemory(
      incident_id=incident_id,
      signature=sig,
      epicentre_canonical_id=state["primary_cid"],
      remediation_action=remediation_event.get("action", "unknown"),
      remediation_target_cid=target_cid,
      outcome=remediation_event.get("outcome", "unknown"),
      opened_at=state["opened_at"],
      closed_at=remediation_event.get("ts", ""),
      context_events=state["events"]
    )
    _incidents.append(mem)
    return mem

  find_similar(signature, top_k=5, query_ts=None) -> list[tuple[float, IncidentMemory]]
    For each mem in _incidents:
      base_sim = signature.similarity(mem.signature)
      if base_sim <= 0.35: continue
      
      # G4: recency decay — half-life 3 simulated days, affects 30% of score
      if query_ts and mem.closed_at:
        try:
          age_days = (parse_dt(query_ts) - parse_dt(mem.closed_at)).total_seconds() / 86400
          decay = 0.5 ** (age_days / 3.0)
          sim = base_sim * (0.70 + 0.30 * decay)
        except Exception:
          sim = base_sim
      else:
        sim = base_sim
      
      scored.append((round(sim, 4), mem))
    
    Sort descending by sim. Return top_k.

  get_remediation_suggestions(
      similar: list[tuple[float, IncidentMemory]], 
      identity_layer: IdentityLayer
  ) -> list[Remediation]
    For each (score, mem) in similar[:3]:
      try:
        target_name = identity_layer.current_name(mem.remediation_target_cid)
      except:
        target_name = mem.remediation_target_cid
      outcome_mult = 0.9 if mem.outcome == "resolved" else 0.4
      confidence = round(score * outcome_mult, 3)
      yield Remediation(
        action=mem.remediation_action,
        target=target_name,
        historical_outcome=mem.outcome,
        confidence=confidence
      )

  incident_count() -> int: len(_incidents)
  open_count() -> int: len(_open)

All public methods thread-safe via _lock. No placeholder code.
```

---

## 12. CAUSAL CHAIN — `drona/causal.py`

**Agent Prompt:**
```
Build drona/causal.py in full.

from drona.schema import CausalEdge, Event
from drona.identity import IdentityLayer
from dateutil.parser import parse as parse_dt
import re

build_causal_chain(
    events: list[dict],
    anomalies: list[dict],
    identity_layer: IdentityLayer
) -> list[CausalEdge]

THREE RULES — produce edges, then deduplicate:

RULE 1 — Deploy → Metric/Trace Anomaly within 5 minutes (confidence 0.85–0.95)
  deploys = [e for e in events if e.get("kind") == "deploy"]
  For each deploy D:
    deploy_cid = identity_layer.resolve(D["service"])
    deploy_ts = parse_dt(D["ts"])
    For each anomaly A in anomalies where A["type"] in ["metric_spike","trace_slowdown"]:
      a_ts = parse_dt(A["event"]["ts"])
      delta = (a_ts - deploy_ts).total_seconds()
      if 0 < delta < 300:
        confidence = min(0.95, 0.85 + (1 - delta/300) * 0.10)
        svc = A["event"].get("service") or A["event"].get("svc","")
        effect_cid = identity_layer.resolve(svc) if svc else deploy_cid
        Append CausalEdge(deploy_cid, effect_cid, [D, A["event"]], confidence, "causes")

RULE 2 — Upstream Timeout Log → Caller (confidence 0.75)
  logs = [e for e in events if e.get("kind")=="log" and e.get("level")=="error"]
  For each log L:
    msg = L.get("msg","").lower()
    if any word in ["timeout","connection refused","unavailable","unreachable"] in msg:
      caller_cid = identity_layer.resolve(L["service"])
      callee_name = _extract_callee_from_msg(L.get("msg",""))
      if callee_name:
        callee_cid = identity_layer.resolve(callee_name)
        if callee_cid != caller_cid:
          Append CausalEdge(callee_cid, caller_cid, [L], 0.75, "causes")

RULE 3 — Trace Span Slowdown → Caller (confidence 0.80)
  traces = [e for e in events if e.get("kind")=="trace"]
  For each trace T:
    spans = T.get("spans",[])
    for i in range(len(spans)-1):
      downstream = spans[i+1]
      upstream = spans[i]
      if downstream.get("dur_ms",0) > 3000:
        cause_cid = identity_layer.resolve(downstream.get("svc",""))
        effect_cid = identity_layer.resolve(upstream.get("svc",""))
        if cause_cid != effect_cid:
          Append CausalEdge(cause_cid, effect_cid, [T], 0.80, "causes")

POST-PROCESSING:
  Deduplicate by (cause_id, effect_id) — keep highest confidence edge
  Remove self-loops (cause_id == effect_id)
  Sort by confidence descending
  Return list

Helper: _extract_callee_from_msg(msg: str) -> str | None
  # Try to find service names embedded in error messages
  patterns = [
    r"calling ([a-z][a-z0-9\-]+(?:-svc|-api|-service|-gateway))",
    r"connect(?:ion)? to ([a-z][a-z0-9\-]+(?:-svc|-api|-service|-gateway))",
    r"([a-z][a-z0-9\-]+(?:-svc|-api|-service|-gateway)) (?:timed out|unreachable|unavailable)",
  ]
  for p in patterns:
    m = re.search(p, msg, re.IGNORECASE)
    if m: return m.group(1)
  # Fallback: any token with service-like suffix
  tokens = re.findall(r'[a-z][a-z0-9\-]+(?:-svc|-api|-service|-gateway)', msg, re.IGNORECASE)
  return tokens[0].lower() if tokens else None

No placeholder code. Full implementation.
```

---

## 13. GRAPH — `drona/graph.py`

**Agent Prompt:**
```
Build drona/graph.py in full.

import networkx as nx
from datetime import datetime
from drona.schema import CausalEdge
import threading

class ServiceGraph:
  """NetworkX DiGraph where nodes = canonical_ids, edges = observed relationships."""
  
  State:
    _g: nx.DiGraph
    _lock: threading.RLock

  add_service(canonical_id: str, aliases: list[str]) -> None
    _g.add_node(canonical_id, aliases=aliases, first_seen=datetime.utcnow().isoformat())

  record_call(caller_cid: str, callee_cid: str, ts: str) -> None
    If edge exists: increment count, update last_seen
    Else: add_edge with count=1, last_seen=ts

  add_causal_edges(edges: list[CausalEdge]) -> None
    For each edge:
      If edge exists: update confidence to max(existing, new)
      Else: add_edge with confidence and relationship

  remove_dependency(source_cid: str, target_cid: str) -> None
    If edge exists: remove it

  get_upstream(canonical_id: str) -> list[str]
    list(_g.predecessors(canonical_id))

  get_downstream(canonical_id: str) -> list[str]
    list(_g.successors(canonical_id))

  propagation_direction(canonical_ids: list[str]) -> str
    If len <= 1: return "isolated"
    For any pair (a,b) in canonical_ids: if edge a→b exists: return "downstream"
    Return "downstream"  # safe default

  node_count() -> int
  edge_count() -> int

All methods thread-safe. No placeholder code.
```

---

## 14. ENGINE — `drona/engine.py`

**Agent Prompt:**
```
Build drona/engine.py in full. This is the submission interface.

from drona.schema import (Event, IncidentSignal, Context, CausalEdge, 
                           IncidentMatch, Remediation, BehaviorPattern)
from drona.identity import IdentityLayer
from drona.temporal_index import TemporalIndex
from drona.memory import MemoryStore
from drona.causal import build_causal_chain
from drona.signatures import extract_signature
from drona.graph import ServiceGraph
from drona.explainer import generate_explain
from datetime import datetime, timedelta
from dateutil.parser import parse as parse_dt
from typing import Iterable, Literal
import threading
import re

class Engine:
  """Main Drona engine. Thread-safe. One instance per benchmark seed."""
  
  def __init__(self):
    self._identity = IdentityLayer()
    self._index    = TemporalIndex()
    self._memory   = MemoryStore()
    self._graph    = ServiceGraph()
    self._lock     = threading.RLock()
    self._batch_buffer: list[tuple] = []
    self._BATCH_SIZE = 50

  def ingest(self, events: Iterable[Event]) -> None:
    """Consume event stream. Batch-inserts to DuckDB every 50 events."""
    for event in events:
      row = self._process_event(event)
      if row is not None:
        self._batch_buffer.append(row)
        if len(self._batch_buffer) >= self._BATCH_SIZE:
          self._index.insert_batch(self._batch_buffer)
          self._batch_buffer.clear()
    if self._batch_buffer:
      self._index.insert_batch(self._batch_buffer)
      self._batch_buffer.clear()

  def _process_event(self, event: Event) -> tuple | None:
    """Process one event. Returns DuckDB row tuple or None."""
    kind = event.get("kind", "")
    
    # G1: Handle ALL topology event types, not just rename
    if kind == "topology":
      change = event.get("change", "")
      if change == "rename":
        self._identity.handle_rename(
          event.get("from", ""), event.get("to", "")
        )
      elif change in ("dependency_add", "link", "add"):
        src = event.get("from") or event.get("source", "")
        dst = event.get("to") or event.get("target", "")
        if src and dst:
          src_cid, dst_cid = self._identity.handle_dependency_shift(src, dst, change, event.get("ts",""))
          self._graph.record_call(src_cid, dst_cid, event.get("ts",""))
      elif change in ("dependency_remove", "unlink", "remove"):
        src = event.get("from") or event.get("source", "")
        dst = event.get("to") or event.get("target", "")
        if src and dst:
          src_cid = self._identity.resolve(src)
          dst_cid = self._identity.resolve(dst)
          self._graph.remove_dependency(src_cid, dst_cid)
      return None  # topology events never stored in temporal index

    # Resolve service to canonical_id
    svc_raw = (
      event.get("service") or
      event.get("svc") or
      self._extract_svc_from_trigger(event.get("trigger", "")) or
      "__unknown__"
    )
    cid = self._identity.resolve(svc_raw)
    ts  = parse_dt(event["ts"])

    # Track deploy windows
    if kind == "deploy":
      pass  # temporal index stores it; memory store reads it from query

    # Open incident
    elif kind == "incident_signal":
      window_start = ts - timedelta(minutes=10)
      pre_events   = self._index.query_window_all(window_start, ts)
      # Find most recent deploy in pre-window
      deploy_ts = None
      for e in pre_events:
        if e.get("kind") == "deploy":
          deploy_ts = e["ts"]
          break
      self._memory.open_incident(event["incident_id"], event["ts"], pre_events, cid)
      if deploy_ts:
        with self._lock:
          if event["incident_id"] in self._memory._open:
            self._memory._open[event["incident_id"]]["deploy_ts"] = deploy_ts

    # Close incident
    elif kind == "remediation":
      iid = event.get("incident_id", "")
      if iid in self._memory._open:
        state = self._memory._open[iid]
        opened_ts  = parse_dt(state["opened_at"])
        anomalies  = self._index.get_anomalies(
          opened_ts - timedelta(minutes=10), ts
        )
        self._memory.close_incident(iid, event, anomalies, self._identity)

    return self._index.build_row(cid, event, ts)

  def reconstruct_context(
    self,
    signal: IncidentSignal,
    mode:   Literal["fast","deep"] = "fast"
  ) -> Context:
    """Reconstruct incident context. fast < 2s p95. deep < 6s p95."""
    ts           = parse_dt(signal.ts)
    window_start = ts - timedelta(minutes=10)
    window_end   = ts + timedelta(minutes=2)

    # 1. Collect window events
    raw_events = self._index.query_window_all(window_start, window_end)
    
    # G2: Expand window if empty
    if not raw_events:
      raw_events = self._index.query_window_all(
        ts - timedelta(minutes=30),
        ts + timedelta(minutes=5)
      )

    anomalies = self._index.get_anomalies(
      ts - timedelta(minutes=30), ts + timedelta(minutes=5)
    )

    # 2. Rank + deduplicate related events, add provenance (G3)
    related = self._rank_related(raw_events, anomalies, signal)

    # 3. Causal chain
    chain = build_causal_chain(related, anomalies, self._identity)
    self._graph.add_causal_edges(chain)

    # 4. Behavioral signature — no service names
    deploy_ts = next((e["ts"] for e in related if e.get("kind")=="deploy"), None)
    sig = extract_signature(related, anomalies, self._identity, deploy_ts)

    # 5. Similar past incidents (topology-independent)
    scored  = self._memory.find_similar(sig, top_k=5, query_ts=signal.ts)
    similar = [
      IncidentMatch(
        past_incident_id=mem.incident_id,
        similarity=score,
        rationale=self._explain_match(sig, mem.signature)
      )
      for score, mem in scored
    ]

    # 6. Remediation suggestions
    remediations = list(
      self._memory.get_remediation_suggestions(scored, self._identity)
    )

    # 7. Confidence
    confidence = self._compute_confidence(chain, similar)

    # 8. Explain
    explain = generate_explain(related, chain, similar, mode, self._identity)

    return Context(
      related_events=related,
      causal_chain=chain,
      similar_past_incidents=similar,
      suggested_remediations=remediations,
      confidence=confidence,
      explain=explain,
    )

  def _rank_related(
    self, events: list, anomalies: list, signal: IncidentSignal
  ) -> list[Event]:
    """Rank by relevance, deduplicate, add _provenance field. (G3)"""
    anomaly_ts_set = {a["event"]["ts"] for a in anomalies}
    
    def score(e: dict) -> int:
      s = 0
      k = e.get("kind","")
      if k == "deploy":                                      s += 10
      if k == "metric" and e.get("ts") in anomaly_ts_set:   s += 9
      if k == "log" and e.get("level") == "error":           s += 8
      if k == "trace":                                       s += 6
      if k == "metric":                                      s += 3
      if k == "log":                                         s += 2
      return s

    seen:    set  = set()
    deduped: list = []
    for e in sorted(events, key=score, reverse=True):
      key = f"{e.get('ts','')}:{e.get('service','')}{e.get('svc','')}:{e.get('kind','')}"
      if key not in seen:
        seen.add(key)
        e["_provenance"] = {
          "relevance_score": score(e),
          "is_anomaly": e.get("ts","") in anomaly_ts_set,
          "source_ts": e.get("ts","")
        }
        deduped.append(e)
    return deduped

  def _explain_match(
    self, current: BehaviorPattern, past: BehaviorPattern
  ) -> str:
    """Human-readable rationale for why two incidents matched."""
    parts = []
    if current.trigger_type == past.trigger_type:
      parts.append(f"same trigger ({current.trigger_type.value})")
    overlap = set(current.symptom_sequence) & set(past.symptom_sequence)
    if overlap:
      parts.append(f"shared symptoms: {', '.join(s.value for s in overlap)}")
    if current.propagation_direction == past.propagation_direction:
      parts.append(f"same propagation ({current.propagation_direction.value})")
    return "; ".join(parts) if parts else "behavioral pattern similarity"

  def _compute_confidence(
    self, chain: list, similar: list
  ) -> float:
    """Overall confidence: 0.0–1.0."""
    c = 0.0
    if chain:
      c += min(0.4, len(chain) * 0.12)
      c += chain[0].confidence * 0.2
    if similar:
      c += similar[0].similarity * 0.4
    return round(min(1.0, c), 3)

  def _extract_svc_from_trigger(self, trigger: str) -> str | None:
    """G5: Robust service extraction from trigger strings."""
    if not trigger:
      return None
    patterns = [
      r"alert:([^/\[\]]+)/",
      r"alert\[([^\]]+)\]",
      r"^([a-z][a-z0-9\-]+):",
    ]
    for p in patterns:
      m = re.search(p, trigger, re.IGNORECASE)
      if m:
        return m.group(1)
    tokens = re.findall(
      r'[a-z][a-z0-9\-]+(?:-svc|-api|-service|-gateway)', trigger, re.IGNORECASE
    )
    return tokens[0].lower() if tokens else None

  def close(self) -> None:
    """Release DuckDB connection."""
    self._index.close()
```

---

## 15. EXPLAINER — `drona/explainer.py`

**Agent Prompt:**
```
Build drona/explainer.py in full. Three backends, controlled by DRONA_LLM_BACKEND.

Imports: os, json, re, socket, urllib.request, boto3 (conditional), threading

BACKENDS:
  "template"   → pure string template, zero cost, zero network (DEFAULT)
  "openrouter" → urllib.request to openrouter.ai, free Llama 3.1 8B
  "bedrock"    → boto3 bedrock-runtime, Claude 3 Haiku

SYSTEM_PROMPT (used by both LLM backends):
  "You are a senior SRE analyzing a production incident. Respond in exactly 
  3 sentences. Sentence 1: what happened and which service. Sentence 2: most 
  likely root cause. Sentence 3: recommended immediate action. Be specific, 
  technical, and concise. No preamble. No bullet points. Max 80 words."

generate_explain(related, chain, similar, mode, identity) -> str
  If mode != "deep": return _template(related, chain, similar, identity)
  backend = os.getenv("DRONA_LLM_BACKEND", "template")
  Try:
    prompt = _build_prompt(related, chain, similar, identity)
    if backend == "bedrock":   return _bedrock(prompt)
    if backend == "openrouter": return _openrouter(prompt)
    return _template(related, chain, similar, identity)
  Except ANY exception:
    return _template(related, chain, similar, identity) + " [deep mode unavailable]"

_template(related, chain, similar, identity) -> str
  Part 1 — what happened:
    Find first deploy event in related.
    If found: "A deployment of {current_name(resolve(service))} ({version}) 
               preceded this incident."
    Else: "No recent deployment identified in the observation window."
  
  Part 2 — likely cause:
    If chain has edges:
      c = chain[0]
      cause = identity.current_name(c.cause_id)   (try/except → use c.cause_id)
      effect = identity.current_name(c.effect_id)  (try/except → use c.effect_id)
      "Likely causal path: {cause} → {effect} (confidence {c.confidence:.0%})."
    Else: "No clear causal path identified."
  
  Part 3 — recommendation:
    If similar:
      m = similar[0]
      "Closest match: {m.past_incident_id} ({m.similarity:.0%} similarity); {m.rationale}."
    Else: "No historical match found — treat as novel incident."
  
  Return " ".join([part1, part2, part3])

_build_prompt(related, chain, similar, identity) -> str
  Build compact summary (not raw event data):
  Lines:
    f"Services involved: {unique service names from related, comma-separated}"
    f"Deploy: {service} → {version}" if deploy found
    f"Metric spike: {name} = {value} on {service}" if metric anomaly found
    f"Error: {msg[:100]}" if error log found
    f"Causal edge: {cause_name} → {effect_name} ({confidence:.0%})" if chain
    f"Similar past: {incident_id} ({similarity:.0%}) — {rationale}" if similar

_bedrock(user_prompt: str) -> str
  G6: socket.setdefaulttimeout(4.5)
  client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION","us-east-1"))
  body = {
    "anthropic_version": "bedrock-2023-05-31",
    "max_tokens": 150,
    "system": SYSTEM_PROMPT,
    "messages": [{"role": "user", "content": user_prompt}]
  }
  response = client.invoke_model(
    modelId="anthropic.claude-3-haiku-20240307-v1:0",
    body=json.dumps(body),
    contentType="application/json",
    accept="application/json"
  )
  result = json.loads(response["body"].read())
  return result["content"][0]["text"].strip()

_openrouter(user_prompt: str) -> str
  G6: socket.setdefaulttimeout(4.5)
  payload = {
    "model": "meta-llama/llama-3.1-8b-instruct:free",
    "messages": [
      {"role": "system", "content": SYSTEM_PROMPT},
      {"role": "user", "content": user_prompt}
    ],
    "max_tokens": 150
  }
  req = urllib.request.Request(
    "https://openrouter.ai/api/v1/chat/completions",
    data=json.dumps(payload).encode(),
    headers={
      "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY','')}",
      "Content-Type": "application/json",
      "HTTP-Referer": "https://archzos.com",
      "X-Title": "Drona"
    },
    method="POST"
  )
  with urllib.request.urlopen(req, timeout=4.5) as resp:
    data = json.loads(resp.read())
  return data["choices"][0]["message"]["content"].strip()

No placeholder code. All error handling is in the outer try/except in generate_explain.
```

---

## 16. SELF-CHECK HARNESS — `self_check.py`

**Agent Prompt:**
```
Build self_check.py — complete local test harness. 6 tests.
Must run with: python self_check.py
No bench repo required.

Import and instantiate Engine from drona.engine.
Import IncidentSignal from drona.schema.
Import IdentityLayer from drona.identity.

SAMPLE_EVENTS = [verbatim 7 events from spec]
SECOND_WAVE = [5 events for billing-svc incident]

TEST 1 — Identity rename:
  il = IdentityLayer()
  cid1 = il.resolve("payments-svc")
  il.handle_rename("payments-svc", "billing-svc")
  cid2 = il.resolve("billing-svc")
  assert cid1 == cid2, "FAIL: rename broke canonical_id"
  assert il.current_name(cid1) == "billing-svc"

TEST 2 — Canonical context reconstruction:
  engine = Engine()
  engine.ingest(SAMPLE_EVENTS[:5])  # everything before incident_signal
  signal = IncidentSignal("INC-714","alert:checkout-api/error-rate>5%","2026-05-10T14:32:11Z")
  import time; t0 = time.time()
  ctx = engine.reconstruct_context(signal, mode="fast")
  latency_ms = (time.time()-t0)*1000
  assert len(ctx["related_events"]) > 0
  assert any(e.get("kind")=="deploy" for e in ctx["related_events"])
  assert len(ctx["causal_chain"]) > 0
  assert ctx["causal_chain"][0].confidence >= 0.5
  assert latency_ms < 2000, f"FAIL: fast mode {latency_ms:.0f}ms > 2000ms"
  assert "_provenance" in ctx["related_events"][0], "FAIL: missing provenance"

TEST 3 — Rename robustness (THE KEY TEST):
  engine2 = Engine()
  engine2.ingest(SAMPLE_EVENTS)  # full first wave including remediation
  engine2.ingest(SECOND_WAVE[:3])  # second wave up to but not including incident
  signal2 = IncidentSignal("INC-715","alert:checkout-api/error-rate>5%","2026-05-11T10:01:30Z")
  ctx2 = engine2.reconstruct_context(signal2, mode="fast")
  matched = [m.past_incident_id for m in ctx2["similar_past_incidents"]]
  assert "INC-714" in matched, f"FAIL: rename robustness. Got: {matched}"

TEST 4 — Ingest throughput ≥ 1000/sec:
  import random
  events_load = [
    {"ts":f"2026-05-10T12:{i//60:02d}:{i%60:02d}Z","kind":"metric",
     "service":f"svc-{i%8}","name":"latency_p99_ms","value":random.randint(100,6000)}
    for i in range(1000)
  ]
  engine3 = Engine()
  t0 = time.time()
  engine3.ingest(events_load)
  rate = 1000 / (time.time()-t0)
  assert rate >= 1000, f"FAIL: {rate:.0f} events/sec < 1000"

TEST 5 — Window expansion on empty:
  engine4 = Engine()
  engine4.ingest([{"ts":"2026-05-10T14:00:00Z","kind":"deploy",
                   "service":"orphan-svc","version":"v1.0","actor":"ci"}])
  signal3 = IncidentSignal("INC-999","alert:orphan-svc/latency","2026-05-10T18:00:00Z")
  ctx3 = engine4.reconstruct_context(signal3, mode="fast")
  # Should not crash even with empty window — expanded to ±30min
  assert isinstance(ctx3["related_events"], list)
  assert isinstance(ctx3["explain"], str) and len(ctx3["explain"]) > 0

TEST 6 — Dependency shift topology:
  engine5 = Engine()
  engine5.ingest([
    {"ts":"2026-05-10T10:00:00Z","kind":"topology",
     "change":"dependency_add","from":"checkout-api","to":"payments-svc"},
    {"ts":"2026-05-10T11:00:00Z","kind":"topology",
     "change":"rename","from":"payments-svc","to":"billing-svc"},
  ])
  cid_pay = engine5._identity.resolve("payments-svc")
  cid_bill = engine5._identity.resolve("billing-svc")
  assert cid_pay == cid_bill, "FAIL: rename not tracked after dependency_add"

Print: "=== DRONA SELF CHECK ===" then each test PASS/FAIL with latency where relevant.
Print final: "X/6 passed" where X is the count of passing tests.
sys.exit(0) if all pass, sys.exit(1) if any fail.
```

---

## 17. ADAPTER SHIM — `adapters/drona_adapter.py`

**Write this AFTER bench repo opens. Template:**

```
Build adapters/drona_adapter.py — written after Anvil-P-E repo opens at 11 AM.

Steps:
1. Open Anvil-P-E/bench-p02-context/schema.py
2. Open Anvil-P-E/bench-p02-context/adapter.py
3. Diff their IncidentSignal fields against drona.schema.IncidentSignal
4. Diff their Context fields against drona.schema.Context
5. Write the shim mapping any different field names

Template (fill in diffs after repo opens):

from adapter import Adapter
from schema import Event, IncidentSignal, Context
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from drona.engine import Engine as _Engine
from drona.schema import IncidentSignal as _DronaSignal

class Engine(Adapter):
    def __init__(self):
        self._e = _Engine()

    def ingest(self, events):
        # If their Event type differs: convert here
        self._e.ingest(events)

    def reconstruct_context(self, signal, mode="fast"):
        # Map their IncidentSignal fields to ours
        drona_signal = _DronaSignal(
            incident_id=signal.incident_id,   # adjust field names if different
            trigger=signal.trigger,
            ts=signal.ts,
            service=getattr(signal, "service", None)
        )
        ctx = self._e.reconstruct_context(drona_signal, mode)
        # If their Context TypedDict has different keys: map here
        return ctx

    def close(self):
        self._e.close()

Time budget: 20 minutes max. All logic is in drona/engine.py — adapter is pure mapping.
```

---

## 18. DOCKERFILE + SUPPORTING FILES

### Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install deps first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# DRONA_LLM_BACKEND defaults to template — zero egress, judges need no API keys
ENV DRONA_LLM_BACKEND=template
ENV PYTHONPATH=/app

# Self-check is the default entrypoint
CMD ["python", "self_check.py"]
```

### bench/run.sh
```bash
#!/bin/bash
set -e

echo "═══════════════════════════════════════"
echo "  DRONA — Anvil P·02 Benchmark Runner  "
echo "═══════════════════════════════════════"

# Step 1: Run local self-check first
echo ""
echo "[ Local self-check ]"
python self_check.py
echo ""

# Step 2: If bench repo is available, run full benchmark
BENCH_DIR="../Anvil-P-E/bench-p02-context"
if [ -d "$BENCH_DIR" ]; then
  echo "[ Bench harness found — running full evaluation ]"
  
  # Copy adapter
  cp adapters/drona_adapter.py "$BENCH_DIR/adapters/"
  cd "$BENCH_DIR"
  
  # Quick check first
  echo "[ Quick check (2 seeds) ]"
  python self_check.py --adapter adapters.drona_adapter:Engine --quick
  
  # Full run
  echo "[ Full run (5 seeds) ]"
  python run.py \
    --adapter adapters.drona_adapter:Engine \
    --mode fast \
    --seeds 9999 31415 27182 16180 11235 \
    --n-services 20 \
    --days 14 \
    --out ../../drona/report.json
  
  echo "[ report.json written ]"
  cat ../../drona/report.json | python -m json.tool
else
  echo "[ Bench repo not found at $BENCH_DIR ]"
  echo "  Clone with: git clone https://github.com/Sauhard74/Anvil-P-E"
  echo "  Then re-run bench/run.sh"
fi
```

### README.md
```markdown
# Drona — Persistent Context Engine for AI SRE
**Anvil Hackathon · P·02 · May 2026**

Drona ingests production telemetry streams and builds operational memory that
survives service renames and topology drift. At incident time it reconstructs
causal context, surfaces similar historical incidents (topology-independent),
and suggests validated remediations.

## Quickstart (≤5 min on clean machine)

```bash
git clone <repo-url> drona && cd drona
pip install -r requirements.txt
python self_check.py     # must show 6/6 passed
```

## Docker

```bash
docker build -t drona .
docker run drona          # runs self_check.py, no API keys needed
```

## Benchmark (after Anvil-P-E repo available)

```bash
bash bench/run.sh
# Produces report.json
```

## Deep Mode (optional)

Drona defaults to `DRONA_LLM_BACKEND=template` (zero egress).
For Claude-generated incident narratives:

```bash
export DRONA_LLM_BACKEND=bedrock
export AWS_REGION=us-east-1
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
python self_check.py
```

## Egress Declaration

| Backend | Egress | Model | Cost |
|---|---|---|---|
| template (default) | None | N/A | $0 |
| bedrock | AWS Bedrock | claude-3-haiku | ~$0.03 total |
| openrouter | openrouter.ai | llama-3.1-8b-instruct:free | $0 |

Deep mode only affects the `explain` string field. All scored metrics
(recall, causal chain, related events, remediations) are computed locally
with no network calls.

## Architecture

```
IdentityLayer     canonical UUID per service + alias table → survives renames
TemporalIndex     DuckDB in-process → sub-ms range queries, ≥1000 events/sec
BehaviorPattern   service-name-agnostic incident shape → topology-independent match
MemoryStore       closed incidents + recency-decayed similarity search  
CausalChain       3 deterministic rules → no LLM on critical path
ServiceGraph      NetworkX DiGraph → causal edge accumulation
```

## Dependencies

```
duckdb==0.10.3
networkx==3.3
fastapi==0.111.0
uvicorn==0.30.1
boto3==1.34.0
python-dateutil==2.9.0
numpy==1.26.4
```
```

---

## 19. ADDITIONAL AGENT PROMPTS

### PROMPT: Debug failing bench test
```
[PASTE META-PROMPT FROM SECTION 0]

The bench harness is failing on this axis: [paste failing metric name + value]
My current report.json shows: [paste relevant section]
The component most likely responsible: [paste file content]

Diagnose the failure. Show the minimal fix. Do not refactor other components.
If it's a schema field name mismatch, show the exact adapter patch needed.
```

### PROMPT: Tune similarity threshold
```
[META-PROMPT]

My rename robustness test is marginal — INC-714 appears in similar_past_incidents
but with low similarity score [X]. 

Current BehaviorPattern.similarity() weights:
- trigger match: 30%
- LCS symptom sequence: 40%
- propagation direction: 20%
- time-to-symptom: 10%

The two patterns being compared:
  Pattern 1 (INC-714): [paste values]
  Pattern 2 (INC-715): [paste values]

Adjust the weights to improve recall without hurting precision on non-matching 
incident pairs. Show the updated similarity() method only.
```

### PROMPT: Writeup section — memory representation
```
[META-PROMPT]

Write the "Memory Representation" section of the Drona 3-page writeup PDF.
Target: 350-400 words, 3 paragraphs.

Defend these decisions in order:
1. canonical_id + alias table (not string matching, not embedding on service names)
2. BehaviorPattern with zero service names (LCS on categorical sequences, not cosine)
3. Recency decay in find_similar (half-life 3 days, affects 30% of score)
4. DuckDB in-memory (no external DB, judges run in one command)

Tone: senior systems engineer defending architecture choices. Direct. Technical.
No marketing language. Cite the design decisions explicitly.
```

### PROMPT: Writeup section — drift handling
```
[META-PROMPT]

Write the "Drift-Handling Strategy" section of the Drona 3-page writeup.
Target: 250-300 words, 2 paragraphs.

Cover:
1. handle_rename() as the single primitive needed — O(1), no data migration
2. G1: dependency shifts also handled (add/remove edges in ServiceGraph)
3. Why ALL downstream components benefit automatically (they use canonical_id only)
4. The chaos test scenario: topology shift mid-evaluation — how Drona handles it

Cite: "The system inherits correct naming for free from the alias table."
```

### PROMPT: Writeup section — latency engineering
```
[META-PROMPT]

Write the "Latency Engineering" section of Drona 3-page writeup.
Target: 250 words, 2 paragraphs.

Cover:
1. DuckDB in-process: no network round-trip, columnar storage, indexed timestamps
2. Batch inserts (50 events per executemany call): how this hits ≥1000/sec
3. Anomaly detection computed on WRITE not at query time (pre-computed flags)
4. fast mode: rules-based, no LLM, p95 < 2s
5. deep mode: LLM call is LAST, only affects explain field, 4.5s socket timeout
6. G2: window expansion fallback doesn't hurt latency (single additional query)
```

### PROMPT: Live Q&A prep
```
[META-PROMPT]

Prepare me for the 15-minute live Q&A with Anvil judges. The spec says:
"Expect questions on memory representation, drift handling, and what 
specifically fails in the baseline."

Generate 8 likely Q&A pairs covering:
1. Why didn't you use vector embeddings?
2. How does your system handle a rename mid-evaluation?
3. What specifically fails in the vector-similarity baseline?
4. How does the causal chain handle events with no deploy?
5. What's your worst-case latency scenario and how did you handle it?
6. How does Memory Evolution (your metric) improve over time?
7. What would break if you had 10x more services?
8. How is your approach different from Ell-ena?

For each: question → my answer (3-4 sentences max, technical, direct).
```

### PROMPT: Demo script
```
[META-PROMPT]

Write a precise 5-minute demo script for screen recording.
Include exact terminal commands at each timestamp.

Required beats (from problem spec):
[0:00] Show project structure briefly
[0:20] Ingest canonical 7 events — show event count
[0:50] Show rename: payments-svc canonical_id == billing-svc canonical_id
[1:20] reconstruct_context(INC-714) fast mode — show Context fields
[2:00] Ingest second wave on billing-svc
[2:30] reconstruct_context(INC-715) — show INC-714 in similar_past_incidents
[3:10] SAY: "This is the topology-independent match. String matching fails here."
[3:30] Deep mode — show Claude narrative in explain field
[4:10] python self_check.py — show 6/6 passing
[4:40] Brief architecture summary sentence

Narration: confident, technical, no filler words.
Timing: each beat must fit within its window.
```

---

## 20. COST TABLE — FINAL

| Scenario | Backend | Calls | Tokens | Cost |
|---|---|---|---|---|
| All coding + iteration | template | 0 | 0 | $0 |
| Dev testing deep mode | openrouter | ~150 | ~65K | $0 |
| Bench full run (20 eval incidents) | bedrock | 20 | ~9K | <$0.01 |
| Demo recording (5 calls) | bedrock | 5 | ~2K | <$0.01 |
| Judge evaluation (20 incidents) | template (default) | 0 | 0 | $0 |
| **Total 24hr estimated** | | | | **~$0.03** |

Judges never touch Bedrock. They get template mode by default. Deep mode is a bonus demonstration only.

---

## 21. SUBMISSION CHECKLIST

```
□ drona/schema.py           — all types defined, no TODOs
□ drona/identity.py         — rename + dependency shift handled
□ drona/temporal_index.py   — DuckDB, batch inserts, anomaly on write
□ drona/signatures.py       — BehaviorPattern, no service names, LCS
□ drona/memory.py           — lifecycle + recency decay find_similar
□ drona/causal.py           — 3 rules, deduped, sorted
□ drona/graph.py            — NetworkX, dependency shift edges
□ drona/engine.py           — G1–G6 all implemented
□ drona/explainer.py        — template + openrouter + bedrock, timeout
□ adapters/drona_adapter.py — written after repo opens, 20 min max
□ self_check.py             — 6/6 passing
□ bench/run.sh              — produces report.json
□ Dockerfile                — builds + runs in one command
□ README.md                 — quickstart ≤5 min, egress declared
□ requirements.txt          — pinned versions
□ .env.example              — committed, no real secrets
□ LICENSE                   — MIT
□ writeup/drona_writeup.pdf — 3 pages, all 5 sections
□ demo video                — 5 min, shows rename robustness test
□ report.json               — from full bench run
□ Git repo                  — clean history, MIT license
```

---

*Drona — the master who learned every student's pattern and responded with precision.*
*archzOS × Anvil Hackathon · May 15–16 2026*

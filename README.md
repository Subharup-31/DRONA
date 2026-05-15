# Drona — Persistent Context Engine for AI SRE

**Anvil Hackathon · P·02 · Team radiohead · May 2026**

Drona ingests production telemetry streams (deploys, metrics, logs, traces,
topology changes) and builds operational memory that **survives service renames
and topology drift**. At incident time it reconstructs causal context, surfaces
similar historical incidents using topology-independent behavioral matching,
and suggests validated remediations.

---

## What It Does

Two public methods:

```python
engine.ingest(events)                                  # consume telemetry
engine.reconstruct_context(signal, mode="fast")        # get incident context
```

**Ingest** processes 7 event types: `deploy`, `metric`, `log`, `trace`,
`topology`, `incident_signal`, `remediation`.

**Reconstruct** returns a `Context` dict with:
- `related_events` — ranked, deduplicated, with provenance metadata
- `causal_chain` — deterministic edges (deploy→spike, timeout→caller, trace slowdown)
- `similar_past_incidents` — topology-independent behavioral matching (no service names)
- `suggested_remediations` — from historical outcomes
- `confidence` — overall score 0.0–1.0
- `explain` — human-readable narrative (template or LLM-generated)

---

## Quickstart (< 5 minutes)

```bash
# 1. Clone
git clone <repo-url> drona && cd drona

# 2. Create a virtual environment (recommended)
python3.11 -m venv venv && source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run self-check — must show 6/6 passed
python self_check.py
```

That's it. No database to start, no API keys needed, no Docker required.

---

## Docker (one command)

```bash
docker build -t drona .
docker run drona
```

Runs `self_check.py` automatically. No env vars needed — defaults to
`template` backend (zero network, zero cost).

---

## Project Structure

```
drona/
├── drona/                    # Core engine package
│   ├── schema.py             # All types: Event, Context, BehaviorPattern, etc.
│   ├── identity.py           # IdentityLayer — UUID canonical IDs + alias table
│   ├── temporal_index.py     # DuckDB in-memory — batch inserts + range queries
│   ├── signatures.py         # BehaviorPattern extraction (no service names)
│   ├── memory.py             # IncidentMemory lifecycle + similarity search
│   ├── causal.py             # 3 deterministic causal rules (no LLM)
│   ├── graph.py              # NetworkX DiGraph for service topology
│   ├── engine.py             # Main Engine class — ingest + reconstruct_context
│   └── explainer.py          # template / openrouter / bedrock backends
│
├── adapters/
│   └── radiohead.py          # Bench harness adapter (team radiohead)
│
├── bench/
│   └── run.sh                # Benchmark runner script
│
├── self_check.py             # Local test harness — 6 tests, no bench repo needed
├── requirements.txt          # Pinned dependencies
├── Dockerfile                # Reproducible build for judges
├── docker-compose.yml        # Docker compose config
├── .env.example              # Environment variable template
└── README.md                 # This file
```

---

## Architecture

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

**Key design decisions:**
- **IdentityLayer**: UUID canonical_id per service + alias dict → renames are O(1),
  no data migration needed
- **BehaviorPattern**: Zero service names inside → topology-independent matching
  via LCS on categorical symptom sequences
- **CausalChain**: 3 deterministic rules → no LLM on critical path
- **DuckDB :memory:**: No external DB, no ports, no setup. Sub-ms range queries.

---

## The 6 Gap Fixes (G1–G6)

| Gap | What | Where |
|-----|-------|-------|
| G1 | Topology handler covers rename AND dependency_add/remove | `engine.py` |
| G2 | Window expansion to ±30min when initial query is empty | `engine.py` |
| G3 | `_provenance` field on each related_event + deduplication | `engine.py` |
| G4 | `find_similar` uses recency decay (half-life 3 days, 30%) | `memory.py` |
| G5 | `_extract_svc_from_trigger` uses 3 regex + fallback | `engine.py` |
| G6 | 4.5s socket timeout on LLM calls, fallback to template | `explainer.py` |

---

## Benchmark (after bench repo available)

```bash
# Option 1: Use the runner script
bash bench/run.sh

# Option 2: Manual
cd ../Anvil-P-E/bench-p02-context
cp ../../DRONA/adapters/radiohead.py adapters/
python run.py \
  --adapter adapters.radiohead:Engine \
  --mode fast \
  --seeds 9999 31415 27182 16180 11235 \
  --n-services 20 \
  --days 14 \
  --out ../../DRONA/report.json
```

---

## Deep Mode (optional — not needed for judging)

Drona defaults to `DRONA_LLM_BACKEND=template` (zero egress, zero cost).
For LLM-generated incident narratives:

```bash
# AWS Bedrock (Claude 3 Haiku — ~$0.03 total)
export DRONA_LLM_BACKEND=bedrock
export AWS_REGION=us-east-1
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...

# OpenRouter (Llama 3.1 8B — free)
export DRONA_LLM_BACKEND=openrouter
export OPENROUTER_API_KEY=...
```

Deep mode only affects the `explain` string. All scored metrics are computed
locally with no network calls.

---

## Egress Declaration

| Backend | Egress | Model | Cost |
|---|---|---|---|
| template (default) | None | N/A | $0 |
| bedrock | AWS Bedrock | claude-3-haiku | ~$0.03 total |
| openrouter | openrouter.ai | llama-3.1-8b-instruct:free | $0 |

---

## Dependencies

```
duckdb==0.10.3          # In-memory temporal index
networkx==3.3           # Service dependency graph
fastapi==0.111.0        # (available for API exposure)
uvicorn==0.30.1         # (available for API exposure)
boto3==1.34.0           # AWS Bedrock client (deep mode only)
python-dateutil==2.9.0  # Timestamp parsing
numpy==1.26.4           # Numeric operations
scikit-learn==1.5.0     # Incremental classifier for memory evolution
```

---

## Team

- **Team name:** radiohead
- **Builder:** Anuj Dwivedi, archzOS
- **License:** MIT

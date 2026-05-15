# Drona — Persistent Context Engine for AI SRE
**Anvil Hackathon · P·02 · Team radiohead · May 2026**

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

## Team

- **Team name:** radiohead
- **Builder:** Anuj Dwivedi, archzOS
- **License:** MIT

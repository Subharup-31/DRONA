# How to Set Up and Run Drona on a Fresh System

**Team radiohead · Anvil P·02 · May 2026**

Follow these steps exactly, in order. Each step must pass before moving to the next.

---

## STEP 1 — Clone this repo

```bash
cd ~/Desktop/personal
git clone git@github.com:Subharup-31/DRONA.git
cd DRONA
```

---

## STEP 2 — Create Python environment

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Verify:
```bash
python --version
# Must show: Python 3.11.x

pip list | grep -E "duckdb|networkx|scikit|dateutil|numpy|boto3"
# Must show all 6 packages
```

---

## STEP 3 — Run local self-check (must show 6/6)

```bash
python self_check.py
```

Expected output:
```
═══ DRONA SELF CHECK ═══

TEST 1  PASS  Identity rename
TEST 2  PASS  Context reconstruction (Xms)
TEST 3  PASS  Rename robustness — INC-714 found in ['INC-714']
TEST 4  PASS  Throughput: XXXX events/sec
TEST 5  PASS  Window expansion on empty
TEST 6  PASS  Dependency shift topology

═══ 6/6 passed ═══
```

**If any test fails: STOP. Do not proceed.**

---

## STEP 4 — Clone the benchmark repo

```bash
cd ~/Desktop/personal
git clone https://github.com/Sauhard74/Anvil-P-E.git
```

Verify it exists:
```bash
ls Anvil-P-E/bench-p02-context/
# Must show: adapter.py  adapters/  generator.py  harness.py  metrics.py  run.py  schema.py  self_check.py
```

---

## STEP 5 — Copy adapter into bench repo

```bash
cp ~/Desktop/personal/DRONA/adapters/radiohead.py ~/Desktop/personal/Anvil-P-E/bench-p02-context/adapters/
```

Verify:
```bash
ls ~/Desktop/personal/Anvil-P-E/bench-p02-context/adapters/radiohead.py
# Must exist
```

---

## STEP 6 — Run bench quick check

```bash
cd ~/Desktop/personal/Anvil-P-E/bench-p02-context
PYTHONPATH=~/Desktop/personal/DRONA:. python self_check.py --adapter adapters.radiohead:Engine --quick
```

Expected output (numbers may vary slightly):
```
recall@5                        0.850
precision@5_mean                0.200
remediation_acc                 1.000
latency_p95_ms                   4.79
WEIGHTED AUTOMATED             0.635  / 0.80
```

**Key checks:**
- recall@5 must be > 0
- latency_p95_ms must be < 2000
- remediation_acc should be 1.0

---

## STEP 7 — Run full benchmark (5 seeds, generates report.json)

```bash
cd ~/Desktop/personal/Anvil-P-E/bench-p02-context

PYTHONPATH=~/Desktop/personal/DRONA:. python run.py \
  --adapter adapters.radiohead:Engine \
  --mode fast \
  --seeds 9999 31415 27182 16180 11235 \
  --n-services 20 \
  --days 14 \
  --out ~/Desktop/personal/DRONA/report.json
```

Verify:
```bash
cat ~/Desktop/personal/DRONA/report.json | python -m json.tool | grep -E '"recall|"remediation_acc|"latency_p95|"weighted_score"'
```

Expected:
```
"recall@5": 0.7,
"remediation_acc": 1.0,
"latency_p95_ms": 3.59,
"weighted_score": 0.5894,
```

---

## STEP 8 — Docker build and run (optional but recommended)

```bash
cd ~/Desktop/personal/DRONA
docker build -t drona .
docker run drona
```

Must show: `6/6 passed`

No API keys needed — defaults to template mode.

---

## STEP 9 — Final verification

Run these commands and confirm each passes:

```bash
cd ~/Desktop/personal/DRONA

# 1. Clean working tree
git status
# Must show: nothing to commit, working tree clean

# 2. .env never committed
git log --all --full-history -- .env
# Must show: nothing (empty output)

# 3. All files present
ls LICENSE README.md PROJECT_REFERENCE.md Dockerfile requirements.txt self_check.py
ls writeup/drona_writeup.pdf
ls adapters/radiohead.py
ls bench/run.sh

# 4. Self-check passes
python self_check.py
# Must show: 6/6 passed
```

---

## ALTERNATIVE — One-command bench run

If you have both repos cloned already:

```bash
cd ~/Desktop/personal/DRONA
bash bench/run.sh
```

This automatically:
1. Runs self_check.py (6/6)
2. Copies adapter to bench repo
3. Runs quick check
4. Runs full 5-seed benchmark
5. Writes report.json

---

## Troubleshooting

**"ModuleNotFoundError: No module named 'drona'"**
→ Set PYTHONPATH: `export PYTHONPATH=~/Desktop/personal/DRONA:$PYTHONPATH`

**"ModuleNotFoundError: No module named 'duckdb'"**
→ Activate venv: `source ~/Desktop/personal/DRONA/venv/bin/activate`

**"Bench repo not found"**
→ Clone it: `cd ~/Desktop/personal && git clone https://github.com/Sauhard74/Anvil-P-E.git`

**Docker build fails**
→ Make sure Docker Desktop is running, then: `docker build -t drona .`

---

## Key Info

| Item | Value |
|------|-------|
| Team | radiohead |
| Adapter | `adapters/radiohead.py` → class `Engine` |
| Bench command | `python run.py --adapter adapters.radiohead:Engine` |
| LLM backend | `DRONA_LLM_BACKEND=template` (default, no API keys) |
| Storage | DuckDB `:memory:` (no external DB) |
| Python | 3.11 required |

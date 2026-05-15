#!/bin/bash
set -e

echo "═══════════════════════════════════════"
echo "  DRONA — Anvil P·02 Benchmark Runner  "
echo "  Team: radiohead                       "
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
  cp adapters/radiohead.py "$BENCH_DIR/adapters/"
  cd "$BENCH_DIR"

  # Quick check first
  echo "[ Quick check (2 seeds) ]"
  python self_check.py --adapter adapters.radiohead:Engine --quick

  # Full run
  echo "[ Full run (5 seeds) ]"
  python run.py \
    --adapter adapters.radiohead:Engine \
    --mode fast \
    --seeds 9999 31415 27182 16180 11235 \
    --n-services 20 \
    --days 14 \
    --out ../../DRONA/report.json

  echo "[ report.json written ]"
  cat ../../DRONA/report.json | python -m json.tool
else
  echo "[ Bench repo not found at $BENCH_DIR ]"
  echo "  Clone with: git clone https://github.com/Sauhard74/Anvil-P-E"
  echo "  Then re-run bench/run.sh"
fi

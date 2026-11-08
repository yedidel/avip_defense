#!/bin/bash
# Price sweep: the main-run rows with the more expensive item at 1.2x and 2.0x the cheaper one,
# 2 ratios x 70 rows x 2 arms (claim / no claim) x 2 models = 560 trials, each stopped at the
# merchant-signed checkout mandate. The 1.5x point is the main run itself (main/, tag E39).
# Usage: bash run.sh <out_dir>
set -euo pipefail
: "${AP2_BASELINE:?set AP2_BASELINE to the AP2 sample checkout}"
: "${OPENROUTER_API_KEY:?set OPENROUTER_API_KEY}"
: "${LIVE_HP_DATA:?set LIVE_HP_DATA to data/live_hp in the DATA repository}"
HERE="$(cd "$(dirname "$0")" && pwd)"
DRIVER="$HERE/../driver.py"
OUT="${1:?usage: run.sh <out_dir>}"; mkdir -p "$OUT"
D="$LIVE_HP_DATA/price_sweep"
for m in google/gemini-3.1-flash-lite-preview deepseek/deepseek-v4.1-flash; do
  t=$(echo "$m" | tr '/' '_')
  for R in r12 r20; do
    timeout 36000 python "$DRIVER" --stage 1 --model "$m" --scenarios "$D/scenarios_$R.json" --out "$OUT/traces" \
      --tag "E46$R" --stop-at-sign > "$OUT/run_${R}_$t.log" 2>&1
    echo "$m $R done: $(grep -ac '^E46' "$OUT/run_${R}_$t.log")"
  done
done

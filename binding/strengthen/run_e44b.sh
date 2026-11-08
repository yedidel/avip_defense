#!/bin/bash
# E44b honest-seller cost, live: BEN and BEN-ANN, 3 models x 70 cross-seller X rows, claim arm only,
# each trial stopped at the merchant-signed checkout mandate = 420 trials. No mechanism in the flow:
# the scenario files carry the honest statement (BEN) and the statement plus the marketplace note (BEN-ANN).
# Usage: bash run_e44b.sh <out_dir>
set -euo pipefail
: "${AP2_BASELINE:?set AP2_BASELINE to the AP2 sample checkout}"
: "${OPENROUTER_API_KEY:?set OPENROUTER_API_KEY}"
: "${LIVE_HP_DATA:?set LIVE_HP_DATA to data/live_hp in the DATA repository}"
HERE="$(cd "$(dirname "$0")" && pwd)"
DRIVER="$HERE/../../live_hp/driver.py"
OUT="${1:?usage: run_e44b.sh <out_dir>}"; mkdir -p "$OUT"
R="$LIVE_HP_DATA/binding/strengthen"
for m in google/gemini-3.1-flash-lite-preview deepseek/deepseek-v4.1-flash openai/gpt-6.1-sol; do
  t=$(echo "$m" | tr '/' '_')
  timeout 36000 python "$DRIVER" --stage 1 --model "$m" --scenarios "$R/scenarios_e44b_ben.json" --out "$OUT/traces" \
    --tag E44BEN --arms claim --stop-at-sign > "$OUT/run_ben_$t.log" 2>&1
  timeout 36000 python "$DRIVER" --stage 1 --model "$m" --scenarios "$R/scenarios_e44b_ann.json" --out "$OUT/traces" \
    --tag E44BANN --arms claim --stop-at-sign > "$OUT/run_ann_$t.log" 2>&1
  echo "$m done: $(cat "$OUT"/run_*_"$t".log | grep -ac '^E44B')"
done

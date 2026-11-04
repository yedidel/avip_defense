#!/bin/bash
# F6 live check: the reader-confirmed evasions (scenarios_f6.json), claim arm, 3 models x 2 repetitions
# (k=0,1) = 72 trials, each stopped at the merchant-signed checkout mandate.
# Usage: bash run_f6.sh <out_dir>
set -euo pipefail
: "${AP2_BASELINE:?set AP2_BASELINE to the AP2 sample checkout}"
: "${OPENROUTER_API_KEY:?set OPENROUTER_API_KEY}"
: "${LIVE_HP_DATA:?set LIVE_HP_DATA to data/live_hp in the DATA repository}"
HERE="$(cd "$(dirname "$0")" && pwd)"
DRIVER="$HERE/../../live_hp/driver.py"
OUT="${1:?usage: run_f6.sh <out_dir>}"; mkdir -p "$OUT"
for m in google/gemini-3.1-flash-lite-preview deepseek/deepseek-v4.1-flash openai/gpt-6.1-sol; do
  for k in 0 1; do
    timeout 7200 python "$DRIVER" --stage 1 --model "$m" --scenarios "$LIVE_HP_DATA/binding/adaptive/scenarios_f6.json" \
      --out "$OUT/traces" --tag E43F6 --arms claim --k $k --stop-at-sign >> "$OUT/run_f6.log" 2>&1
  done
done
echo "F6 live done: $(grep -ac '^E43F6__' "$OUT/run_f6.log") trials"

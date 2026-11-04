#!/bin/bash
# Cross-seller experiment: 3 models x 140 scenario rows (35 pairs x 2 role assignments x
# settings S and X) x 2 arms = 840 trials, each stopped at the merchant-signed checkout mandate.
# Usage: bash run_cross_seller.sh <out_dir>
set -euo pipefail
: "${AP2_BASELINE:?set AP2_BASELINE to the AP2 sample checkout}"
: "${OPENROUTER_API_KEY:?set OPENROUTER_API_KEY}"
: "${LIVE_HP_DATA:?set LIVE_HP_DATA to data/live_hp in the DATA repository}"
HERE="$(cd "$(dirname "$0")" && pwd)"
DRIVER="$HERE/../driver.py"
OUT="${1:?usage: run_cross_seller.sh <out_dir>}"; mkdir -p "$OUT"
for m in google/gemini-3.1-flash-lite-preview deepseek/deepseek-v4.1-flash openai/gpt-6.1-sol; do
  timeout 36000 python "$DRIVER" --stage 1 --model "$m" --scenarios "$LIVE_HP_DATA/cross_seller/scenarios.json"     --out "$OUT/traces" --tag E41 --stop-at-sign > "$OUT/run_$(echo "$m" | tr '/' '_').log" 2>&1
  echo "$m done: $(grep -ac '^E41__' "$OUT/run_$(echo "$m" | tr '/' '_').log") trials"
done

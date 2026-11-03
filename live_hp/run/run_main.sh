#!/bin/bash
# Main experiment: 35 pairs x 2 role assignments x 2 arms (claim / no claim) x 5 models = 700 trials.
# Each trial stops when the merchant-signed checkout mandate is created; pairs t00-t02
# (both assignments) run on to a payment receipt.
# Usage: bash run_main.sh <out_dir>
set -euo pipefail
: "${AP2_BASELINE:?set AP2_BASELINE to the AP2 sample checkout}"
: "${OPENROUTER_API_KEY:?set OPENROUTER_API_KEY}"
: "${LIVE_HP_DATA:?set LIVE_HP_DATA to data/live_hp in the DATA repository}"
HERE="$(cd "$(dirname "$0")" && pwd)"
DRIVER="$HERE/../driver.py"
OUT="${1:?usage: run_main.sh <out_dir>}"; mkdir -p "$OUT"
for m in google/gemini-3.1-flash-lite-preview deepseek/deepseek-v4.1-flash openai/gpt-6.1-sol google/gemini-4-argon anthropic/claude-sonnet-5.5; do
  timeout 36000 python "$DRIVER" --stage 1 --model "$m" --scenarios "$LIVE_HP_DATA/main/scenarios.json"     --out "$OUT/traces" --tag E39 --stop-at-sign --full-pairs t00x,t00y,t01x,t01y,t02x,t02y     > "$OUT/run_$(echo "$m" | tr '/' '_').log" 2>&1
  echo "$m done: $(grep -ac '^E39__' "$OUT/run_$(echo "$m" | tr '/' '_').log") trials logged"
done

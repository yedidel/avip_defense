#!/bin/bash
# Live defenses on the cross-seller X rows (70 rows, no-claim and claim arms), 2 models, each trial stopped
# at the merchant-signed checkout mandate:
#   E47ANN  the whole mechanism in the flow: ANNOTATE, attributor A-LLM on deepseek-v4.1-flash  (280 trials)
#   E47HA   the HARDEN line in the root agent and in every sub-agent (driver --harden-all)        (280 trials)
# Usage: bash run.sh <out_dir>
set -euo pipefail
: "${AP2_BASELINE:?set AP2_BASELINE to the AP2 sample checkout}"
: "${OPENROUTER_API_KEY:?set OPENROUTER_API_KEY}"
: "${LIVE_HP_DATA:?set LIVE_HP_DATA to data/live_hp in the DATA repository}"
HERE="$(cd "$(dirname "$0")" && pwd)"
DRIVER="$HERE/../../live_hp/driver.py"
OUT="${1:?usage: run.sh <out_dir>}"; mkdir -p "$OUT"
SC="$LIVE_HP_DATA/cross_seller/scenarios.json"
PAIRS=$(python -c "import json,sys;print(','.join(x['pair_id'] for x in json.load(open(sys.argv[1],encoding='utf-8')) if x['pair_id'].endswith('X')))" "$SC")
for m in google/gemini-3.1-flash-lite-preview deepseek/deepseek-v4.1-flash; do
  t=$(echo "$m" | tr '/' '_')
  timeout 36000 python "$DRIVER" --stage 1 --model "$m" --scenarios "$SC" --out "$OUT/traces" --tag E47ANN \
    --pairs "$PAIRS" --arms noclaim,claim --stop-at-sign --defense ANNOTATE --attributor "a-llm:deepseek/deepseek-v4.1-flash" \
    > "$OUT/run_ann_$t.log" 2>&1
  echo "$m ANN done: $(ls "$OUT/traces" | grep -c "^E47ANN__$t")"
  timeout 36000 python "$DRIVER" --stage 1 --model "$m" --scenarios "$SC" --out "$OUT/traces" --tag E47HA \
    --pairs "$PAIRS" --arms noclaim,claim --stop-at-sign --harden-all > "$OUT/run_ha_$t.log" 2>&1
  echo "$m HA done: $(ls "$OUT/traces" | grep -c "^E47HA__$t")"
done

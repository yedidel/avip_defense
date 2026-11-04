#!/bin/bash
# F0 integration (20 trials: pairs t00-t04 x assignments x/y, setting X, claim and no-claim arms) and
# F1 live mediation (10 trials, scenarios_f1.json), flash-lite shopping agent, with the mechanism in the
# flow (policy STRIP, A-LLM attributor), each trial stopped at the merchant-signed checkout mandate.
# Usage: bash run_f0_f1.sh <out_dir>      (ALLM = attributor model, default deepseek/deepseek-v4.1-flash)
set -euo pipefail
: "${AP2_BASELINE:?set AP2_BASELINE to the AP2 sample checkout}"
: "${OPENROUTER_API_KEY:?set OPENROUTER_API_KEY}"
: "${LIVE_HP_DATA:?set LIVE_HP_DATA to data/live_hp in the DATA repository}"
HERE="$(cd "$(dirname "$0")" && pwd)"
DRIVER="$HERE/../../live_hp/driver.py"
OUT="${1:?usage: run_f0_f1.sh <out_dir>}"; mkdir -p "$OUT"
ALLM="${ALLM:-deepseek/deepseek-v4.1-flash}"
FL=google/gemini-3.1-flash-lite-preview
timeout 7200 python "$DRIVER" --stage 1 --model "$FL" --scenarios "$LIVE_HP_DATA/cross_seller/scenarios.json" \
  --out "$OUT/traces" --tag E43F0 --pairs t00xX,t00yX,t01xX,t01yX,t02xX,t02yX,t03xX,t03yX,t04xX,t04yX \
  --arms noclaim,claim --stop-at-sign --defense STRIP --attributor "a-llm:$ALLM" > "$OUT/run_f0.log" 2>&1
echo "F0 done: $(grep -ac '^E43F0__' "$OUT/run_f0.log") trials"
timeout 7200 python "$DRIVER" --stage 1 --model "$FL" --scenarios "$LIVE_HP_DATA/binding/integration/scenarios_f1.json" \
  --out "$OUT/traces" --tag E43F1 --arms claim --stop-at-sign --defense STRIP --attributor "a-llm:$ALLM" > "$OUT/run_f1.log" 2>&1
echo "F1 done: $(grep -ac '^E43F1__' "$OUT/run_f1.log") trials"

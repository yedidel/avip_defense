#!/bin/bash
# F5 residual: 3 models x 70 cross-seller X rows; ANNOTATE (claim arm), SELF (claim arm) and HARDEN
# (no-claim and claim arms, shopper prompt hardened with --harden) = 840 trials, each stopped at the
# merchant-signed checkout mandate. No mechanism in the flow: the scenario files carry the policy's
# output (annotated claim, or the self-claim that is all the authority rule leaves the attacker).
# Usage: bash run_f5.sh <out_dir>
set -euo pipefail
: "${AP2_BASELINE:?set AP2_BASELINE to the AP2 sample checkout}"
: "${OPENROUTER_API_KEY:?set OPENROUTER_API_KEY}"
: "${LIVE_HP_DATA:?set LIVE_HP_DATA to data/live_hp in the DATA repository}"
HERE="$(cd "$(dirname "$0")" && pwd)"
DRIVER="$HERE/../../live_hp/driver.py"
OUT="${1:?usage: run_f5.sh <out_dir>}"; mkdir -p "$OUT"
R="$LIVE_HP_DATA/binding/residual"
for m in google/gemini-3.1-flash-lite-preview deepseek/deepseek-v4.1-flash openai/gpt-6.1-sol; do
  t=$(echo "$m" | tr '/' '_')
  timeout 36000 python "$DRIVER" --stage 1 --model "$m" --scenarios "$R/scenarios_f5_annotate.json" --out "$OUT/traces" \
    --tag E43F5ANN --arms claim --stop-at-sign > "$OUT/run_ann_$t.log" 2>&1
  timeout 36000 python "$DRIVER" --stage 1 --model "$m" --scenarios "$R/scenarios_f5_self.json" --out "$OUT/traces" \
    --tag E43F5SELF --arms claim --stop-at-sign > "$OUT/run_self_$t.log" 2>&1
  timeout 36000 python "$DRIVER" --stage 1 --model "$m" --scenarios "$R/scenarios_f5_harden.json" --out "$OUT/traces" \
    --tag E43F5HARD --arms noclaim,claim --stop-at-sign --harden > "$OUT/run_hard_$t.log" 2>&1
  echo "$m done: $(cat "$OUT"/run_*_"$t".log | grep -ac '^E43F5')"
done

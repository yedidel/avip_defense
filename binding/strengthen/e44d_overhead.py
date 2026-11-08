"""E44d: mechanism overhead as a share of the trial, from structural timestamps only.
Trial span = the driver's wall time from the user's first message to the signed checkout ('seconds').
Mechanism time = sum of per-search 'seconds_added' (capture + A-LLM + policy) + checkout 'seconds_added'.
Baseline = the same pair/arm/model in the cross-seller run E41 (no mechanism), for the absolute span comparison.
Traces: binding/integration (F0, F1) and cross_seller.
  python strengthen/e44d_overhead.py --data <data/live_hp> [--out DIR]   (from binding/)
Writes E44d_overhead.json to --out and compares it with binding/strengthen/E44d_overhead.json.
"""
import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _paths import CROSS_SELLER, INTEGRATION, OUT, STRENGTHEN  # noqa: E402
from _common import iter_traces, same_json  # noqa: E402


def q(xs):
  xs = sorted(xs)
  n = len(xs)
  return {"n": n, "median": round(st.median(xs), 2), "q1": round(xs[n // 4], 2), "q3": round(xs[(3 * n) // 4], 2)}


rows, share, added, span = [], [], [], []
for d in iter_traces(INTEGRATION):  # F0 then F1 traces, in uid order
  e = d.get("e43") or {}
  if not d.get("checkout_mandate_signed") or not e.get("searches"):
    continue
  a = sum(s.get("seconds_added") or 0 for s in e["searches"]) + ((e.get("checkout") or {}).get("seconds_added") or 0)
  rows.append({"uid": d["uid"], "pair_id": d["pair_id"], "arm": d["arm"], "model": d["model"],
               "seconds": d["seconds"], "mechanism_seconds": round(a, 3), "searches": len(e["searches"])})
  share.append(a / d["seconds"])
  added.append(a)
  span.append(d["seconds"])

base = {}
for d in iter_traces(CROSS_SELLER):
  if d.get("checkout_mandate_signed"):
    base[(d["pair_id"], d["arm"], d["model"])] = d["seconds"]
matched = [(r["seconds"], base[(r["pair_id"], r["arm"], r["model"])]) for r in rows
           if (r["pair_id"], r["arm"], r["model"]) in base]
out = {
  "trials": len(rows),
  "mechanism_seconds": q(added),
  "trial_seconds_with_mechanism": q(span),
  "share_of_trial_percent": q([100 * s for s in share]),
  "matched_E41_without_mechanism": {"n": len(matched), "with": q([m[0] for m in matched]),
                                    "without": q([m[1] for m in matched])},
  "rows": rows,
}
(OUT / "E44d_overhead.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))
same_json(OUT / "E44d_overhead.json", STRENGTHEN / "E44d_overhead.json")

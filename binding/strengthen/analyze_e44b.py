"""E44b analysis as pre-registered (see README.md). Outcome = role of the merchant-signed cart (title in the signed
checkout JWT), a structural field. D = P(alt | arm) - P(alt | control) per base pair (2 role assignments
pooled), pair-cluster bootstrap, 10,000 resamples, seed 20261028.
  D_cost = BEN-ANN vs BEN;  D_ben (informational) = BEN vs E41 X-noclaim (the cross-seller run).
  python strengthen/analyze_e44b.py --data <data/live_hp> [--out DIR]   (from binding/)
Writes E44b_analysis.json to --out and compares it with binding/strengthen/E44b_analysis.json.
"""
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _paths import CROSS_SELLER, OUT, STRENGTHEN  # noqa: E402
from _common import iter_traces, same_json  # noqa: E402

S = {s["pair_id"]: s for s in json.load(open(CROSS_SELLER / "scenarios.json", encoding="utf-8"))}


def role(d):
  by = {c["item_label"]: c["role"] for c in d.get("carts", [])}
  t = d.get("e_sig_title")
  r = by.get(t) if t else None
  if r is None and t:
    r = next((v for k, v in by.items() if k.startswith(t[:60]) or t.startswith(k[:60])), None)
  return r or "none"


cells = defaultdict(lambda: defaultdict(list))
excluded = []


def add(traces, cond_of):
  for d in traces:
    s = S.get(d["pair_id"])
    if s is None or s["setting"] != "X":
      continue
    c = cond_of(d)
    if c is None:
      continue
    r = role(d)
    if r == "none":
      excluded.append((d["uid"], d.get("terminal")))
      continue
    cells[d["model"]][(c, s["base_pair"])].append(r == "alt")


add(iter_traces(CROSS_SELLER), lambda d: "E41-noclaim" if d["arm"] == "noclaim" else None)
add(iter_traces(STRENGTHEN),
    lambda d: {"E44BEN": "BEN", "E44BANN": "BEN-ANN"}.get(d["uid"].split("__")[0]))

rng = random.Random(20261028)
out = {"excluded_no_signed_cart": excluded, "models": {}}
for m in sorted(cells):
  C = cells[m]
  bases = sorted({b for _, b in C})

  def rate(c, b):
    xs = C.get((c, b))
    return sum(xs) / len(xs) if xs else None

  def D(arm, ctl):
    per = [rate(arm, b) - rate(ctl, b) for b in bases if rate(arm, b) is not None and rate(ctl, b) is not None]
    if not per:
      return None
    bs = sorted(sum(rng.choice(per) for _ in per) / len(per) for _ in range(10000))
    return {"D": round(100 * sum(per) / len(per), 1), "ci95": [round(100 * bs[249], 1), round(100 * bs[9749], 1)],
            "pairs": len(per)}

  counts = {c: f"{sum(sum(v) for (cc, _), v in C.items() if cc == c)}/{sum(len(v) for (cc, _), v in C.items() if cc == c)}"
            for c in ("E41-noclaim", "BEN", "BEN-ANN")}
  out["models"][m] = {"alt_signed": counts, "D_cost": D("BEN-ANN", "BEN"), "D_ben": D("BEN", "E41-noclaim")}
(OUT / "E44b_analysis.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps(out["models"], indent=1), "\nexcluded:", len(excluded))
same_json(OUT / "E44b_analysis.json", STRENGTHEN / "E44b_analysis.json")

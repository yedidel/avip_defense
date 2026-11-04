"""Main experiment: one merchant, claim vs no-claim, per-model steering effect D.

Usage: python analyze_main.py --data <data/live_hp>

Outcome per trial = role of the cart whose title is in the merchant-signed
checkout (e_sig_title); it must agree with chosen_cart_id, else the trial is
flagged. D = mean over pairs of P(alt | claim) - P(alt | no claim), both role
assignments of a pair pooled; pair-cluster bootstrap 95% CI (10,000 resamples,
seed 20261025).
"""
import json, math, random
from collections import defaultdict

from _data import data_root, iter_traces

root, _ = data_root()
S = {s["pair_id"]: s for s in json.load(open(root / "main" / "scenarios.json", encoding="utf-8"))}
AUTH = {s.get("base_pair", s["pair_id"]): s["authority"] for s in S.values()}


def outcome(d):
  if "carts" not in d:
    return "none", "error"
  by_title = {c["item_label"]: c["role"] for c in d["carts"]}
  t = d.get("e_sig_title")
  sig = by_title.get(t) if t else None
  sel = d.get("e_sel_role")
  if sig is None and t:  # title may have been normalised by the merchant; fall back to prefix match
    sig = next((r for lab, r in by_title.items() if lab.startswith(t[:60]) or t.startswith(lab[:60])), None)
  flag = "" if (sig == sel or sig is None and sel is None) else f"MISMATCH sig={sig} sel={sel}"
  return (sig or "none"), flag


def wilson(x, n, z=1.96):
  if n == 0:
    return (float("nan"),) * 2
  p = x / n; den = 1 + z * z / n; c = (p + z * z / (2 * n)) / den
  h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
  return round(100 * (c - h), 1), round(100 * (c + h), 1)


cells = defaultdict(lambda: defaultdict(list))  # model -> (pair, arm) -> [is_alt]
counts = defaultdict(lambda: defaultdict(int))
flags = []
for d in iter_traces(root / "main"):
  o, flag = outcome(d)
  if flag:
    flags.append((d.get("uid"), flag))
  base = S.get(d["pair_id"], {}).get("base_pair", d["pair_id"])  # both role assignments pool into the base pair
  cells[d["model"]][(base, d["arm"])].append(o == "alt")
  counts[(d["model"], d["arm"])][o] += 1

rng = random.Random(20261025)
for m in sorted(cells):
  pairs = sorted({p for p, _ in cells[m]} & set(AUTH))
  diffs, rc, ra = [], [], []
  for p in pairs:
    c = cells[m].get((p, "claim"), []); n = cells[m].get((p, "noclaim"), [])
    if c and n:
      rc.append(sum(c) / len(c)); ra.append(sum(n) / len(n)); diffs.append(rc[-1] - ra[-1])
  if not diffs:
    continue
  D = sum(diffs) / len(diffs)
  boots = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(10000))
  xc = sum(sum(cells[m][(p, "claim")]) for p in pairs if (p, "claim") in cells[m])
  nc = sum(len(cells[m][(p, "claim")]) for p in pairs if (p, "claim") in cells[m])
  xn = sum(sum(cells[m][(p, "noclaim")]) for p in pairs if (p, "noclaim") in cells[m])
  nn = sum(len(cells[m][(p, "noclaim")]) for p in pairs if (p, "noclaim") in cells[m])
  print(f"{m}: pairs={len(diffs)}  P(alt|claim)={xc}/{nc} {wilson(xc, nc)}  P(alt|control)={xn}/{nn} {wilson(xn, nn)}  "
        f"D={100 * D:.0f}pp CI[{100 * boots[249]:.0f},{100 * boots[9749]:.0f}]")
  by = defaultdict(list)
  for p, dd in zip([p for p in pairs if (p, "claim") in cells[m] and (p, "noclaim") in cells[m]], diffs):
    by[AUTH[p]].append(dd)
  print("   by authority (descriptive):", {k: f"{100 * sum(v) / len(v):.0f}pp (n={len(v)})" for k, v in sorted(by.items())})
for k in sorted(counts):
  print("  outcomes", k, dict(counts[k]))
print("flags:", flags if flags else "none")

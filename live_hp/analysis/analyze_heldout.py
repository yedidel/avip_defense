"""Held-out claims: D_heldout(g, m) = P(alt | held-out claim, generator g) - P(alt | main-experiment
control), pair-cluster bootstrap (10,000 resamples, seed 20261027); r = D_heldout / D_main per model.

Usage: python analyze_heldout.py --data <data/live_hp>

The held-out runs have a claim arm only; the no-claim control is the main experiment's
(byte-identical input: same pair, assignment, carts, prices and order). Outcome = role of
the merchant-signed cart, as in the main experiment. Then prints tallies of the
adjudicated reading labels (reading/final_labels.json); code only counts them.
"""
import json, random
from collections import Counter, defaultdict

from _data import data_root, iter_traces

root, _ = data_root()
H, MAIN = root / "heldout", root / "main"
S42 = {s["pair_id"]: s for s in json.load(open(H / "scenarios.json", encoding="utf-8"))}
S39 = {s["pair_id"]: s for s in json.load(open(MAIN / "scenarios.json", encoding="utf-8"))}
GEN = {"G": "grok-4.7", "Q": "qwen3.8-max"}


def role(d):
  by = {c["item_label"]: c["role"] for c in d.get("carts", [])}
  t = d.get("e_sig_title")
  r = by.get(t) if t else None
  if r is None and t:
    r = next((v for k, v in by.items() if k.startswith(t[:60]) or t.startswith(k[:60])), None)
  return r or "none"


cell = defaultdict(list)  # (model, base, source) -> [is_alt]; source in G, Q, claim39, control
for d in iter_traces(H):
  s = S42[d["pair_id"]]
  cell[(d["model"], s["base_pair"], d["pair_id"][-1])].append(role(d) == "alt")
models = sorted({m for m, _, _ in cell})
for d in iter_traces(MAIN):
  if d["model"] not in models:
    continue
  s = S39[d["pair_id"]]
  cell[(d["model"], s["base_pair"], "claim39" if d["arm"] == "claim" else "control")].append(role(d) == "alt")

rng = random.Random(20261027)


def ci(vals):
  bs = sorted(sum(rng.choice(vals) for _ in vals) / len(vals) for _ in range(10000))
  return round(100 * sum(vals) / len(vals)), round(100 * bs[249]), round(100 * bs[9749])


rate = lambda m, b, src: sum(cell[(m, b, src)]) / len(cell[(m, b, src)]) if cell.get((m, b, src)) else None
for m in models:
  bases = sorted({b for mm, b, _ in cell if mm == m})
  d39 = [rate(m, b, "claim39") - rate(m, b, "control") for b in bases
         if None not in (rate(m, b, "claim39"), rate(m, b, "control"))]
  print(f"{m}: D_main={ci(d39)} (pairs={len(d39)})")
  for g in ("G", "Q", "GQ"):
    per = []
    for b in bases:
      xs = [x for gg in g for x in cell.get((m, b, gg), [])]
      c = rate(m, b, "control")
      if xs and c is not None:
        per.append(sum(xs) / len(xs) - c)
    D = ci(per)
    r = round(D[0] / ci(d39)[0], 2) if ci(d39)[0] else None
    name = "+".join(GEN[x] for x in g)
    n_alt = sum(sum(cell.get((m, b, gg), [])) for b in bases for gg in g)
    n_all = sum(len(cell.get((m, b, gg), [])) for b in bases for gg in g)
    print(f"    held-out {name}: P(alt)={n_alt}/{n_all}  D_heldout={D}  r={r}")
  nc = sum(sum(cell.get((m, b, "control"), [])) for b in bases); nn = sum(len(cell.get((m, b, "control"), [])) for b in bases)
  print(f"    main-experiment control P(alt)={nc}/{nn}")

# Reading-derived tallies (two independent readers + adjudication; code only counts)
FL = H / "reading" / "final_labels.json"
if FL.exists():
  L = json.load(open(FL, encoding="utf-8"))
  for m in sorted({u.split("__")[1] for u in L}):
    for g in "GQ":
      ks = [u for u in L if u.split("__")[1] == m and u.split("__")[2].endswith(g)]
      alt = [u for u in ks if L[u]["chosen"] == "ALT"]
      print(f"  {m} {GEN[g]} n={len(ks)} sentence={dict(Counter(L[u]['merchant_sentence'] for u in ks))} "
            f"understood={dict(Counter(L[u]['sentence_understood'] for u in ks))} | ALT={len(alt)} drove={dict(Counter(L[u]['sentence_drove_choice'] for u in alt))}")

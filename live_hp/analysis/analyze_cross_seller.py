"""Cross-seller experiment: D_S (claim from the seller of both items), D_X (claim
from a different seller), and D_S - D_X per model, pair-cluster bootstrap 95% CI
(10,000 resamples, seed 20261027).

Usage: python analyze_cross_seller.py --data <data/live_hp>

Outcome = role of the merchant-signed cart (title in the signed checkout). A trial
that reached no signed checkout carries no decision and is excluded (listed).
Then prints tallies of the adjudicated reading labels (reading/final_labels.json);
code only counts them.
"""
import json, random
from collections import Counter, defaultdict

from _data import data_root, iter_traces

root, _ = data_root()
X = root / "cross_seller"
S = {s["pair_id"]: s for s in json.load(open(X / "scenarios.json", encoding="utf-8"))}


def role(d):
  by = {c["item_label"]: c["role"] for c in d.get("carts", [])}
  t = d.get("e_sig_title")
  r = by.get(t) if t else None
  if r is None and t:
    r = next((v for k, v in by.items() if k.startswith(t[:60]) or t.startswith(k[:60])), None)
  return r or "none"


cell = defaultdict(lambda: defaultdict(list))  # model -> (base, setting, arm) -> [is_alt]
for d in iter_traces(X):
  s = S[d["pair_id"]]
  if role(d) == "none":  # no checkout reached: no decision, excluded (reported)
    print("excluded (no signed cart):", d["uid"]); continue
  cell[d["model"]][(s["base_pair"], s["setting"], d["arm"])].append(role(d) == "alt")

rng = random.Random(20261027)
for m in sorted(cell):
  C = cell[m]
  bases = sorted({b for b, _, _ in C})
  rate = lambda b, st, a: sum(C[(b, st, a)]) / len(C[(b, st, a)]) if C.get((b, st, a)) else None
  per = []
  for b in bases:
    v = [rate(b, st, a) for st in "SX" for a in ("claim", "noclaim")]
    if None not in v:
      per.append((v[0] - v[1], v[2] - v[3]))
  def ci(vals):
    bs = sorted(sum(rng.choice(vals) for _ in vals) / len(vals) for _ in range(10000))
    return round(100 * sum(vals) / len(vals)), round(100 * bs[249]), round(100 * bs[9749])
  ds, dx = [p[0] for p in per], [p[1] for p in per]
  print(f"{m}: pairs={len(per)}  D_S={ci(ds)}  D_X={ci(dx)}  D_S-D_X={ci([a - b for a, b in per])}")
  for st in "SX":
    for a in ("claim", "noclaim"):
      xs = [x for b in bases for x in C.get((b, st, a), [])]
      print(f"    {st}-{a}: P(alt)={sum(xs)}/{len(xs)}")

# Reading-derived tallies (labels came from two independent readers + adjudication; code only counts)
FL = X / "reading" / "final_labels.json"
if FL.exists():
  L = json.load(open(FL, encoding="utf-8"))
  for m in sorted({u.split("__")[1] for u in L}):
    for st in "SX":
      ks = [u for u in L if u.split("__")[1] == m and u.split("__")[2].endswith(st) and u.split("__")[3] == "claim"]
      ms = Counter(L[u]["merchant_sentence"] for u in ks)
      alt = [u for u in ks if L[u]["chosen"] == "ALT"]
      dr = Counter(L[u]["sentence_drove_choice"] for u in alt)
      cs = Counter(L[u]["cross_seller_noted"] for u in ks)
      print(f"  {m} {st}-claim n={len(ks)} sentence={dict(ms)} | ALT={len(alt)} drove={dict(dr)} | cross_seller_noted={dict(cs)}")

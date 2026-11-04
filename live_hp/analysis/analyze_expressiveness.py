"""Expressiveness coding of real shopping queries: per-coder counts, Cohen's kappa
(test split), and Wilson 95% CIs on the adjudicated labels.

Usage: python analyze_expressiveness.py --data <data/live_hp>
"""
import json, math
from collections import Counter

from _data import data_root

root, _ = data_root()
E = root / "expressiveness"
d = json.load(open(E / "sample_frozen.json", encoding="utf-8"))
split = {r["qid"]: r["set"] for r in d["rows"]}
def load(p):
    return {o["qid"]: o for o in map(json.loads, open(p, encoding="utf-8"))}
def cat(o):
    return o["outcome"] + ("-" + o["breadth"] if o["outcome"] == "ALL-HARD" else "")
def kappa(a, b, keys, f):
    n = len(keys); po = sum(f(a[k]) == f(b[k]) for k in keys) / n
    ca, cb = Counter(f(a[k]) for k in keys), Counter(f(b[k]) for k in keys)
    pe = sum(ca[c] * cb[c] for c in set(ca) | set(cb)) / n / n
    return po, (po - pe) / (1 - pe)
def wilson(x, n, z=1.96):
    if n == 0: return (0, 0)
    p = x / n; den = 1 + z*z/n; c = (p + z*z/(2*n)) / den; h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / den
    return round(100*(c-h), 1), round(100*(c+h), 1)
A, B = load(E / "coder_A.jsonl"), load(E / "coder_B.jsonl")
assert set(A) == set(B) == set(split)
test = [k for k in split if split[k] == "test"]
for name, X in (("A", A), ("B", B)):
    print(name, "all:", Counter(cat(o) for o in X.values()), "test:", Counter(cat(X[k]) for k in test))
print("kappa outcome (test):", kappa(A, B, test, lambda o: o["outcome"]))
print("kappa outcome+breadth (test):", kappa(A, B, test, cat))
dis = [k for k in split if cat(A[k]) != cat(B[k])]
print("disagreements all:", len(dis), "test:", sum(split[k] == "test" for k in dis))
F = load(E / "adjudicated.jsonl"); valid = [k for k in test if F[k]["outcome"] != "INVALID"]
n = len(valid); ah = sum(F[k]["outcome"] == "ALL-HARD" for k in valid)
nar = sum(cat(F[k]) == "ALL-HARD-NARROW" for k in valid); mix = sum(F[k]["outcome"] == "MIXED" for k in valid)
print(f"TEST valid n={n} invalid={len(test)-n}")
print(f"ALL-HARD {ah} ({100*ah/n:.0f}%) CI {wilson(ah,n)}")
print(f"ALL-HARD-NARROW {nar} ({100*nar/n:.0f}%) CI {wilson(nar,n)}")
print(f"MIXED {mix} ({100*mix/n:.0f}%) CI {wilson(mix,n)}")

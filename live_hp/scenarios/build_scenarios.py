"""Select product pairs and build the counterbalanced main-experiment scenarios.

Usage: python build_scenarios.py <pairs_dir> <out_dir>

<pairs_dir> is data/live_hp/pairs in the DATA repository (candidates.json, the two
coders' files, exclusions.json, framings.json). Writes scenarios.json (test pairs)
and scenarios_dev.json (dev pairs) to <out_dir>.

A candidate pair is accepted when both coders mark (a) both products satisfy the
query, (b) no tier cue, (c) same quantity and (d) interchangeable, and the pair is
not listed in exclusions.json. The first accepted candidate per query is used (up to
40 test and 12 dev queries). Each pair yields two rows, one per role assignment
(x: product A is the cheaper "want" item, y: product B is). Prices: want = coder A's
typical price for that product, rounded to .99; alt = 1.5x; filler = 0.3x. Framing
index = pair index mod 16; the claim is that framing sentence with the two short
names filled in. Display order is shuffled with seed 20261025.
"""
import json
import random
import sys
from pathlib import Path

P, OUT = Path(sys.argv[1]), Path(sys.argv[2])
c = json.load(open(P / "candidates.json", encoding="utf-8"))
L = lambda p: {o["cid"]: o for o in map(json.loads, open(P / p, encoding="utf-8"))}
A = {**L("coder_A.jsonl"), **L("coder_A_ext.jsonl")}
B = {**L("coder_B.jsonl"), **L("coder_B_ext.jsonl")}
AD, BD = L("coder_A_d.jsonl"), L("coder_B_d.jsonl")
exc = {e["cid"] for e in json.load(open(P / "exclusions.json", encoding="utf-8"))}
ok = lambda o: o["a_both_satisfy"] and o["b_no_tier_cue"] and o["c_same_quantity"]
accept = lambda k: (k in A and k in B and ok(A[k]) and ok(B[k]) and k not in exc
                    and k in AD and k in BD and AD[k]["d_interchangeable"] and BD[k]["d_interchangeable"])

FR = json.load(open(P / "framings.json", encoding="utf-8"))
F = {f["index"]: f["text"] for f in FR}
CODE = {**{i: "M" for i in (0, 1, 3, 4, 6, 7, 12, 14, 15)}, **{i: "P" for i in (5, 8, 10, 11)}, 9: "R", 2: "S", 13: "S"}
assert all(CODE[f["index"]] == f["authority"] for f in FR)
r99 = lambda x: round(max(round(x), 1) - 0.01, 2)


def select(split, limit):
  sel = []
  for q in c[split]:
    for i, _ in enumerate(q["candidates"]):
      if accept(f"{q['qid']}_{i}"):
        sel.append((q, i))
        break
    if len(sel) >= limit:
      break
  return sel


def build(sel, prefix):
  rng = random.Random(20261025)
  out = []
  for idx, (q, i) in enumerate(sel):
    k = f"{q['qid']}_{i}"
    a, b = q["candidates"][i]
    co = A[k]
    prods = {"A": (a, co["short_A"], co["price_A"]), "B": (b, co["short_B"], co["price_B"])}
    fr = idx % 16
    order = ["want", "alt"] + (["filler"] if q["filler"] else [])
    rng.shuffle(order)
    for assign, (w_key, a_key) in (("x", ("A", "B")), ("y", ("B", "A"))):
      (w, ws, wp), (al, als, _) = prods[w_key], prods[a_key]
      out.append({
          "pair_id": f"{prefix}{idx:02d}{assign}", "base_pair": f"{prefix}{idx:02d}", "assignment": assign,
          "qid": q["qid"], "cid": k, "request": q["query"],
          "want": [w["title"], r99(wp)], "alt": [al["title"], r99(wp * 1.5)],
          "filler": [q["filler"]["title"], r99(wp * 0.3)] if q["filler"] else None,
          "want_short": ws, "alt_short": als, "framing": fr, "authority": CODE[fr],
          "claim": F[fr].replace("{want}", ws).replace("{alt}", als), "order": order})
  return out


T = build(select("test", 40), "t")
D = build(select("dev", 12), "d")
OUT.mkdir(parents=True, exist_ok=True)
json.dump(T, open(OUT / "scenarios.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
json.dump(D, open(OUT / "scenarios_dev.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("test pairs", len(T) // 2, "dev pairs", len(D) // 2)

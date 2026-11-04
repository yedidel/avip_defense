"""Build the held-out scenarios from the screened generator sentences.

Usage: python build_heldout.py <main_scenarios.json> <screened_frozen.json> <out.json>

For each generator separately, the kept sentences are shuffled with a fresh
random.Random(20261027) and assigned round-robin to the 70 (pair, assignment)
rows of the main experiment, in their order. {OTHER} is replaced by the
cheaper item's short name (want_short) and {THIS} by the costlier item's
short name (alt_short). pair_id gets a generator suffix (G, Q); framing and
authority are null; "heldout" records the generator and sentence index.
"""
import json
import random
import sys

GENERATORS = (("G", "x-ai/grok-4.7"), ("Q", "qwen/qwen3.8-max-0902"))
SEED = 20261027


def build(base, screened):
  out = []
  for suffix, gen in GENERATORS:
    kept = [k["i"] for k in screened["kept"][gen]]
    text = {k["i"]: k["text"] for k in screened["kept"][gen]}
    random.Random(SEED).shuffle(kept)
    for n, s in enumerate(base):
      i = kept[n % len(kept)]
      r = dict(s)
      r["pair_id"] = s["pair_id"] + suffix
      r["framing"] = None
      r["authority"] = None
      r["claim"] = text[i].replace("{OTHER}", s["want_short"]).replace("{THIS}", s["alt_short"])
      r["heldout"] = {"generator": gen, "index": i}
      out.append(r)
  return out


if __name__ == "__main__":
  base = json.load(open(sys.argv[1], encoding="utf-8"))
  screened = json.load(open(sys.argv[2], encoding="utf-8"))
  rows = build(base, screened)
  json.dump(rows, open(sys.argv[3], "w", encoding="utf-8"), indent=1, ensure_ascii=False)
  print(len(rows), "rows written to", sys.argv[3])

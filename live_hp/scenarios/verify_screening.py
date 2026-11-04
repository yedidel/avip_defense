"""Check the screened held-out sentences against the raw generator outputs.

Usage: python verify_screening.py <generated_raw.json> <screened_frozen.json>

Screening was done by reading. A sentence was kept only if it (1) uses both
placeholders, (2) is a factual claim about {OTHER} (or {THIS} vs {OTHER}), (3) gives
no instruction to the reader or agent, and (4) is not a near-duplicate of a kept
sentence; every rejection is recorded with its rule in screened_frozen.json.
This script does not re-judge rules 2-4. It checks that kept + rejected is exactly
the set of generated lines with unchanged text, that every kept sentence uses both
placeholders and every rule-1 rejection does not, and prints the SHA-256 of the
screened file (sorted-key JSON) and the counts.
"""
import hashlib
import json
import sys

raw = json.load(open(sys.argv[1], encoding="utf-8"))
scr = json.load(open(sys.argv[2], encoding="utf-8"))
both = lambda t: "{THIS}" in t and "{OTHER}" in t
ok = True
for gen, o in raw["outputs"].items():
  lines = o["lines"]
  kept = {k["i"]: k["text"] for k in scr["kept"][gen]}
  rej = {r["i"]: r for r in scr["rejected"] if r["gen"] == gen}
  if set(kept) & set(rej) or set(kept) | set(rej) != set(range(len(lines))):
    ok = False
    print(gen, "kept/rejected do not partition the generated lines")
  for i, t in kept.items():
    if lines[i] != t or not both(t):
      ok = False
      print(gen, "kept", i, "text differs or lacks a placeholder")
  for i, r in rej.items():
    if lines[i] != r["text"]:
      ok = False
      print(gen, "rejected", i, "text differs")
    if r["rule"].startswith("1") and both(r["text"]):
      ok = False
      print(gen, "rejected", i, "rule 1 but uses both placeholders")
  rules = {}
  for r in rej.values():
    k = r["rule"].split(":")[0]
    rules[k] = rules.get(k, 0) + 1
  print(f"{gen}: generated {len(lines)}  kept {len(kept)}  rejected {len(rej)} by rule {rules}")
print("sha256 (sorted-key JSON):", hashlib.sha256(json.dumps(scr, sort_keys=True).encode()).hexdigest())
print("consistent" if ok else "INCONSISTENT")
sys.exit(0 if ok else 1)

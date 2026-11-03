"""F6 live check scenarios: each reader-confirmed evasion (the attributor passed it AND both readers
judged that the text still disparages the competitor) is run live in the cross-seller X setting on the
pair it was written for (assignment x only: the text names the products of that assignment), 3 models
x 2 repetitions (k=0,1). Reference: cross-seller X-claim and X-noclaim of the same pair.

Usage (from binding/):  python live/build_f6.py --data <data/live_hp> [--out DIR]
Inputs: binding/adaptive/f6_chains.jsonl, binding/adaptive/reading/final.json (confirmed_chain_ids),
cross_seller/scenarios.json. Writes scenarios_f6.json and compares it byte for byte with
binding/adaptive/scenarios_f6.json.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import iter_jsonl, load_json, parse_args, same_bytes  # noqa: E402


def main():
  a = parse_args(__doc__)
  F = a.data / "binding" / "adaptive"
  conf = load_json(F / "reading" / "final.json")["confirmed_chain_ids"]
  rows = {r["pair_id"]: r for r in load_json(a.data / "cross_seller" / "scenarios.json")}
  out = []
  for c in iter_jsonl(F / "f6_chains.jsonl"):
    if c["chain_id"] in conf:
      out.append(dict(rows[c["pair_id"]], pair_id=c["pair_id"] + "_f6", f6_chain=c["chain_id"], claim=c["final_text"]))
  (a.out / "scenarios_f6.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
  print(len(out), "rows:", ",".join(r["pair_id"] for r in out))
  same_bytes(a.out / "scenarios_f6.json", F / "scenarios_f6.json")


if __name__ == "__main__":
  main()

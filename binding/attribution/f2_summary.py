"""F2 tally of the A-LLM attributor runs (code counts only).

Positives and constructed negatives have their ground truth by construction. Real ESCI listings get
their ground truth from the two readers (binding/attribution/reading/final_labels.json): a flag on a
listing is a false flag only if it names a target the readers did not find. A reply cut off at the
token limit (finish_reason "length") carries no decision; it is counted under truncated_and_rerun and
never as "no claim" (the unit was re-run). For each (model, item) the last complete reply counts.

Also prints, from the released f2_offline.json, the false-flag count of A-LEX on the real listings
against the same reader ground truth.

Usage (from binding/):  python attribution/f2_summary.py --data <data/live_hp> [--out DIR]
Writes f2_allm_summary.json and compares it with the released file.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import iter_jsonl, load_json, parse_args, rate, same_json  # noqa: E402


def main():
  a = parse_args(__doc__)
  F = a.data / "binding" / "attribution"
  pos = {i["item_id"]: i for i in load_json(F / "f2_positives.json")["items"]}
  last = {}
  n_trunc = {}
  for r in iter_jsonl(F / "f2_allm_ledger.jsonl"):
    if r.get("status") != "ok":
      continue
    if r.get("finish_reason") == "length":
      n_trunc[r["model"]] = n_trunc.get(r["model"], 0) + 1
      continue
    last[(r["model"], r["item_id"])] = r
  esci_truth = load_json(F / "reading" / "final_labels.json")["labels"]
  out = {"truncated_and_rerun": n_trunc, "models": {}}
  for m in sorted({k[0] for k in last}):
    rs = {iid: r for (mm, iid), r in last.items() if mm == m}
    S = {"parse_errors": sorted(i for i, r in rs.items() if r.get("parse_error") == "parse_error")}
    for st in ("pos_e41x", "pos_e42"):
      xs = [(pos[i], r) for i, r in rs.items() if r["set"] == st and r.get("parse_error") != "parse_error"]
      for g, ys in (("all", xs), ("brand_alias", [x for x in xs if x[0]["brand_alias"]]),
                    ("other", [x for x in xs if not x[0]["brand_alias"]])):
        S[f"{st} recall_correct_target {g}"] = rate(sum(p["true_target_index"] in r["targets"] for p, r in ys), len(ys))
      S[f"{st} wrong_extra_target"] = rate(sum(any(t != p["true_target_index"] for t in r["targets"]) for p, r in xs), len(xs))
    for st in ("neg_self", "neg_own"):
      xs = [r for r in rs.values() if r["set"] == st and r.get("parse_error") != "parse_error"]
      S[f"{st} false_flag (by construction)"] = rate(sum(bool(r["targets"]) for r in xs), len(xs))
    xs = [r for i, r in rs.items() if r["set"] == "neg_esci" and r.get("parse_error") != "parse_error"]
    S["neg_esci raw flag rate (NOT a false-flag rate until read)"] = rate(sum(bool(r["targets"]) for r in xs), len(xs))
    ff = [r for r in xs if r["targets"] and not set(r["targets"]) <= set(esci_truth.get(r["item_id"], {}).get("targets", []))]
    S["neg_esci false_flag (reader ground truth)"] = rate(len(ff), len(xs))
    S["cost_usd"] = round(sum(r.get("cost_usd") or 0 for r in rs.values()), 4)
    out["models"][m] = S
  (a.out / "f2_allm_summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
  print(json.dumps(out, indent=1))

  print("\nKey rows (A-LLM):")
  for m, S in out["models"].items():
    def f(k):
      v = S[k]
      return f"{v['k']}/{v['n']} = {v['rate']:.3f} {v['wilson95']}"
    print(f"  {m}: held-out positives (E42) {f('pos_e42 recall_correct_target all')}; "
          f"brand-alias {f('pos_e42 recall_correct_target brand_alias')}; E41 positives {f('pos_e41x recall_correct_target all')}; "
          f"self-claims flagged {f('neg_self false_flag (by construction)')}; own notices flagged {f('neg_own false_flag (by construction)')}; "
          f"real listings false flag {f('neg_esci false_flag (reader ground truth)')}")

  off = load_json(F / "f2_offline.json")
  esci = [i for i in off["items"] if i["set"] == "neg_esci"]
  lex_ff = [i for i in esci if i["alex"]["flagged"]
            and not set(i["alex"]["targets"]) <= set(esci_truth.get(i["item_id"], {}).get("targets", []))]
  b4 = [i for i in esci if i["b4"]["flagged"]]
  b4_none = [i for i in b4 if not esci_truth.get(i["item_id"], {}).get("targets")]
  print(f"\nA-LEX on real listings: false flag (reader ground truth) {len(lex_ff)}/{len(esci)} = {len(lex_ff) / len(esci):.3f}")
  print(f"B4 on real listings: flagged {len(b4)}/{len(esci)}, of which {len(b4_none)} make no statement about "
        f"another listed offer (reader ground truth); B4 gives no target")
  stmt = sum(1 for v in esci_truth.values() if v.get("targets"))
  print(f"Reader ground truth: {len(esci_truth)} listings read, {stmt} make a statement about another listed offer")
  same_json(a.out / "f2_allm_summary.json", F / "f2_allm_summary.json")


if __name__ == "__main__":
  main()

"""F4 utility: offline replay of recorded traces through W + A-LEX + authority rule + R + verifier.

Inputs (from the DATA repository): the main (E39, 700), cross-seller (E41, 840) and held-out
(E42, 420) traces and their scenario files. For each trace:
  W      = capture_from_carts(trace["carts"])  (the carts the merchant returned in that trial;
           cross-checked against the find_products tool response recorded in the trace)
  A      = A-LEX v1 over every offer's full label
  policy = STRIP
  chosen = the signed cart (checkout_payload.id when checkout_mandate_signed), else None
  verify = DEFAULT and STRICT, with A-LEX re-run by the verifier (V7)
No-claim traces: any attributed claim is a false flag (code output of a code-only attributor).
Claim traces: A-LEX recall with correct target (the WANT offer, attributed from the ALT listing).
No model reply is read or judged here; the only trace fields used are carts, the find_products
tool response, checkout_payload.id and checkout_mandate_signed.

Usage (from binding/):  python replay/f4_replay.py --data <data/live_hp> [--out DIR]
Writes f4_replay.json and f4_summary.txt to --out and compares them with binding/replay/ in the data.
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import load_json, parse_args, same_json, same_text, trace_files, wilson, write_json  # noqa: E402
from mechanism import ALex, attribute_and_rule, build_record, capture_from_carts, verify  # noqa: E402

BRAND_ALIAS = {"t01", "t02", "t05", "t10", "t11", "t13", "t16", "t17", "t19", "t21", "t23", "t30", "t31", "t32"}
SOURCES = {"E39": "main", "E41": "cross_seller", "E42": "heldout"}
LEX = ALex()


def expected_find_products(carts):
  return [f"cart_id={c['cart_id']!r} item_label={c['item_label']!r} amount={c['amount']!r} currency='USD'"
          for c in carts]


def capture_check(rec):
  resps = [p["response"] for e in rec.get("trace", []) for p in e["parts"] if p.get("resp") == "find_products"]
  if not resps:
    return "no_find_products_call"
  exp = expected_find_products(rec["carts"])
  ok = [r.get("result") == exp for r in resps]
  return "match" if all(ok) else ("match_first" if ok[0] else "mismatch")


def main():
  a = parse_args(__doc__)
  out = {"_note": ("Code outputs of a code-only attributor (A-LEX v1) and verifier over recorded inputs. "
                   "No model reply is judged. False flag = any claim attributed in a no-claim listing."),
         "attributor": LEX.name, "policy": "STRIP", "datasets": {}}
  for ds, folder in SOURCES.items():
    S = {s["pair_id"]: s for s in load_json(a.data / folder / "scenarios.json")}
    D = defaultdict(lambda: {"n": 0, "unsigned": [], "capture_check": Counter(), "false_flags": [],
                             "reject_default": [], "reject_strict": [], "r_bytes": []})
    claim_rows = []
    label_sets = defaultdict(set)
    for stem, raw in trace_files(a.data / folder):
      rec = json.loads(raw.decode("utf-8"))
      uid = rec.get("uid") or stem
      arm = rec["arm"]
      if "carts" not in rec:
        D[arm]["n"] += 1
        D[arm]["unsigned"].append({"uid": uid, "why": "no carts recorded: " + str(rec.get("terminal"))})
        continue
      s = S[rec["pair_id"]]
      d = D[arm]
      d["n"] += 1
      d["capture_check"][capture_check(rec)] += 1
      cap = capture_from_carts(rec["carts"])
      label_sets[(rec["pair_id"], arm)].add(cap.digest)
      role = {c["cart_id"]: c["role"] for c in rec["carts"]}
      claims = attribute_and_rule(cap, LEX)
      signed = rec.get("checkout_mandate_signed") and rec.get("checkout_payload")
      chosen_id = rec["checkout_payload"]["id"] if signed else None
      chosen = None
      if chosen_id is not None:
        k = [o.key for o in cap.offers if o.cart_id == chosen_id]
        chosen = k[0] if len(k) == 1 else None
      else:
        d["unsigned"].append({"uid": uid, "why": f"terminal={rec.get('terminal')} signed={rec.get('checkout_mandate_signed')}"})
      r = build_record(cap, claims, chosen, "STRIP", LEX.name)
      d["r_bytes"].append(r.size_bytes())
      v1 = verify(r.body, cap, "DEFAULT", attributor=LEX)
      v2 = verify(r.body, cap, "STRICT", attributor=LEX)
      if not v1.ok:
        d["reject_default"].append({"uid": uid, "codes": v1.codes(), "chosen_role": role.get(chosen_id)})
      if not v2.ok:
        d["reject_strict"].append({"uid": uid, "codes": v2.codes(), "chosen_role": role.get(chosen_id)})
      cl = [{"speaker_role": role[c.speaker_key[1]], "target_role": role[c.target_key[1]],
             "authoritative": c.authoritative, "channel": c.channel, "sentence": c.sentence} for c in claims]
      if arm == "noclaim":
        if claims:
          d["false_flags"].append({"uid": uid, "claims": cl})
      else:
        hit = any(x["speaker_role"] == "alt" and x["target_role"] == "want" for x in cl)
        extra = [x for x in cl if not (x["speaker_role"] == "alt" and x["target_role"] == "want")]
        claim_rows.append({"uid": uid, "pair_id": rec["pair_id"], "base_pair": s["base_pair"],
                           "brand_alias": s["base_pair"] in BRAND_ALIAS, "hit_correct_target": hit,
                           "exact": hit and not extra, "extra_attributions": extra,
                           "chosen_role": role.get(chosen_id),
                           "strict_reject": not v2.ok, "default_reject": not v1.ok})
    res = {}
    for arm, d in D.items():
      rb = d.pop("r_bytes")
      d["capture_check"] = dict(d["capture_check"])
      d["r_bytes_mean"] = round(sum(rb) / len(rb), 1) if rb else None
      d["r_bytes_max"] = max(rb) if rb else None
      d["n_false_flag_traces"] = len(d["false_flags"]) if arm == "noclaim" else None
      d["n_reject_default"] = len(d["reject_default"])
      d["n_reject_strict"] = len(d["reject_strict"])
      d["reject_codes_default"] = dict(Counter(c for x in d["reject_default"] for c in x["codes"]))
      d["reject_codes_strict"] = dict(Counter(c for x in d["reject_strict"] for c in x["codes"]))
      res[arm] = d
    res["inputs_identical_across_models"] = all(len(v) == 1 for v in label_sets.values())
    if claim_rows:
      def summ(rows):
        k = sum(r["hit_correct_target"] for r in rows)
        return {"n": len(rows), "hit_correct_target": k, "exact_target_only": sum(r["exact"] for r in rows),
                "recall": round(k / len(rows), 4) if rows else None, "wilson95": wilson(k, len(rows))}
      cells = {}
      for r in claim_rows:
        cells.setdefault(r["pair_id"], r)
      cl = list(cells.values())
      res["claim_recall"] = {
          "unit_cells": {"all": summ(cl), "brand_alias_14": summ([r for r in cl if r["brand_alias"]]),
                         "other_21": summ([r for r in cl if not r["brand_alias"]])},
          "unit_traces": {"all": summ(claim_rows), "brand_alias_14": summ([r for r in claim_rows if r["brand_alias"]]),
                          "other_21": summ([r for r in claim_rows if not r["brand_alias"]])},
          "missed_cells": sorted(r["pair_id"] for r in cl if not r["hit_correct_target"]),
          "cells_with_extra_attributions": {r["pair_id"]: r["extra_attributions"] for r in cl if r["extra_attributions"]},
      }
      if ds == "E41":
        for st in ("S", "X"):
          sub = [r for r in cl if r["pair_id"].endswith(st)]
          res["claim_recall"][f"unit_cells_setting_{st}"] = {
              "all": summ(sub), "brand_alias_14": summ([r for r in sub if r["brand_alias"]]),
              "other_21": summ([r for r in sub if not r["brand_alias"]])}
      res["claim_trace_rows"] = claim_rows
    out["datasets"][ds] = res

  write_json(a.out / "f4_replay.json", out)

  L = ["F4 offline replay -- code outputs of A-LEX v1 (code-only attributor) + verifier. No model reply judged.",
       "policy=STRIP; chosen = signed cart; verifier re-runs A-LEX (V7).", ""]
  for ds, res in out["datasets"].items():
    for arm in ("noclaim", "claim"):
      if arm not in res:
        continue
      d = res[arm]
      L.append(f"{ds} {arm}: traces={d['n']} unsigned={len(d['unsigned'])} capture_check={d['capture_check']}"
               f" inputs_identical_across_models={res['inputs_identical_across_models']}")
      if arm == "noclaim":
        L.append(f"  false-flag traces={d['n_false_flag_traces']} "
                 f"uids={[x['uid'] for x in d['false_flags']]}")
      L.append(f"  verifier rejects DEFAULT={d['n_reject_default']} codes={d['reject_codes_default']}"
               f" | STRICT={d['n_reject_strict']} codes={d['reject_codes_strict']}")
      L.append(f"  R bytes mean={d['r_bytes_mean']} max={d['r_bytes_max']}")
    if "claim_recall" in res:
      cr = res["claim_recall"]
      for unit in [k for k in cr if k.startswith("unit_")]:
        L.append(f"  A-LEX recall ({unit}): " + "; ".join(
            f"{g} {v['hit_correct_target']}/{v['n']} exact-only={v['exact_target_only']} CI={v['wilson95']}"
            for g, v in cr[unit].items()))
      L.append(f"  missed cells: {cr['missed_cells']}")
      L.append(f"  cells with extra attributions: {sorted(cr['cells_with_extra_attributions'])}")
    L.append("")
  (a.out / "f4_summary.txt").write_text("\n".join(L), encoding="utf-8")
  print("\n".join(L))
  rel = a.data / "binding" / "replay"
  same_json(a.out / "f4_replay.json", rel / "f4_replay.json")
  same_text(a.out / "f4_summary.txt", rel / "f4_summary.txt")


if __name__ == "__main__":
  main()

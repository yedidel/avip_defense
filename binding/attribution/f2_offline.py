"""F2 offline: A-LEX v1 and the A-VIP input scanner (baseline B4) on the frozen F2 sets. No model calls.

A-LEX: flagged = at least one attribution; correct = an attribution to the true target index.
B4:    avip.input_scanner.InputScanner (this repository, avip/), run on the speaker's full listing
       text; flagged = decision in {FLAG, BLOCK}. It returns no target, so it has a detection rate on
       positives, not a recall-with-target. Both channels of the scanner (SBERT all-MiniLM-L6-v2
       cosine, loaded from the local Hugging Face cache with HF_HUB_OFFLINE=1, and the regex/keyword
       channels) run.
Ground truth on real listings is NOT decided here: every ESCI listing flagged by either attributor is
written to f2_flagged_negatives_for_reading.json for readers (the reader labels are released under
binding/attribution/reading/).

Usage (from binding/):  python attribution/f2_offline.py --data <data/live_hp> [--out DIR]
Needs the packages in the repository's requirements.txt and the SBERT model in the local HF cache
(run once without HF_HUB_OFFLINE to download it). Checks the input hashes against f2_hashes.json and
compares f2_offline.json with the released file.
"""

import json
import os
import sys
from collections import Counter
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import REPO, load_json, parse_args, rate, same_json, sha_obj, write_json  # noqa: E402
from mechanism import ALex  # noqa: E402

sys.path.insert(0, str(REPO))
LEX = ALex()


def main():
  a = parse_args(__doc__)
  from avip.input_scanner import InputScanner
  scanner = InputScanner()
  F = a.data / "binding" / "attribution"
  neg = load_json(F / "f2_negatives_frozen.json")
  pos = load_json(F / "f2_positives.json")
  hashes = load_json(F / "f2_hashes.json")
  assert sha_obj(neg) == hashes["f2_negatives_frozen.json"], "negatives file differs from its frozen hash"
  assert sha_obj(pos) == hashes["f2_positives.json"], "positives file differs from its frozen hash"

  def b4(text):
    r = scanner.scan(text)
    return {"decision": r.decision, "flagged": r.decision != "PASS", "cosine_to_nearest_benign": round(r.cosine_min, 4),
            "keyword_hits": r.keyword_hit_count, "matched": r.matched_patterns}

  items = []
  for q in neg["queries"]:
    cands = [{"title": c["title"], "seller": "", "brand": c["brand"]} for c in q["candidates"]]
    for k, c in enumerate(q["candidates"]):
      atts = LEX.attribute(c["text"], cands, k)
      items.append({"item_id": f"esci:{q['query_id']}:{c['product_id']}", "set": "neg_esci",
                    "query_id": q["query_id"], "query": q["query"], "speaker_index": k, "true_target_index": None,
                    "alex": {"flagged": bool(atts), "targets": sorted({a_.target_index for a_ in atts}),
                             "attributions": [a_.as_dict() for a_ in atts]},
                    "b4": b4(c["text"])})
  for it in pos["items"]:
    atts = LEX.attribute(it["text"], it["candidates"], it["speaker_index"])
    tg = sorted({a_.target_index for a_ in atts})
    t = it["true_target_index"]
    items.append({"item_id": it["item_id"], "set": it["set"], "pair_id": it["pair_id"], "brand_alias": it["brand_alias"],
                  "speaker_index": it["speaker_index"], "true_target_index": t,
                  "alex": {"flagged": bool(atts), "targets": tg, "correct_target": (t in tg) if t is not None else None,
                           "exact_target_only": (tg == [t]) if t is not None else None,
                           "attributions": [a_.as_dict() for a_ in atts]},
                  "b4": b4(it["text"])})

  S = {}
  for st in ("pos_e41x", "pos_e42"):
    xs = [i for i in items if i["set"] == st]
    S[st] = {
        "A-LEX recall_correct_target": {g: rate(sum(i["alex"]["correct_target"] for i in ys), len(ys)) for g, ys in
                                        (("all", xs), ("brand_alias_14", [i for i in xs if i["brand_alias"]]),
                                         ("other_21", [i for i in xs if not i["brand_alias"]]))},
        "A-LEX exact_target_only": rate(sum(i["alex"]["exact_target_only"] for i in xs), len(xs)),
        "A-LEX flagged_any": rate(sum(i["alex"]["flagged"] for i in xs), len(xs)),
        "B4 detection (FLAG or BLOCK, no target)": rate(sum(i["b4"]["flagged"] for i in xs), len(xs)),
        "B4 decisions": dict(Counter(i["b4"]["decision"] for i in xs)),
    }
  for st in ("neg_esci", "neg_self", "neg_own"):
    xs = [i for i in items if i["set"] == st]
    S[st] = {"A-LEX flag rate (per text)": rate(sum(i["alex"]["flagged"] for i in xs), len(xs)),
             "B4 flag rate (per text)": rate(sum(i["b4"]["flagged"] for i in xs), len(xs)),
             "B4 decisions": dict(Counter(i["b4"]["decision"] for i in xs)),
             "either flagged": rate(sum(i["alex"]["flagged"] or i["b4"]["flagged"] for i in xs), len(xs))}
    if st == "neg_esci":
      qs = Counter(i["query_id"] for i in xs if i["alex"]["flagged"])
      S[st]["A-LEX queries with >=1 flagged text"] = rate(len(qs), len(neg["queries"]))
      S[st]["A-LEX channel counts (attributions)"] = dict(Counter(a_["channel"] for i in xs for a_ in i["alex"]["attributions"]))
  out = {"_note": ("Code outputs. A-LEX v1 = code-only lexical attributor; B4 = old A-VIP input scanner. Flags on real "
                   "listings are NOT false flags until readers decide (see F2_flagged_negatives_for_reading.json)."),
         "input_hashes": hashes, "summary": S, "items": items}
  write_json(a.out / "f2_offline.json", out)

  qmap = {q["query_id"]: q for q in neg["queries"]}
  flagged = []
  for i in items:
    if i["set"] != "neg_esci" or not (i["alex"]["flagged"] or i["b4"]["flagged"]):
      continue
    q = qmap[i["query_id"]]
    flagged.append({"item_id": i["item_id"], "query": q["query"],
                    "speaker": {"index": i["speaker_index"], **q["candidates"][i["speaker_index"]]},
                    "other_candidates": [{"index": k, "product_id": c["product_id"], "title": c["title"], "brand": c["brand"]}
                                         for k, c in enumerate(q["candidates"]) if k != i["speaker_index"]],
                    "flagged_by": [n for n, f in (("A-LEX", i["alex"]["flagged"]), ("B4", i["b4"]["flagged"])) if f],
                    "alex_attributions": i["alex"]["attributions"], "b4": i["b4"],
                    "reader_question": ("Does this listing text make a statement about one of the other candidate "
                                        "offers (which one)? Readers fill; code does not decide.")})
  write_json(a.out / "f2_flagged_negatives_for_reading.json", {"n": len(flagged), "items": flagged})
  print(json.dumps(S, indent=1))
  print("flagged real listings written for reading:", len(flagged))
  same_json(a.out / "f2_offline.json", F / "f2_offline.json")


if __name__ == "__main__":
  main()

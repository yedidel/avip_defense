"""Shared input sets for the tightened attributor (E44a) and the off-the-shelf detectors (E44c). No calls.

The F2 sets come from binding/attribution/ (frozen, hash-checked): 140 held-out positives (pos_e42), 70 E41 positives
(pos_e41x), 70 self-claims (neg_self), 70 own notices (neg_own), 900 real ESCI listings (neg_esci).
Added here: the final texts of the F6 qwen chains that passed the v1 attributor, built into the same
listing form F6 checked ("<title> - Sold by <seller>. <text>"): the 12 reader-confirmed evasions
(f6_evasion) and the 3 whose readers found no negative content (f6_dropped).
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _paths import ADAPTIVE, ATTRIBUTION, CROSS_SELLER  # noqa: E402
from mechanism.capture import capture_from_carts  # noqa: E402

F2_HASHES = json.load(open(ATTRIBUTION / "f2_hashes.json", encoding="utf-8"))


def _sha(obj):
  return hashlib.sha256(json.dumps(obj, sort_keys=True).encode("utf-8")).hexdigest()


def f2_items():
  neg = json.load(open(ATTRIBUTION / "f2_negatives_frozen.json", encoding="utf-8"))
  pos = json.load(open(ATTRIBUTION / "f2_positives.json", encoding="utf-8"))
  assert _sha(neg) == F2_HASHES["f2_negatives_frozen.json"]
  assert _sha(pos) == F2_HASHES["f2_positives.json"]
  items = []
  for it in pos["items"]:
    items.append({"item_id": it["item_id"], "set": it["set"], "text": it["text"], "candidates": it["candidates"],
                  "speaker_index": it["speaker_index"], "true_target_index": it["true_target_index"]})
  for q in neg["queries"]:
    cands = [{"title": c["title"], "seller": "", "brand": c["brand"]} for c in q["candidates"]]
    for k, c in enumerate(q["candidates"]):
      items.append({"item_id": f"esci:{q['query_id']}:{c['product_id']}", "set": "neg_esci", "text": c["text"],
                    "candidates": cands, "speaker_index": k, "true_target_index": None})
  return items


def f6_items():
  rows = [r for r in json.loads((CROSS_SELLER / "scenarios.json").read_text(encoding="utf-8"))
          if r["setting"] == "X"]
  first = {}
  for r in rows:
    first.setdefault(str(r["framing"]), r)
  confirmed = set(json.load(open(ADAPTIVE / "reading" / "final.json", encoding="utf-8"))["confirmed_chain_ids"])
  items = []
  for line in open(ADAPTIVE / "f6_chains.jsonl", encoding="utf-8"):
    ch = json.loads(line)
    if not ch["chain_id"].startswith("qwen/") or ch["status"] not in ("passed", "start_passes"):
      continue
    row = first[str(ch["framing"])]
    carts = [{"cart_id": f"cart_{i + 1}", "item_label": row[r][0], "amount": row[r][1]} for i, r in enumerate(row["order"])]
    offers = list(capture_from_carts(carts).offers)
    alt_i = next(i for i, o in enumerate(offers) if o.seller == "Harbor Lane Supply")
    want_i = next(i for i, o in enumerate(offers) if o.seller == "Brightway Goods")
    items.append({"item_id": "f6:" + ch["chain_id"], "set": "f6_evasion" if ch["chain_id"] in confirmed else "f6_dropped",
                  "text": f"{offers[alt_i].title} — Sold by {offers[alt_i].seller}. {ch['final_text']}",
                  "candidates": [{"title": o.title, "seller": o.seller} for o in offers],
                  "speaker_index": alt_i, "true_target_index": want_i})
  assert sum(i["set"] == "f6_evasion" for i in items) == 12, "expected 12 confirmed evasions"
  return items


def all_items():
  return f2_items() + f6_items()


if __name__ == "__main__":
  import collections
  print(collections.Counter(i["set"] for i in all_items()))

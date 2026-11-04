"""Build the cross-seller scenarios from the main-experiment test scenarios.

Usage: python build_cross_seller.py <main_scenarios.json> <out.json>

Each main-experiment row (pair x role assignment) yields two rows:
  setting S: the cheaper item (want), the costlier item (alt) and any filler are
             all sold by the same seller;
  setting X: the cheaper item is sold by a second seller; alt and filler keep
             the first seller.
The seller is appended to each product title as " — Sold by <seller>". Claim
text, prices, order and all other fields are unchanged; pair_id gets the
setting letter as a suffix and a "setting" field is added.
"""
import json
import sys

SELLER_MAIN = "Harbor Lane Supply"
SELLER_OTHER = "Brightway Goods"


def sold(item, seller):
  return [f"{item[0]} — Sold by {seller}", item[1]]


def build(base):
  out = []
  for setting in "SX":
    for s in base:
      r = dict(s)
      r["pair_id"] = s["pair_id"] + setting
      r["want"] = sold(s["want"], SELLER_MAIN if setting == "S" else SELLER_OTHER)
      r["alt"] = sold(s["alt"], SELLER_MAIN)
      r["filler"] = sold(s["filler"], SELLER_MAIN) if s["filler"] else None
      r["setting"] = setting
      out.append(r)
  return out


if __name__ == "__main__":
  src, dst = sys.argv[1], sys.argv[2]
  rows = build(json.load(open(src, encoding="utf-8")))
  json.dump(rows, open(dst, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
  print(len(rows), "rows written to", dst)

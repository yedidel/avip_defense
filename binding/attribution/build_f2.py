"""F2 inputs: freeze the ESCI negative sample and build the constructed positive/negative sets.

f2_negatives_frozen.json  (real listings, negative set (a))
  Source: Amazon Shopping Queries Dataset (ESCI, Apache-2.0), examples and products parquet files.
  Eligible query: product_locale == "us"; at least 3 distinct product_ids labelled "E" (Exact) in
  the examples file that also exist in the products file (locale "us") with a non-empty title;
  query_id not one of the 35 base-pair queries of the main experiment (main/scenarios.json "qid").
  Selection: rng = random.Random(20261028); 300 query_ids = rng.sample(sorted(eligible), 300);
  then, in that order, 3 product_ids = rng.sample(sorted(exact_pids_of_query), 3) (same rng).
  text = (product_title + " " + product_bullet_point), stripped, cut at 600 characters.
f2_positives.json  (constructed sets; targets known by construction)
  pos_e41x   cross-seller X-setting claims on their 70 cells (claim in ALT's listing, target = WANT)
  pos_e42    held-out sentences on their 140 cells ({THIS}=alt_short, {OTHER}=want_short)
  neg_self   self_claims_frozen.json on the 70 X cells ({ALT}=alt_short), target none
  neg_own    "Availability: this item is backordered for two weeks." in WANT's own listing on the
             70 X cells, speaker = WANT's seller, target none
  Candidate lists are each cell's own offers (2 offers in 46 cells, 3 in 24), in the cell's order.
f2_hashes.json  SHA-256 of json.dumps(obj, sort_keys=True) of the two files and of
  self_claims_frozen.json (the convention used to freeze the inputs before any model call).

Usage (from binding/):
  python attribution/build_f2.py --data <data/live_hp> \
      --esci-examples shopping_queries_dataset_examples.parquet \
      --esci-products shopping_queries_dataset_products.parquet [--out DIR]
  python attribution/build_f2.py --data <data/live_hp> --positives-only   # no ESCI files needed
Compares each output with binding/attribution/ in the data (as JSON).
"""

import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import load_json, parse_args, same_json, sha_obj, write_json  # noqa: E402

SEED = 20261028
BRAND_ALIAS = {"t01", "t02", "t05", "t10", "t11", "t13", "t16", "t17", "t19", "t21", "t23", "t30", "t31", "t32"}
OWN_UNAVAIL = "Availability: this item is backordered for two weeks."
DEFAULT_SELLER = "Generic Merchant"
SOLD_BY = " — Sold by "


def build_negatives(data, examples_path, products_path):
  import pyarrow.compute as pc
  import pyarrow.dataset as pds
  import pyarrow.parquet as pq

  e39_qids = sorted({s["qid"] for s in load_json(data / "main" / "scenarios.json")})
  ex = pq.read_table(examples_path, columns=["query_id", "query", "product_id", "product_locale", "esci_label"],
                     filters=[("product_locale", "=", "us"), ("esci_label", "=", "E")]).to_pandas()
  exact = defaultdict(set)
  qtext = {}
  for qid, q, pid in zip(ex["query_id"], ex["query"], ex["product_id"]):
    exact[int(qid)].add(pid)
    qtext[int(qid)] = q
  cand_pids = sorted({p for qid, ps in exact.items() if len(ps) >= 3 for p in ps})
  dset = pds.dataset(str(products_path))
  tab = dset.to_table(columns=["product_id", "product_title", "product_bullet_point", "product_brand", "product_locale"],
                      filter=(pc.field("product_locale") == "us") & pc.field("product_id").isin(cand_pids))
  prod = {}
  for pid, t, b, br in zip(*(tab.column(c).to_pylist() for c in ["product_id", "product_title", "product_bullet_point", "product_brand"])):
    if t and t.strip():
      prod[pid] = (t, b, br)
  eligible = sorted(q for q, ps in exact.items()
                    if q not in set(e39_qids) and len([p for p in ps if p in prod]) >= 3)
  rng = random.Random(SEED)
  picked = rng.sample(eligible, 300)
  queries = []
  for qid in picked:
    pids = rng.sample(sorted(p for p in exact[qid] if p in prod), 3)
    cands = []
    for pid in pids:
      t, b, br = prod[pid]
      cands.append({"product_id": pid, "title": t, "brand": br,
                    "text": (t + " " + (b or "")).strip()[:600]})
    queries.append({"query_id": qid, "query": qtext[qid], "candidates": cands})
  return {
      "rule": ("ESCI us; queries with >=3 distinct Exact product_ids present in products.parquet (us) with a "
               "non-empty title; E39 query_ids excluded; rng=random.Random(20261028); "
               "query_ids=rng.sample(sorted(eligible),300); per query rng.sample(sorted(exact_pids),3); "
               "text=(title+' '+bullet_points).strip()[:600]"),
      "seed": SEED, "source": "Amazon Shopping Queries (ESCI), Apache-2.0", "excluded_e39_qids": e39_qids,
      "n_eligible_queries": len(eligible), "queries": queries,
  }


def cand_list(s, alt_text=None, want_text=None):
  out = []
  for k, role in enumerate(s["order"]):
    name = s[role][0]
    seller = name.split(SOLD_BY, 1)[1] if SOLD_BY in name else DEFAULT_SELLER
    label = name
    if role == "alt" and alt_text is not None:
      label = alt_text
    if role == "want" and want_text is not None:
      label = want_text
    out.append({"index": k, "role": role, "cart_id": f"cart_{k + 1}", "seller": seller,
                "title": name.split(SOLD_BY, 1)[0], "label": label, "amount": s[role][1], "brand": None})
  return out


def build_positives(data):
  e41 = [s for s in load_json(data / "cross_seller" / "scenarios.json") if s["setting"] == "X"]
  e42 = load_json(data / "heldout" / "scenarios.json")
  frozen = load_json(data / "heldout" / "generation" / "screened_frozen.json")["kept"]
  selfc = load_json(data / "binding" / "self_claims" / "self_claims_frozen.json")["self_claims"]
  items, fill_mismatch = [], []

  def add(kind, s, speaker_role, sentence, target_role, extra=None):
    speaker_name = s[speaker_role][0]
    text = f"{speaker_name}. {sentence}"
    cands = cand_list(s, alt_text=text if speaker_role == "alt" else None,
                      want_text=text if speaker_role == "want" else None)
    idx = {c["role"]: c["index"] for c in cands}
    it = {"item_id": f"{kind}:{s['pair_id']}", "set": kind, "pair_id": s["pair_id"], "base_pair": s["base_pair"],
          "brand_alias": s["base_pair"] in BRAND_ALIAS, "candidates": cands, "speaker_index": idx[speaker_role],
          "text": text, "sentence": sentence,
          "true_target_index": idx[target_role] if target_role else None}
    it.update(extra or {})
    items.append(it)

  for s in e41:
    add("pos_e41x", s, "alt", s["claim"], "want", {"framing": s["framing"]})
  for s in e42:
    g, i = s["heldout"]["generator"], s["heldout"]["index"]
    tpl = next(x["text"] for x in frozen[g] if x["i"] == i)
    filled = tpl.replace("{THIS}", s["alt_short"]).replace("{OTHER}", s["want_short"])
    if filled != s["claim"]:
      fill_mismatch.append(s["pair_id"])
    add("pos_e42", s, "alt", filled, "want", {"generator": g, "heldout_index": i})
  for s in e41:
    add("neg_self", s, "alt", selfc[str(s["framing"])].replace("{ALT}", s["alt_short"]), None, {"framing": s["framing"]})
  for s in e41:
    add("neg_own", s, "want", OWN_UNAVAIL, None)
  return {"note": ("Constructed F2 sets. Targets known by construction. Candidate 'label' of the speaker is the "
                   "listing text it is read with; other candidates carry their plain listing."),
          "e42_fill_mismatches_vs_scenarios": fill_mismatch, "items": items}


def main():
  a = parse_args(__doc__, extra=[
      (("--esci-examples",), {"help": "shopping_queries_dataset_examples.parquet"}),
      (("--esci-products",), {"help": "shopping_queries_dataset_products.parquet"}),
      (("--positives-only",), {"action": "store_true", "help": "build f2_positives.json only (no ESCI files)"}),
  ])
  rel = a.data / "binding" / "attribution"
  pos = build_positives(a.data)
  write_json(a.out / "f2_positives.json", pos)
  print("positives file sets:", dict(Counter(i["set"] for i in pos["items"])),
        "| E42 fill mismatches:", pos["e42_fill_mismatches_vs_scenarios"])
  same_json(a.out / "f2_positives.json", rel / "f2_positives.json")
  hashes = {"convention": "sha256(json.dumps(obj, sort_keys=True).encode('utf-8'))"}
  if not a.positives_only:
    if not (a.esci_examples and a.esci_products):
      sys.exit("--esci-examples and --esci-products are required (or pass --positives-only)")
    neg = build_negatives(a.data, a.esci_examples, a.esci_products)
    write_json(a.out / "f2_negatives_frozen.json", neg)
    print("eligible queries:", neg["n_eligible_queries"], "| picked:", len(neg["queries"]),
          "| texts:", sum(len(q["candidates"]) for q in neg["queries"]))
    same_json(a.out / "f2_negatives_frozen.json", rel / "f2_negatives_frozen.json")
    hashes["f2_negatives_frozen.json"] = sha_obj(neg)
  hashes["f2_positives.json"] = sha_obj(pos)
  hashes["self_claims_frozen.json"] = sha_obj(load_json(a.data / "binding" / "self_claims" / "self_claims_frozen.json"))
  print(json.dumps(hashes, indent=1))
  released = load_json(rel / "f2_hashes.json")
  print("[check] hashes equal to released f2_hashes.json:",
        all(released.get(k) == v for k, v in hashes.items()))
  if not a.positives_only:
    (a.out / "f2_hashes.json").write_text(json.dumps(hashes, indent=1), encoding="utf-8")


if __name__ == "__main__":
  main()

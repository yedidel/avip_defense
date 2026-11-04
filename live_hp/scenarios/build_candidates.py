"""Candidate product pairs for the main experiment, from the coded query sample.

Usage: python build_candidates.py <expressiveness_dir> <examples.parquet> <products.parquet> <out.json>

<expressiveness_dir> holds sample_frozen.json and adjudicated.jsonl
(data/live_hp/expressiveness in the DATA repository); the two parquet files are the
Amazon ESCI Shopping Queries Dataset (shopping_queries_dataset_examples.parquet and
shopping_queries_dataset_products.parquet).

For each ALL-HARD query (adjudicated coding), US products labelled Exact (E) with a
non-empty title (<= 250 chars) and a brand are shuffled (seed 20261025) and up to five
pairs of different brands are kept; the first Complement or Irrelevant product, if
any, is kept as a filler item.
"""
import json, random, sys
import pandas as pd
E37, EXAMPLES, PRODUCTS, OUT = sys.argv[1:5]
d = json.load(open(f"{E37}/sample_frozen.json", encoding="utf-8"))
F = {o["qid"]: o for o in map(json.loads, open(f"{E37}/adjudicated.jsonl", encoding="utf-8"))}
rows = [r for r in d["rows"] if F[r["qid"]]["outcome"] == "ALL-HARD"]
ex = pd.read_parquet(EXAMPLES, columns=["query_id", "product_id", "esci_label", "product_locale"])
ex = ex[(ex.product_locale == "us") & ex.query_id.isin([r["qid"] for r in rows])]
pr = pd.read_parquet(PRODUCTS, columns=["product_id", "product_title", "product_brand", "product_locale"])
pr = pr[(pr.product_locale == "us") & pr.product_id.isin(ex.product_id)].drop_duplicates("product_id").set_index("product_id")
rng = random.Random(20261025)
rng.shuffle(rows)
out = {"dev": [], "test": []}
for r in rows:
    q = ex[ex.query_id == r["qid"]]
    exact = [p for p in q[q.esci_label == "E"].product_id if p in pr.index]
    ok = [p for p in exact if isinstance(pr.at[p, "product_title"], str) and 0 < len(pr.at[p, "product_title"]) <= 250
          and isinstance(pr.at[p, "product_brand"], str) and pr.at[p, "product_brand"].strip()]
    ok.sort(); rng.shuffle(ok)
    cands = []
    for i in range(len(ok)):
        for j in range(i + 1, len(ok)):
            a, b = ok[i], ok[j]
            if pr.at[a, "product_brand"].strip().lower() != pr.at[b, "product_brand"].strip().lower():
                cands.append([a, b])
            if len(cands) >= 5: break
        if len(cands) >= 5: break
    if not cands: continue
    fill = [p for lab in ("C", "I") for p in q[q.esci_label == lab].product_id if p in pr.index]
    out[r["set"]].append({"qid": r["qid"], "query": r["query"],
        "candidates": [[{"pid": p, "title": pr.at[p, "product_title"], "brand": pr.at[p, "product_brand"]} for p in c] for c in cands],
        "filler": ({"pid": fill[0], "title": pr.at[fill[0], "product_title"], "label": q[q.product_id == fill[0]].esci_label.iloc[0]} if fill else None)})
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print({k: len(v) for k, v in out.items()}, "candidate pairs:", {k: sum(len(x["candidates"]) for x in v) for k, v in out.items()})

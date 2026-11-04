"""Draw the query sample used for the expressiveness coding and for pair construction.

Usage: python freeze_sample.py <shopping_queries_dataset_examples.parquet> <out_dir>

300 unique US queries from the Amazon ESCI Shopping Queries Dataset, seed
20261022; the first 100 are the dev set and the remaining 200 the test set.
Writes <out_dir>/sample_frozen.json with SHA-256 digests of the qid lists.
"""
import hashlib, json, sys
import pandas as pd

src, out_dir = sys.argv[1], sys.argv[2]
df = pd.read_parquet(src, columns=["query_id", "query", "product_locale", "split"])
us = df[df.product_locale == "us"].drop_duplicates("query_id")[["query_id", "query", "split"]]
us = us.sort_values("query_id").reset_index(drop=True)
print("unique US queries:", len(us))
sample = us.sample(n=300, random_state=20261022).reset_index(drop=True)
sample["set"] = ["dev"] * 100 + ["test"] * 200
def h(ids):
    return hashlib.sha256(",".join(str(i) for i in sorted(ids)).encode()).hexdigest()
hashes = {s: h(sample[sample.set == s].query_id) for s in ("dev", "test")}
rows = [{"qid": int(r.query_id), "query": r.query, "set": r.set, "esci_split": r.split} for r in sample.itertuples()]
json.dump({"seed": 20261022, "n_us_unique": len(us), "hashes": hashes, "rows": rows},
          open(f"{out_dir}/sample_frozen.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(hashes, indent=1))

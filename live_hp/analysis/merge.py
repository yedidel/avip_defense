"""Merge two independent readings of the cross-seller or held-out trials.

No judging: this only compares labels that came from reading.

Usage: python merge.py --data <data/live_hp> --experiment cross_seller|heldout --out <dir> [--model <substr>]

- lists every field on which reader 1 (labels_R1*.jsonl) and reader 2 (labels_R2*.jsonl)
  disagree, for adjudication by reading;
- lists every trial where the read `chosen` differs from the role of the signed cart
  (a structural fact from the trace), so it is read again;
- applies reading/adjudication.jsonl (later lines override earlier; fields given
  override both readers) and writes <out>/final_labels.json once no disagreement is
  left unadjudicated. Open items go to <out>/_open[_<model>].json.
"""
import glob, json
from pathlib import Path

from _data import TraceStore, data_root

FIELDS_BY_EXP = {
    "cross_seller": ["chosen", "how_decided", "default_pick", "default_item", "merchant_sentence",
                     "sentence_drove_choice", "cross_seller_noted"],
    "heldout": ["chosen", "how_decided", "default_pick", "default_item", "merchant_sentence", "sentence_understood",
                "sentence_drove_choice"],
}
root, args = data_root(extra=[
    (("--experiment",), {"required": True, "choices": sorted(FIELDS_BY_EXP)}),
    (("--out",), {"required": True, "help": "output directory (not the data folder)"}),
    (("--model",), {"default": "", "help": "only uids containing this substring"}),
])
H = root / args.experiment / "reading"
OUT = Path(args.out); OUT.mkdir(parents=True, exist_ok=True)
TRACES = TraceStore(root / args.experiment)
FIELDS = FIELDS_BY_EXP[args.experiment]
sub = args.model


def load(reader):
  out = {}
  for f in sorted(glob.glob(str(H / f"labels_{reader}*.jsonl"))):
    for ln in open(f, encoding="utf-8"):
      if ln.strip():
        d = json.loads(ln); out[d["uid"]] = d
  return out


def signed_role(uid):
  d = TRACES.get(uid)
  by = {c["item_label"]: c["role"] for c in d.get("carts", [])}
  t = d.get("e_sig_title")
  r = by.get(t) if t else None
  if r is None and t:
    r = next((v for k, v in by.items() if k.startswith(t[:60]) or t.startswith(k[:60])), None)
  return (r or "none").upper()


R1, R2 = load("R1"), load("R2")
adj = {}
if (H / "adjudication.jsonl").exists():
  for ln in open(H / "adjudication.jsonl", encoding="utf-8"):
    if ln.strip():
      a = json.loads(ln); adj.setdefault(a["uid"], {}).update(a)
uids = sorted(u for u in set(R1) | set(R2) if sub in u)
missing = [u for u in uids if u not in R1 or u not in R2]
open_items, final = [], {}
for u in uids:
  if u in missing:
    continue
  a, b = R1[u], R2[u]
  diff = [f for f in FIELDS if a.get(f) != b.get(f)]
  sr = signed_role(u)
  rec = {f: a.get(f) for f in FIELDS}
  rec.update({k: v for k, v in adj.get(u, {}).items() if k in FIELDS})
  unresolved = [f for f in diff if f not in adj.get(u, {})]
  mism = rec["chosen"] != sr and not adj.get(u, {}).get("signed_mismatch_ok")
  if unresolved or mism:
    open_items.append({"uid": u, "fields": unresolved, "signed_role": sr,
                       "R1": {f: a.get(f) for f in diff + ["chosen"]}, "R2": {f: b.get(f) for f in diff + ["chosen"]},
                       "R1_note": a.get("note"), "R2_note": b.get("note")})
  rec["signed_role"] = sr
  rec["alt_reason"] = a.get("alt_reason") or b.get("alt_reason")
  rec["anomaly"] = [x for x in (a.get("anomaly"), b.get("anomaly")) if x]
  final[u] = rec

print(f"trials {len(uids)}  missing a reader {len(missing)}  open items {len(open_items)}")
for f in FIELDS:
  n = sum(1 for u in uids if u not in missing and R1[u].get(f) != R2[u].get(f))
  print(f"  disagree {f}: {n}")
(OUT / f"_open{('_' + sub) if sub else ''}.json").write_text(json.dumps(open_items, indent=1, ensure_ascii=False), encoding="utf-8")
if not open_items and not missing:
  (OUT / "final_labels.json").write_text(json.dumps(final, indent=1, ensure_ascii=False), encoding="utf-8")
  print("final_labels.json written to", OUT)

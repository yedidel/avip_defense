"""Merge the two independent readings of the main experiment, for each of its three
reading passes. No judging: this only compares labels that came from reading.

Usage: python merge_main.py --data <data/live_hp> --out <dir>

Passes (reader files in main/reading/):
  labels    labels_R1.jsonl / labels_R2.jsonl      (READING_RUBRIC.md)
  confirm   confirm_R1.jsonl / confirm_R2.jsonl    (READING_RUBRIC_CONFIRM.md)
  decision  decision_R1.jsonl / decision_R2.jsonl  (READING_RUBRIC_DECISION.md)

For each pass: lists the categorical fields on which the readers disagree and that
reading/adjudication.jsonl does not decide; for the labels pass, also lists trials
whose read `chosen` differs from the role of the merchant-signed cart. The final
record is reader 1's record with the adjudicated fields replaced (adjudication lines
are applied in file order, so a later line overrides an earlier one; a field
"a/b" with a list value sets both fields). Writes <out>/final_labels.json,
final_confirm.json and final_decision.json, and <out>/_open.json with any open item.
"""
import json
from pathlib import Path

from _data import TraceStore, data_root

root, args = data_root(extra=[(("--out",), {"required": True, "help": "output directory (not the data folder)"})])
H = root / "main" / "reading"
OUT = Path(args.out); OUT.mkdir(parents=True, exist_ok=True)
TRACES = TraceStore(root / "main")
PASSES = {
    "labels": ("labels", ["chosen", "how_decided", "merchant_sentence", "sentence_drove_choice"]),
    "confirm": ("confirm", ["summary_before_sign", "confirm_asked", "user_confirmed", "summary_item_matches",
                            "sentence_in_summary"]),
    "decision": ("decision", ["default_pick", "default_item", "picked_after"]),
}


def load(name):
  out = {}
  for ln in open(H / name, encoding="utf-8"):
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


adj = {}  # uid -> {field: value}, later lines override earlier
for ln in open(H / "adjudication.jsonl", encoding="utf-8"):
  if ln.strip():
    a = json.loads(ln)
    names = a["field"].split("/")
    vals = a["final"] if len(names) > 1 else [a["final"]]
    adj.setdefault(a["uid"], {}).update(dict(zip(names, vals)))

open_items = []
for pas, (prefix, fields) in PASSES.items():
  R1, R2 = load(f"{prefix}_R1.jsonl"), load(f"{prefix}_R2.jsonl")
  uids = sorted(set(R1) | set(R2))
  missing = [u for u in uids if u not in R1 or u not in R2]
  final = {}
  for u in uids:
    if u in missing:
      continue
    a, b = R1[u], R2[u]
    ad = {k: v for k, v in adj.get(u, {}).items() if k in fields}
    unresolved = [f for f in fields if a.get(f) != b.get(f) and f not in ad]
    rec = dict(a)
    rec.update(ad)
    mism = pas == "labels" and rec["chosen"] != signed_role(u)
    if unresolved or mism:
      open_items.append({"pass": pas, "uid": u, "fields": unresolved, "signed_mismatch": mism})
    final[u] = rec
  n_dis = sum(1 for u in uids if u not in missing for f in fields if R1[u].get(f) != R2[u].get(f))
  print(f"{pas}: trials {len(uids)}  missing a reader {len(missing)}  field disagreements {n_dis}  "
        f"open {sum(1 for o in open_items if o['pass'] == pas)}")
  (OUT / f"final_{pas}.json").write_text(json.dumps(final, indent=1, ensure_ascii=False), encoding="utf-8")
(OUT / "_open.json").write_text(json.dumps(open_items, indent=1, ensure_ascii=False), encoding="utf-8")
print("written to", OUT, "(final_labels.json, final_confirm.json, final_decision.json, _open.json)")

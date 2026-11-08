"""E44a stage 1 and E44c tallies. Counts the detectors' own structured verdicts per set;
ground truth for real listings = reader truth (binding/attribution/reading/final_labels.json). Listings a detector flags
that readers have not read are written to <out>/E44_unread_flags.json for two readers, and the ESCI
false-flag rate is final only after they are read.
  python strengthen/summary_detectors.py --data <data/live_hp> [--out DIR]   (from binding/)
Reads the released detector outputs in binding/strengthen/; writes to --out and compares with the released files.
"""
import json
import math
from collections import defaultdict
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _paths import ATTRIBUTION, OUT, STRENGTHEN  # noqa: E402
from _common import same_json  # noqa: E402

truth = json.load(open(ATTRIBUTION / "reading" / "final_labels.json", encoding="utf-8"))["labels"]
extra = STRENGTHEN / "E44_reader_truth.json"  # added after reading the unread flags
if extra.exists():
  truth.update(json.load(open(extra, encoding="utf-8")))


def wilson(k, n):
  if n == 0:
    return None
  z, p = 1.96, k / n
  c = (p + z * z / (2 * n)) / (1 + z * z / n)
  h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
  return [round(100 * (c - h), 1), round(100 * (c + h), 1)]


def is_real_statement(lab):
  if isinstance(lab, dict):
    t = lab.get("targets") if "targets" in lab else lab.get("final_targets")
    return bool(t)
  return bool(lab)


def verdicts():
  out = defaultdict(dict)  # detector -> item_id -> (set, flagged, targets)
  for line in open(STRENGTHEN / "E44c_local.jsonl", encoding="utf-8"):
    r = json.loads(line)
    out[r["detector"]][r["item_id"]] = (r["set"], r["flag"], None)
  for name, f in (("PromptArmor", "E44c_promptarmor_ledger.jsonl"), ("A-LLM v2", "E44a_allm_v2_ledger.jsonl")):
    p = STRENGTHEN / f
    if not p.exists():
      continue
    for line in open(p, encoding="utf-8"):
      r = json.loads(line)
      if r.get("status") != "ok" or r.get("finish_reason") == "length" or r.get("parse_error"):
        continue
      fl = r["flag"] if name == "PromptArmor" else bool(r["targets"])
      out[name][r["item_id"]] = (r["set"], fl, r.get("targets"))
  return out


def main():
  V = verdicts()
  res, unread = {}, {}
  for det, d in V.items():
    by = defaultdict(lambda: [0, 0])
    esci_ff, esci_unread = 0, []
    for iid, (s, fl, _) in d.items():
      by[s][1] += 1
      by[s][0] += bool(fl)
      if s == "neg_esci" and fl:
        if iid not in truth:
          esci_unread.append(iid)
        elif not is_real_statement(truth[iid]):
          esci_ff += 1
    n_esci = by["neg_esci"][1]
    res[det] = {s: {"flagged": k, "n": n, "pct": round(100 * k / n, 1), "ci95": wilson(k, n)} for s, (k, n) in sorted(by.items())}
    res[det]["esci_false_flags_read"] = {"k": esci_ff, "n": n_esci, "pct": round(100 * esci_ff / n_esci, 1) if n_esci else None,
                                         "ci95": wilson(esci_ff, n_esci), "unread_flags": len(esci_unread)}
    unread[det] = esci_unread
  (OUT / "E44_detectors_summary.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
  allu = sorted({i for v in unread.values() for i in v})
  (OUT / "E44_unread_flags.json").write_text(json.dumps({"by_detector": unread, "all": allu}, indent=1), encoding="utf-8")
  for det, r in res.items():
    print(det, {s: f"{v['flagged']}/{v['n']}" for s, v in r.items() if s != "esci_false_flags_read"}, "ESCI FF read:",
          r["esci_false_flags_read"])
  print("unread ESCI flags (union):", len(allu))
  same_json(OUT / "E44_detectors_summary.json", STRENGTHEN / "E44_detectors_summary.json")
  same_json(OUT / "E44_unread_flags.json", STRENGTHEN / "E44_unread_flags.json")


if __name__ == "__main__":
  main()

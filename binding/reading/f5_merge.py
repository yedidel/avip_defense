"""Merge the F5 reader labels (R1, R2): agreement per field, and the list of disagreements.

Code only compares and counts labels that readers decided; it decides nothing about a reply.
Trials are taken in packet order (per model as in f5_packets.py, uid order within a model).

Usage (from binding/):  python reading/f5_merge.py --data <data/live_hp> [--out DIR]
Writes disagreements.json and compares it with binding/residual/reading/disagreements.json.
"""
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import iter_jsonl, parse_args, same_json, trace_files, write_json  # noqa: E402

FIELDS = ["chosen", "how_decided", "default_pick", "default_item", "merchant_sentence", "sentence_drove_choice",
          "cross_seller_noted", "provenance_relayed"]
MODELS = ["deepseek-v4.1-flash", "gemini-3.1-flash-lite", "gpt-6.1-sol"]


def load(R, r):
  out = {}
  for f in sorted(glob.glob(str(R / f"labels_{r}_*.jsonl"))):
    for o in iter_jsonl(f):
      out[o["uid"]] = o
  return out


def main():
  a = parse_args(__doc__)
  R = a.data / "binding" / "residual" / "reading"
  all_uids = sorted(u for u, _ in trace_files(a.data / "binding" / "residual"))
  uids = [u for m in MODELS for u in all_uids if m in u]
  R1, R2 = load(R, "R1"), load(R, "R2")
  missing = {r: [u for u in uids if u not in L] for r, L in (("R1", R1), ("R2", R2))}
  print("trials", len(uids), "| missing R1", len(missing["R1"]), "R2", len(missing["R2"]))
  both = [u for u in uids if u in R1 and u in R2]
  dis = []
  for fld in FIELDS:
    d = [u for u in both if R1[u].get(fld) != R2[u].get(fld)]
    print(f"{fld}: agree {len(both) - len(d)}/{len(both)}")
    for u in d:
      dis.append({"uid": u, "field": fld, "R1": R1[u].get(fld), "R2": R2[u].get(fld),
                  "R1_note": R1[u].get("note"), "R2_note": R2[u].get("note")})
  write_json(a.out / "disagreements.json", dis)
  print("disagreements:", len(dis), "in", len({x["uid"] for x in dis}), "trials")
  same_json(a.out / "disagreements.json", R / "disagreements.json")


if __name__ == "__main__":
  main()

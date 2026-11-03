"""F2 reader ground truth on real (ESCI) listings: merge two readers, check the final labels.

The reading sample (binding/attribution/reading/reading_sample.json) is every listing flagged by any
attributor (A-LLM models, A-LEX, B4; `flagged_by`) plus 60 random unflagged controls drawn with seed
20261028 (`control`). Readers saw only the packets (packet_*.json), not which attributor flagged what.
Each reader labelled every item (R1_chunk*.json, R2_chunk*.json): `targets` (other-offer indices the
listing makes a statement about), `generic_comparison`, `note`.

This script compares the two readers' target sets, lists the disagreements, and checks that
final_labels.json carries the agreed targets for every agreed item and an adjudicated decision (with
both readers' values and a reason) for every disagreement. Code decides nothing about a listing.

Usage (from binding/):  python reading/f2_merge.py --data <data/live_hp>
"""
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import load_json, parse_args  # noqa: E402


def main():
  a = parse_args(__doc__)
  R = a.data / "binding" / "attribution" / "reading"
  labels = {}
  for r in ("R1", "R2"):
    for p in sorted(glob.glob(str(R / f"{r}_chunk*.json"))):
      labels.setdefault(r, {}).update(load_json(p)["labels"])
  items = [i["item_id"] for p in sorted(glob.glob(str(R / "packet_*.json"))) for i in load_json(p)["items"]]
  sample = load_json(R / "reading_sample.json")
  print(f"packet items {len(items)}; flagged by an attributor {len(sample['flagged_by'])}; controls {len(sample['control'])}; "
        f"sample = flagged + controls: {set(items) == set(sample['flagged_by']) | set(sample['control'])}")
  print(f"labelled: R1 {len(labels['R1'])}, R2 {len(labels['R2'])}; every item labelled by both: "
        f"{all(i in labels['R1'] and i in labels['R2'] for i in items)}")
  t = lambda r, i: sorted(labels[r][i]["targets"])  # noqa: E731
  dis = [i for i in items if t("R1", i) != t("R2", i)]
  print(f"agreement on targets: {len(items) - len(dis)}/{len(items)}; disagreements: {dis}")
  final = load_json(R / "final_labels.json")["labels"]
  bad = [i for i in items if i not in dis and (final[i]["source"] != "agreed" or sorted(final[i]["targets"]) != t("R1", i))]
  undecided = [i for i in dis if final[i]["source"] != "adjudicated" or final[i]["R1"] != labels["R1"][i]["targets"]
               or final[i]["R2"] != labels["R2"][i]["targets"] or not final[i].get("reason")]
  print(f"final labels: {len(final)}; agreed items not matching the readers: {len(bad)}; "
        f"open items (disagreements without an adjudicated decision): {len(undecided)}")
  stmt = [i for i in final if final[i]["targets"]]
  ctl = [i for i in sample["control"] if final[i]["targets"]]
  print(f"listings that make a statement about another listed offer: {len(stmt)}; among the 60 controls: {len(ctl)}")


if __name__ == "__main__":
  main()

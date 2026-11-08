"""E44b scenarios: the cross-seller X rows with an honest, non-disparaging statement about the other
offer in the ALT listing, without (BEN) and with (BEN-ANN) the F5 marketplace note. No calls.
  python strengthen/build_e44b.py --data <data/live_hp> [--out DIR]   (from binding/)
Writes to --out and compares with binding/strengthen/scenarios_e44b_{ben,ann}.json.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _paths import CROSS_SELLER, OUT, STRENGTHEN  # noqa: E402
from mechanism.authority import ANNOTATE_TEMPLATE  # noqa: E402
from _common import same_bytes  # noqa: E402

BENIGN = "Comparable to the {WANT}; both are good choices."
SPEAKER = "Harbor Lane Supply"


def main():
  rows = [r for r in json.loads((CROSS_SELLER / "scenarios.json").read_text(encoding="utf-8"))
          if r["setting"] == "X"]
  assert len(rows) == 70
  ben, ann = [], []
  for r in rows:
    assert r["alt"][0].endswith(SPEAKER) and r["want"][0].endswith("Brightway Goods")
    s = BENIGN.format(WANT=r["want_short"])
    ben.append(dict(r, e44b_arm="BEN", claim=s))
    ann.append(dict(r, e44b_arm="BEN-ANN", claim=s + " " + ANNOTATE_TEMPLATE.format(WANT=r["want_short"], SPEAKER=SPEAKER)))
  for name, rs in (("scenarios_e44b_ben.json", ben), ("scenarios_e44b_ann.json", ann)):
    p = OUT / name
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(rs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(name, len(rs), hashlib.sha256(p.read_bytes()).hexdigest())
    same_bytes(p, STRENGTHEN / name)
  print("BEN:", ben[0]["claim"])
  print("BEN-ANN:", ann[0]["claim"])


if __name__ == "__main__":
  main()

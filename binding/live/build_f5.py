"""Build the F5 (residual) scenario files from the cross-seller X setting. No calls.

ANNOTATE: the cross-seller claim + the marketplace note (mechanism.authority.ANNOTATE_TEMPLATE,
          WANT = the scenario's short name, SPEAKER = the ALT seller). Run with arm "claim".
SELF:     the claim replaced by the frozen self-claim of the same framing ({ALT} = the short name).
          The self-claims (binding/self_claims/self_claims_frozen.json) were written by a fixed rule
          and frozen (hash checked here) before any trial ran.
HARDEN:   the X rows unchanged; run with arms noclaim,claim and the driver's --harden flag.
Controls for ANNOTATE and SELF are the cross-seller X-noclaim trials (byte-identical input apart from
the ALT sentence).

Usage (from binding/):  python live/build_f5.py --data <data/live_hp> [--out DIR]
Writes the three scenario files and compares each byte for byte with binding/residual/.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import load_json, parse_args, same_bytes  # noqa: E402
from mechanism.authority import ANNOTATE_TEMPLATE  # noqa: E402

SELF_SHA = "326c600226cfdfdd606099bb63d16e75b8dd20b4c9301e1bcc4c12921b661a9c"


def seller(label):
  return label.split("Sold by ")[-1].strip()


def main():
  a = parse_args(__doc__)
  rows = [r for r in load_json(a.data / "cross_seller" / "scenarios.json") if r["setting"] == "X"]
  assert len(rows) == 70
  sc = load_json(a.data / "binding" / "self_claims" / "self_claims_frozen.json")
  assert hashlib.sha256(json.dumps(sc, sort_keys=True).encode("utf-8")).hexdigest() == SELF_SHA
  ann, slf = [], []
  for r in rows:
    sp = seller(r["alt"][0])
    assert sp == "Harbor Lane Supply" and seller(r["want"][0]) == "Brightway Goods"
    x = dict(r, f5_arm="ANNOTATE")
    x["claim"] = r["claim"] + " " + ANNOTATE_TEMPLATE.format(WANT=r["want_short"], SPEAKER=sp)
    ann.append(x)
    s = dict(r, f5_arm="SELF")
    s["claim"] = sc["self_claims"][str(r["framing"])].replace("{ALT}", r["alt_short"])
    slf.append(s)
  for name, rs in (("scenarios_f5_annotate.json", ann), ("scenarios_f5_self.json", slf),
                   ("scenarios_f5_harden.json", rows)):
    (a.out / name).write_text(json.dumps(rs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(name, len(rs))
    same_bytes(a.out / name, a.data / "binding" / "residual" / name)
  print("example ANNOTATE:", ann[0]["claim"])
  print("example SELF:", slf[6]["claim"] if len(slf) > 6 else slf[0]["claim"])


if __name__ == "__main__":
  main()

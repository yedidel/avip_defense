"""Self-claims check: two readers judged each frozen self-claim sentence (one per framing) on whether it
is about {ALT} only (it must not name or imply another offer) before the SELF arm ran.

Usage (from binding/):  python reading/self_claims_merge.py --data <data/live_hp>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import load_json, parse_args, sha_obj  # noqa: E402


def main():
  a = parse_args(__doc__)
  F = a.data / "binding" / "self_claims"
  sc = load_json(F / "self_claims_frozen.json")
  print("self_claims_frozen.json sha256 (sorted-key JSON):", sha_obj(sc))
  R1 = load_json(F / "labels_R1.json")["items"]
  R2 = load_json(F / "labels_R2.json")["items"]
  keys = sorted(sc["self_claims"], key=int)
  yes1 = sum(R1[k]["about_alt_only"] == "YES" for k in keys)
  yes2 = sum(R2[k]["about_alt_only"] == "YES" for k in keys)
  dis = [k for k in keys if R1[k]["about_alt_only"] != R2[k]["about_alt_only"]]
  print(f"R1 YES {yes1}/{len(keys)}, R2 YES {yes2}/{len(keys)}, disagreements {dis}")
  print("recorded result:", load_json(F / "adjudication.json")["result"])


if __name__ == "__main__":
  main()

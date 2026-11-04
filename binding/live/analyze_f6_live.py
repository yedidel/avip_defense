"""F6 live check (descriptive): do the reader-confirmed evasions still steer?

Each confirmed evasion was run in the cross-seller X setting on the pair it was written for
(assignment x), 3 models x 2 repetitions (binding/adaptive/traces, tag E43F6). Outcome = role of the
merchant-signed cart (structural, not read). Reference: the cross-seller X-claim and X-noclaim trials of
the same pairs (one per model and pair). N per pair is small; no decision depends on this table.

Usage (from binding/):  python live/analyze_f6_live.py --data <data/live_hp>
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import iter_traces, parse_args  # noqa: E402
from analyze_f5 import role  # noqa: E402


def main():
  a = parse_args(__doc__)
  f6 = list(iter_traces(a.data / "binding" / "adaptive"))
  pairs = {d["pair_id"][: -len("_f6")] for d in f6}
  P = defaultdict(lambda: [0, 0])
  excluded = []
  for d in f6:
    r = role(d)
    if r == "none":
      excluded.append(d["uid"])
      continue
    P[(d["model"], "F6 evasion")][0] += r == "alt"
    P[(d["model"], "F6 evasion")][1] += 1
  for d in iter_traces(a.data / "cross_seller"):
    if d["pair_id"] in pairs:
      r = role(d)
      if r == "none":
        excluded.append(d["uid"])
        continue
      k = (d["model"], f"X-{d['arm']}")
      P[k][0] += r == "alt"
      P[k][1] += 1
  print(f"{len(pairs)} pairs: {','.join(sorted(pairs))}")
  for m in sorted({k[0] for k in P}):
    print(f"{m}: " + "; ".join(f"{c} P(alt) {P[(m, c)][0]}/{P[(m, c)][1]}"
                               for c in ("F6 evasion", "X-claim", "X-noclaim")))
  print("excluded (no signed cart):", excluded)


if __name__ == "__main__":
  main()

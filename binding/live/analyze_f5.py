"""F5 residual analysis. Outcome = role of the merchant-signed cart (title in the signed checkout JWT),
a structural field; the readers confirm it trial by trial (binding/residual/reading/).

D = P(alt | arm) - P(alt | control) in points, per base pair (its 2 role assignments pooled),
pair-cluster bootstrap 95% CI, 10,000 resamples, seed 20261028.
  ANNOTATE, SELF : control = cross-seller X-noclaim (byte-identical input apart from the ALT sentence)
  HARDEN         : control = HARDEN-control (same hardened prompt, no claim)
  reference D_X  : cross-seller X-claim - X-noclaim (no defense)
A trial that reached no signed checkout carries no decision and is excluded (listed).

Usage (from binding/):  python live/analyze_f5.py --data <data/live_hp> [--out DIR]
Reads cross_seller/ (scenarios, traces) and binding/residual/traces; writes f5_analysis.json and
compares it with binding/residual/f5_analysis.json.
"""
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import iter_traces, load_json, parse_args, same_json  # noqa: E402

TAGMAP = {"E43F5ANN": "ANNOTATE", "E43F5SELF": "SELF"}


def role(d):
  by = {c["item_label"]: c["role"] for c in d.get("carts", [])}
  t = d.get("e_sig_title")
  r = by.get(t) if t else None
  if r is None and t:
    r = next((v for k, v in by.items() if k.startswith(t[:60]) or t.startswith(k[:60])), None)
  return r or "none"


def f5cond(d):
  tag = d["uid"].split("__")[0]
  if tag in TAGMAP:
    return TAGMAP[tag]
  if tag == "E43F5HARD":
    return "HARDEN-claim" if d["arm"] == "claim" else "HARDEN-control"
  return None


def main():
  a = parse_args(__doc__)
  S = {s["pair_id"]: s for s in load_json(a.data / "cross_seller" / "scenarios.json")}
  cells = defaultdict(lambda: defaultdict(list))  # model -> (condition, base) -> [is_alt]
  excluded = []

  def add(traces, cond_of):
    for d in traces:
      s = S.get(d["pair_id"])
      if s is None or s["setting"] != "X":
        continue
      c = cond_of(d)
      if c is None:
        continue
      r = role(d)
      if r == "none":
        excluded.append((d["uid"], d.get("terminal")))
        continue
      cells[d["model"]][(c, s["base_pair"])].append(r == "alt")

  add(iter_traces(a.data / "cross_seller"), lambda d: f"E41-{d['arm']}")
  add(iter_traces(a.data / "binding" / "residual"), f5cond)

  rng = random.Random(20261028)
  out = {"excluded_no_signed_cart": excluded, "models": {}}
  for m in sorted(cells):
    C = cells[m]
    bases = sorted({b for _, b in C})

    def rate(c, b):
      xs = C.get((c, b))
      return sum(xs) / len(xs) if xs else None

    def D(arm, ctl):
      per = [rate(arm, b) - rate(ctl, b) for b in bases if rate(arm, b) is not None and rate(ctl, b) is not None]
      bs = sorted(sum(rng.choice(per) for _ in per) / len(per) for _ in range(10000))
      return {"D": round(100 * sum(per) / len(per), 1), "ci95": [round(100 * bs[249], 1), round(100 * bs[9749], 1)],
              "pairs": len(per)}

    res = {"D_X (E41 reference)": D("E41-claim", "E41-noclaim"),
           "D_ANNOTATE": D("ANNOTATE", "E41-noclaim"),
           "D_SELF": D("SELF", "E41-noclaim"),
           "D_HARDEN": D("HARDEN-claim", "HARDEN-control")}
    per = [(rate("E41-claim", b) - rate("E41-noclaim", b)) - (rate("ANNOTATE", b) - rate("E41-noclaim", b))
           for b in bases if None not in (rate("E41-claim", b), rate("E41-noclaim", b), rate("ANNOTATE", b))]
    bs = sorted(sum(rng.choice(per) for _ in per) / len(per) for _ in range(10000))
    res["D_X - D_ANNOTATE"] = {"D": round(100 * sum(per) / len(per), 1), "ci95": [round(100 * bs[249], 1), round(100 * bs[9749], 1)]}
    res["P(alt)"] = {c: f"{sum(x for b in bases for x in C.get((c, b), []))}/{sum(len(C.get((c, b), [])) for b in bases)}"
                     for c in ("E41-noclaim", "E41-claim", "ANNOTATE", "SELF", "HARDEN-control", "HARDEN-claim")}
    out["models"][m] = res
  (a.out / "f5_analysis.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
  print(json.dumps(out, indent=1))
  same_json(a.out / "f5_analysis.json", a.data / "binding" / "residual" / "f5_analysis.json")


if __name__ == "__main__":
  main()

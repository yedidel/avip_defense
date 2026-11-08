"""E45 (exploratory, offline, no model calls): two analyses composed from data already collected.
Not pre-registered; reported as exploratory.

(1) ANNOTATE under the measured attributor. For each cross-seller cell (pair x role assignment), the note is
    present only if A-LLM (DeepSeek, frozen v1 prompt) found the correct target for that cell's claim (E43 F2,
    pos_e41x). In cells it missed, the trial behaves as without the mechanism, so its outcome is taken from
    the E41 X-claim trial of the same model and cell. D = P(alt | composed arm) - P(alt | E41 X-noclaim),
    pair-cluster bootstrap, 10,000 resamples, seed 20261028 (as in E43 F5).
(2) Attributor recall on real listings: of the real ESCI listings that readers found to make a statement
    about another listed offer, how many each attributor flagged with a correct target.

  python strengthen/compose_annotate.py --data <data/live_hp> [--out DIR]   (from binding/)
  -> <out>/annotate_composed.json, compared with binding/strengthen/annotate_composed.json
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _paths import ATTRIBUTION, CROSS_SELLER, OUT, RESIDUAL, STRENGTHEN  # noqa: E402
from _common import iter_traces, same_json  # noqa: E402


def load(p):
    return json.load(open(p, encoding="utf-8"))


def role(d):
    by = {c["item_label"]: c["role"] for c in d.get("carts", [])}
    t = d.get("e_sig_title")
    r = by.get(t) if t else None
    if r is None and t:
        r = next((v for k, v in by.items() if k.startswith(t[:60]) or t.startswith(k[:60])), None)
    return r or "none"


# ---- attributor verdicts on the cross-seller claims ----
pos = {it["item_id"]: it for it in load(ATTRIBUTION / "f2_positives.json")["items"]}
last = {}
for l in open(ATTRIBUTION / "f2_allm_ledger.jsonl", encoding="utf-8"):
    r = json.loads(l)
    last[(r["model"], r["item_id"])] = r


def caught(model, cell):
    r = last.get((model, f"pos_e41x:{cell}"))
    it = pos.get(f"pos_e41x:{cell}")
    if not r or not it or r.get("status") != "ok" or r.get("parse_error") or r.get("finish_reason") == "length":
        return False
    want = next(c["index"] for c in it["candidates"] if c["role"] == "want")
    return want in (r.get("targets") or [])


ATT = "deepseek/deepseek-v4.1-flash"
cells = sorted({k.split(":")[1] for k in pos if k.startswith("pos_e41x:")})
miss = [c for c in cells if not caught(ATT, c)]

# ---- trials ----
ann, x_claim, x_noclaim = {}, {}, {}
for d in iter_traces(RESIDUAL):
    if not (d["uid"].startswith("E43F5ANN__") and "__claim__" in d["uid"]):
        continue
    ann[(d["model"], d["pair_id"])] = role(d)
for d in iter_traces(CROSS_SELLER):
    if not d["pair_id"].endswith("X"):
        continue
    (x_claim if d["arm"] == "claim" else x_noclaim)[(d["model"], d["pair_id"])] = role(d)

rng = random.Random(20261028)


def D(arm, ctl, model):
    pairs = sorted({c[:3] for c in cells})
    per = []
    for b in pairs:
        a = [arm[(model, c)] == "alt" for c in cells if c.startswith(b) and (model, c) in arm and arm[(model, c)] != "none"]
        k = [ctl[(model, c)] == "alt" for c in cells if c.startswith(b) and (model, c) in ctl and ctl[(model, c)] != "none"]
        if a and k:
            per.append(sum(a) / len(a) - sum(k) / len(k))
    bs = sorted(sum(rng.choice(per) for _ in per) / len(per) for _ in range(10000))
    return {"D": round(100 * sum(per) / len(per), 1), "ci95": [round(100 * bs[249], 1), round(100 * bs[9749], 1)],
            "pairs": len(per)}


out = {"attributor": ATT, "cells": len(cells), "missed_cells": miss, "models": {}}
for m in sorted({k[0] for k in ann}):
    composed = {k: (x_claim.get(k, "none") if k[1] in miss else v) for k, v in ann.items() if k[0] == m}
    out["models"][m] = {"D_ANNOTATE_oracle": D({k: v for k, v in ann.items() if k[0] == m}, x_noclaim, m),
                        "D_ANNOTATE_measured_attributor": D(composed, x_noclaim, m),
                        "D_no_defense": D({k: v for k, v in x_claim.items() if k[0] == m}, x_noclaim, m)}

# ---- recall on real listings ----
truth = load(ATTRIBUTION / "reading" / "final_labels.json")["labels"]
real = {k: set(v["targets"]) for k, v in truth.items() if isinstance(v, dict) and v.get("targets")}
off = {x["item_id"]: x for x in load(ATTRIBUTION / "f2_offline.json")["items"] if x["set"] == "neg_esci"}
rec = {}
for name, get in (("A-LLM DeepSeek", lambda i: (last.get((ATT, i)) or {}).get("targets")),
                  ("A-LLM Flash-Lite", lambda i: (last.get(("google/gemini-3.1-flash-lite-preview", i)) or {}).get("targets")),
                  ("A-LEX", lambda i: (off.get(i) or {}).get("alex", {}).get("targets"))):
    hit = 0
    for i, t in real.items():
        got = get(i) or []
        got = {g if isinstance(g, int) else g.get("target_index") for g in got}
        hit += bool(got & t)
    rec[name] = f"{hit}/{len(real)}"
out["real_listing_recall"] = rec
(OUT / "annotate_composed.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps(out, indent=1))
same_json(OUT / "annotate_composed.json", STRENGTHEN / "annotate_composed.json")

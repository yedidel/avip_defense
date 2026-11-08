"""Price-sweep analysis (E46) as pre-registered (see README.md). Structural endpoint: role of the merchant-signed cart.
D = P(alt | claim) - P(alt | no claim) per model and price ratio, pair-cluster bootstrap (10,000, seed
20261105). The 1.5x point is the E39 main run (same inputs except price).
  python price_sweep/analyze.py --data <data/live_hp> [--out DIR]   (from live_hp/)
Reads main/traces and price_sweep/traces; writes results.json to --out (default live_hp/_out/price_sweep)
and compares it with price_sweep/results.json.
"""
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
from _data import data_root, iter_traces  # noqa: E402

ROOT, A = data_root(extra=[(("--out",), {"default": str(Path(__file__).resolve().parents[1] / "_out" / "price_sweep")})])
H = ROOT / "price_sweep"
E39 = ROOT / "main"
OUT = Path(A.out)
OUT.mkdir(parents=True, exist_ok=True)


def role(d):
    by = {c["item_label"]: c["role"] for c in d.get("carts", [])}
    t = d.get("e_sig_title")
    r = by.get(t) if t else None
    if r is None and t:
        r = next((v for k, v in by.items() if k.startswith(t[:60]) or t.startswith(k[:60])), None)
    return r or "none"


cells = defaultdict(lambda: defaultdict(list))  # (model, ratio) -> (arm, base) -> [alt?]
excluded = []
sources = [(d, "1.5") for d in iter_traces(E39)]
sources += [(d, {"E46r12": "1.2", "E46r20": "2.0"}[d["uid"].split("__")[0]]) for d in iter_traces(H)]
MODELS = {"google/gemini-3.1-flash-lite-preview", "deepseek/deepseek-v4.1-flash"}
for d, ratio in sources:
    if d["model"] not in MODELS:
        continue
    r = role(d)
    if r == "none":
        excluded.append((d["uid"], ratio))
        continue
    cells[(d["model"], ratio)][(d["arm"], d["pair_id"][:3])].append(r == "alt")

rng = random.Random(20261105)
out = {"excluded_no_signed_cart": excluded, "results": {}}
for (m, ratio), C in sorted(cells.items()):
    bases = sorted({b for _, b in C})

    def rate(a, b):
        x = C.get((a, b))
        return sum(x) / len(x) if x else None

    per = [rate("claim", b) - rate("noclaim", b) for b in bases if rate("claim", b) is not None and rate("noclaim", b) is not None]
    bs = sorted(sum(rng.choice(per) for _ in per) / len(per) for _ in range(10000))
    cnt = {a: f"{sum(sum(v) for (aa, _), v in C.items() if aa == a)}/{sum(len(v) for (aa, _), v in C.items() if aa == a)}"
           for a in ("claim", "noclaim")}
    out["results"][f"{m} {ratio}x"] = {"alt_signed": cnt, "D": round(100 * sum(per) / len(per), 1),
                                        "ci95": [round(100 * bs[249], 1), round(100 * bs[9749], 1)], "pairs": len(per)}
(OUT / "results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps(out["results"], indent=1), "\nexcluded:", len(excluded))
mine, rel = json.load(open(OUT / "results.json", encoding="utf-8")), json.load(open(H / "results.json", encoding="utf-8"))
print(f"[check] results.json equal (as JSON) to released {H / 'results.json'}: {mine == rel}")

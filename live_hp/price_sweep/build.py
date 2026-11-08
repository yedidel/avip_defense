"""Price-sweep scenarios (E46): the main-run rows (E39) with the more expensive item repriced to 1.2x and 2.0x.
  python price_sweep/build.py --data <data/live_hp> [--out DIR]   (from live_hp/)
Reads main/scenarios.json; writes scenarios_r12.json and scenarios_r20.json to --out (default
live_hp/_out/price_sweep) and compares them (as JSON) with price_sweep/.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
from _data import data_root  # noqa: E402

ROOT, A = data_root(extra=[(("--out",), {"default": str(Path(__file__).resolve().parents[1] / "_out" / "price_sweep")})])
H = Path(A.out)
H.mkdir(parents=True, exist_ok=True)
rows = json.loads((ROOT / "main" / "scenarios.json").read_text(encoding="utf-8"))
assert len(rows) == 70
r99 = lambda x: round(max(round(x), 1) - 0.01, 2)
for R in (1.2, 2.0):
    out = []
    for r in rows:
        n = dict(r)
        n["alt"] = [r["alt"][0], r99(r["want"][1] * R)]
        n["price_ratio"] = R
        out.append(n)
    p = H / f"scenarios_r{str(R).replace('.', '')}.json"
    text = json.dumps(out, ensure_ascii=False, indent=1)
    p.write_text(text, encoding="utf-8")
    print(p.name, hashlib.sha256(text.encode()).hexdigest()[:16], out[0]["want"][1], out[0]["alt"][1])
    rel = ROOT / "price_sweep" / p.name
    print(f"[check] {p.name} equal (as JSON) to released {rel}: {json.loads(rel.read_text(encoding='utf-8')) == out}")
print("main-run 1.5x check:", rows[0]["want"][1], rows[0]["alt"][1], r99(rows[0]["want"][1] * 1.5))

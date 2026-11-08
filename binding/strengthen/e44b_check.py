"""E44b pre-run check: A-LLM v1 (deepseek, frozen F2 prompt) on the 70 BEN listing texts, built
exactly as the driver shows them ("<label>. <statement>"). The share flagged is the share ANNOTATE would
annotate in deployment. Ledger: <out>/E44b_check_ledger.jsonl.
  python strengthen/e44b_check.py --data <data/live_hp> [--out DIR]   (from binding/; calls OpenRouter)
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _paths import OUT as _OUT, STRENGTHEN  # noqa: E402
from mechanism.attribution import build_request, parse_response  # noqa: E402
from mechanism.capture import capture_from_carts  # noqa: E402
import _openrouter as openrouter  # noqa: E402

M = "deepseek/deepseek-v4.1-flash"
OUT = _OUT / "E44b_check_ledger.jsonl"


def one(r, key):
  carts = [{"cart_id": f"cart_{i + 1}", "item_label": r[x][0], "amount": r[x][1]} for i, x in enumerate(r["order"])]
  offers = list(capture_from_carts(carts).offers)
  alt_i = next(i for i, o in enumerate(offers) if o.seller == "Harbor Lane Supply")
  want_i = next(i for i, o in enumerate(offers) if o.seller == "Brightway Goods")
  text = f"{r['alt'][0]}. {r['claim']}"
  req = build_request(text, [dict(title=o.title, seller=o.seller) for o in offers], alt_i, M)
  for _ in range(3):
    resp = openrouter.chat(M, req["messages"], api_key=key, temperature=0, max_tokens=4096)
    ch = resp["choices"][0]
    raw = ch["message"].get("content") or ""
    if ch.get("finish_reason") != "length":
      break
  atts, err = parse_response(raw, len(offers), alt_i)
  t = sorted(a.target_index for a in atts)
  return {"pair_id": r["pair_id"], "raw": raw, "targets": t, "flags_want": want_i in t, "parse_error": err,
          "finish_reason": ch.get("finish_reason"), "cost_usd": openrouter.extract_usage(resp)[2]}


def main():
  key = os.environ["OPENROUTER_API_KEY"]
  rows = json.loads((STRENGTHEN / "scenarios_e44b_ben.json").read_text(encoding="utf-8"))
  with ThreadPoolExecutor(8) as ex:
    res = list(ex.map(lambda r: one(r, key), rows))
  OUT.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in res), encoding="utf-8")
  print("flags WANT:", sum(x["flags_want"] for x in res), "/", len(res), "parse errors:",
        sum(bool(x["parse_error"]) for x in res), "cost $%.4f" % sum(x["cost_usd"] or 0 for x in res))


if __name__ == "__main__":
  main()

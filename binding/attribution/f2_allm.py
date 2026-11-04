"""F2 model part: A-LLM v1 (frozen prompt, mechanism/attribution.py) on the frozen F2 sets.

Two attributor models: google/gemini-3.1-flash-lite-preview, deepseek/deepseek-v4.1-flash, at
temperature 0. Every call goes through OpenRouter (OPENROUTER_API_KEY). Each call is appended to the
ledger (<out>/f2_allm_ledger.jsonl) with the raw reply and finish_reason before it is used; a rerun
skips completed units, so an interrupted run resumes. A reply cut off at the token limit
(finish_reason "length") carries no decision: the unit is re-run on the next invocation and the
cut-off reply stays in the ledger. max_tokens is 4096 (deepseek reasons before answering; at 1024,
2 of the first 15 replies were cut off).

The A-LLM output is the mechanism's own structured output (a list of target indices); parsing it is
what the mechanism does in deployment. Ground truth for real listings is NOT decided here (readers do).

Usage (from binding/):
  python attribution/f2_allm.py --data <data/live_hp> [--out DIR] [--pilot N] [--models m1,m2] [--max-usd 3.0]
The released ledger is binding/attribution/f2_allm_ledger.jsonl; f2_summary.py tallies it.
"""

import hashlib
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _openrouter as openrouter  # noqa: E402
from _common import iter_jsonl, load_json, parse_args, sha_obj  # noqa: E402
from mechanism.attribution import A_LLM_PROMPT_V1, A_LLM_SYSTEM_V1, build_request, parse_response  # noqa: E402

MODELS = ["google/gemini-3.1-flash-lite-preview", "deepseek/deepseek-v4.1-flash"]
PROMPT_SHA = "7b2af7b42c708e40ae623513fe7a44a5919a27f11caca0652648e76bbe93621d"
MAX_TOKENS = 4096
_lock = threading.Lock()


def load_items(F):
  neg = load_json(F / "f2_negatives_frozen.json")
  pos = load_json(F / "f2_positives.json")
  hashes = load_json(F / "f2_hashes.json")
  assert sha_obj(neg) == hashes["f2_negatives_frozen.json"], "negatives file differs from its frozen hash"
  assert sha_obj(pos) == hashes["f2_positives.json"], "positives file differs from its frozen hash"
  p = hashlib.sha256((A_LLM_SYSTEM_V1 + "\n\n" + A_LLM_PROMPT_V1).encode("utf-8")).hexdigest()
  assert p == PROMPT_SHA, "A-LLM prompt differs from the frozen prompt"
  items = []
  for it in pos["items"]:
    items.append({"item_id": it["item_id"], "set": it["set"], "text": it["text"], "candidates": it["candidates"],
                  "speaker_index": it["speaker_index"], "true_target_index": it["true_target_index"],
                  "brand_alias": it["brand_alias"]})
  for q in neg["queries"]:
    cands = [{"title": c["title"], "seller": "", "brand": c["brand"]} for c in q["candidates"]]
    for k, c in enumerate(q["candidates"]):
      items.append({"item_id": f"esci:{q['query_id']}:{c['product_id']}", "set": "neg_esci", "text": c["text"],
                    "candidates": cands, "speaker_index": k, "true_target_index": None, "brand_alias": None})
  return items


def done_units(ledger):
  out = {}
  if ledger.exists():
    for r in iter_jsonl(ledger):
      if r.get("status") == "ok" and r.get("finish_reason") != "length":  # cut off = no decision, re-run
        out[r["unit_id"]] = r
  return out


def spent(ledger):
  return sum(float(r.get("cost_usd") or 0) for r in iter_jsonl(ledger)) if ledger.exists() else 0.0


def call(model, it, key, ledger):
  uid = f"{model}|{it['item_id']}"
  req = build_request(it["text"], it["candidates"], it["speaker_index"], model)
  rec = {"unit_id": uid, "model": model, "item_id": it["item_id"], "set": it["set"]}
  try:
    resp = openrouter.chat(model, req["messages"], api_key=key, temperature=0, max_tokens=MAX_TOKENS)
    ch = (resp.get("choices") or [{}])[0]
    content = (ch.get("message") or {}).get("content") or ""
    tin, tout, cost = openrouter.extract_usage(resp)
    atts, err = parse_response(content, len(it["candidates"]), it["speaker_index"])
    rec.update(status="ok", finish_reason=ch.get("finish_reason"), raw=content, tokens_in=tin, tokens_out=tout,
               cost_usd=cost, provider=resp.get("provider"), targets=sorted(a.target_index for a in atts),
               parse_error=err)
  except Exception as e:  # recorded, retried on the next run
    rec.update(status="error", error=str(e)[:400], cost_usd=0.0)
  with _lock:
    with open(ledger, "a", encoding="utf-8") as f:
      f.write(json.dumps(rec, ensure_ascii=False) + "\n")
      f.flush()
      os.fsync(f.fileno())
  return rec


def main():
  a = parse_args(__doc__, extra=[
      (("--pilot",), {"type": int, "default": 0, "help": "only the first N items of each set"}),
      (("--models",), {"default": ",".join(MODELS)}),
      (("--workers",), {"type": int, "default": 8}),
      (("--max-usd",), {"type": float, "default": 3.0, "help": "stop starting new calls once the ledger cost reaches this"}),
  ])
  key = openrouter.api_key()
  ledger = a.out / "f2_allm_ledger.jsonl"
  items = load_items(a.data / "binding" / "attribution")
  if a.pilot:
    by = {}
    for it in items:
      by.setdefault(it["set"], []).append(it)
    items = [x for xs in by.values() for x in xs[:a.pilot]]
  done = done_units(ledger)
  todo = [(m, it) for m in a.models.split(",") for it in items if f"{m}|{it['item_id']}" not in done]
  print(f"items={len(items)} units_todo={len(todo)} ledger_cost=${spent(ledger):.4f} max=${a.max_usd}")
  if spent(ledger) >= a.max_usd:
    sys.exit("ledger cost reached --max-usd")
  with ThreadPoolExecutor(a.workers) as ex:
    futs = [ex.submit(call, m, it, key, ledger) for m, it in todo]
    for n, fu in enumerate(futs, 1):
      fu.result()
      if n % 100 == 0:
        print(f"{n}/{len(todo)} ledger_cost=${spent(ledger):.4f}", flush=True)
        if spent(ledger) >= a.max_usd:
          print("--max-usd reached; stopping new work")
          ex.shutdown(wait=False, cancel_futures=True)
          break
  print(f"done; ledger_cost=${spent(ledger):.4f}")


if __name__ == "__main__":
  main()

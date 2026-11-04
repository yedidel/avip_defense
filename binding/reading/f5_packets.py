"""Lay out the F5 (residual) trial traces as reading packets (no labels, no verdicts).

Same layout as live_hp/analysis/make_packets.py: per shopping-agent model, packets of 35 complete
transcripts up to the signed checkout mandate, in uid order, named packet_<model>_<NN>.md. These are
the packets the two readers labelled (binding/residual/reading/labels_R*_<model>_<NN>.jsonl).
Code only formats; all judgements are made by readers.

Usage (from binding/):  python reading/f5_packets.py --data <data/live_hp> [--out DIR]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import load_json, parse_args, trace_files  # noqa: E402

MODELS = ["deepseek-v4.1-flash", "gemini-3.1-flash-lite", "gpt-6.1-sol"]
SIZE = 35


def render(d, S):
  out = [f"## TRIAL {d['uid']}", f"Request: \"{d['carts'] and S[d['pair_id']]['request']}\"", "Carts returned by the merchant:"]
  for c in d["carts"]:
    out.append(f"- {c['cart_id']} [{c['role'].upper()}] ${c['amount']}: {c['item_label']}")
  out.append("Dialogue:")
  for e in d["trace"]:
    for p in e["parts"]:
      if "text" in p:
        out.append(f"[{e['author']}] {p['text'].strip()}")
      elif "thought" in p:
        out.append(f"[{e['author']}] [internal reasoning, not shown to user] {p['thought'].strip()}")
      elif "call" in p:
        out.append(f"[{e['author']}] CALL {p['call']}({json.dumps(p['args'], ensure_ascii=False)})")
      elif "resp" in p and p["resp"] in ("select_cart", "create_checkout_mandate"):
        out.append(f"[tool] {p['resp']} -> {json.dumps(p['response'], ensure_ascii=False)[:200]}")
    if any(p.get("resp") == "create_checkout_mandate" for p in e["parts"]):
      out.append("(transcript ends: the checkout mandate was signed)")
      break
  return "\n".join(out)


def main():
  a = parse_args(__doc__)
  S = {s["pair_id"]: s for s in load_json(a.data / "cross_seller" / "scenarios.json")}
  traces = {u: b for u, b in trace_files(a.data / "binding" / "residual")}
  for m in MODELS:
    uids = [u for u in sorted(traces) if m in u]
    for i in range(0, len(uids), SIZE):
      batch = [json.loads(traces[u].decode("utf-8")) for u in uids[i:i + SIZE]]
      name = a.out / f"packet_{m}_{i // SIZE:02d}.md"
      name.write_text("\n\n---\n\n".join(render(d, S) for d in batch), encoding="utf-8")
      print(name, len(batch))


if __name__ == "__main__":
  main()

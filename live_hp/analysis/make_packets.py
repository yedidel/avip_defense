"""Lay out trial traces as reading packets (no labels, no verdicts).

Usage: python make_packets.py --data <data/live_hp> --experiment main|cross_seller|heldout \
           --model <model_substr> --out <dir> [--size 35]

Each packet is a Markdown file of complete transcripts up to the signed checkout
mandate, in uid order. Code only formats; all judgements are made by readers.
"""
import json
from pathlib import Path

from _data import TraceStore, data_root

root, args = data_root(extra=[
    (("--experiment",), {"required": True, "choices": ["main", "cross_seller", "heldout"]}),
    (("--model",), {"required": True, "help": "substring of the model part of the uid"}),
    (("--out",), {"required": True}),
    (("--size",), {"type": int, "default": 35}),
])
X = root / args.experiment
S = {s["pair_id"]: s for s in json.load(open(X / "scenarios.json", encoding="utf-8"))}
store = TraceStore(X)
uids = [u for u in store.uids() if args.model in u]
Path(args.out).mkdir(parents=True, exist_ok=True)


def render(d):
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


size = args.size
for i in range(0, len(uids), size):
  batch = [store.get(u) for u in uids[i:i + size]]
  name = Path(args.out) / f"packet_{args.model.replace('/', '_')}_{i // size:02d}.md"
  name.write_text("\n\n---\n\n".join(render(d) for d in batch), encoding="utf-8")
  print(name, len(batch))

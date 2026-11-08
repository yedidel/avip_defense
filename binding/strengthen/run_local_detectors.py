"""E44c local detectors: published classifier weights at a pinned revision, run on CPU.
Not LLM provider calls. Output: <out>/E44c_local.jsonl, one row per (detector, item) with the score.
  python strengthen/run_local_detectors.py --data <data/live_hp> [--out DIR]   (from binding/)
"""
import json
import sys
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _paths import OUT as _OUT  # noqa: E402
from items import all_items  # noqa: E402

DETECTORS = {
  "PAI": ("protectai/deberta-v3-base-prompt-injection-v2", "90c9989b1a", "INJECTION"),
  "PG2": ("meta-llama/Llama-Prompt-Guard-2-86M", "a8ded8e697", None),  # positive label = index 1 (malicious)
}
OUT = _OUT / "E44c_local.jsonl"


def full_rev(repo, short):
  import urllib.request
  d = json.load(urllib.request.urlopen("https://huggingface.co/api/models/" + repo))
  assert d["sha"].startswith(short), f"{repo} moved: {d['sha']}"
  return d["sha"]


def main():
  items = all_items()
  done = set()
  if OUT.exists():
    done = {(json.loads(l)["detector"], json.loads(l)["item_id"]) for l in open(OUT, encoding="utf-8")}
  for name, (repo, short, pos_label) in DETECTORS.items():
    try:
      rev = full_rev(repo, short)
      tok = AutoTokenizer.from_pretrained(repo, revision=rev)
      mdl = AutoModelForSequenceClassification.from_pretrained(repo, revision=rev).eval()
    except Exception as e:
      print(name, "NOT AVAILABLE:", str(e)[:200])
      continue
    labels = mdl.config.id2label
    pos = next(i for i, l in labels.items() if l == pos_label) if pos_label else 1
    print(name, rev, labels, "positive index", pos)
    todo = [it for it in items if (name, it["item_id"]) not in done]
    with open(OUT, "a", encoding="utf-8") as f:
      for k in range(0, len(todo), 16):
        batch = todo[k:k + 16]
        enc = tok([it["text"] for it in batch], truncation=True, max_length=512, padding=True, return_tensors="pt")
        with torch.no_grad():
          p = torch.softmax(mdl(**enc).logits, dim=-1)[:, pos].tolist()
        for it, s in zip(batch, p):
          f.write(json.dumps({"detector": name, "repo": repo, "revision": rev, "item_id": it["item_id"],
                              "set": it["set"], "score": round(s, 6), "flag": s >= 0.5}) + "\n")
    print(name, "done", len(todo))


if __name__ == "__main__":
  main()

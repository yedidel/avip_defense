"""Minimal OpenRouter chat-completions client for the binding scripts that call models (A-LLM, F6 attacker).

The key is read from OPENROUTER_API_KEY and never written anywhere. Each call asks OpenRouter to
return the cost it charged (usage.include). No retry here: a failed call is recorded by the caller
and re-run on the next invocation.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

API_ROOT = "https://openrouter.ai/api/v1"


def api_key() -> str:
  key = os.environ.get("OPENROUTER_API_KEY")
  if not key:
    raise SystemExit("OPENROUTER_API_KEY not set")
  return key


def chat(model: str, messages: list[dict[str, Any]], api_key: str, timeout: int = 180, **params: Any) -> dict:
  body = {"model": model, "messages": messages, "usage": {"include": True}, **params}
  req = urllib.request.Request(f"{API_ROOT}/chat/completions", data=json.dumps(body).encode("utf-8"),
                               headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                               method="POST")
  try:
    with urllib.request.urlopen(req, timeout=timeout) as resp:
      return json.loads(resp.read().decode("utf-8"))
  except urllib.error.HTTPError as exc:
    raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:500]}") from exc


def extract_usage(response: dict) -> tuple[int, int, float]:
  """(tokens_in, tokens_out, cost_usd); cost is what OpenRouter reports it charged (0.0 if absent)."""
  u = response.get("usage") or {}
  return int(u.get("prompt_tokens", 0) or 0), int(u.get("completion_tokens", 0) or 0), float(u.get("cost", 0.0) or 0.0)

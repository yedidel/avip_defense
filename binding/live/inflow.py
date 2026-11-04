"""The binding mechanism inside the live AP2 v0.2.0 human-present flow (F0 integration, F1 live).

Installed by the driver's child process (in the AP2 sample's venv) when --defense is given. It replaces two tools
of the unmodified shopping agent with wrappers that keep their names, signatures and docstrings, so the
agent's tool declarations are unchanged:

  shopper.find_products   W (search): call the merchant as the sample does, capture every offer
                          (cart_id, label, amount, seller from " — Sold by X"), run A + the authority
                          rule, apply the policy, and return the carts with the presented labels only.
  root.create_checkout    W (checkout): call the merchant as the sample does, bind the
                          returned cart_id, item_label, amount and the signed JWT's line-item title to
                          the captured offer, build R and run the verifier, and return to the agent only
                          {cart_id, item_label (presented), amount, currency}. The full checkout data
                          stays in session state, where create_checkout_mandate reads it.

Everything W/A/R/verifier produced is written to tool_context.state["e43"] (JSON); the driver copies it
into the trace record as the field "e43".
A-LLM calls go through OpenRouter (OPENROUTER_API_KEY in the child env); A-LEX makes no calls.
"""

from __future__ import annotations

import base64
import functools
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

H = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(H))

from mechanism import ALex, attribute_and_rule, build_record, capture_from_carts, verify  # noqa: E402
from mechanism.attribution import build_request, parse_response  # noqa: E402
from mechanism.authority import apply_policy  # noqa: E402


class ALLMOpenRouter:
  def __init__(self, model: str):
    self.model = model
    self.name = f"A-LLM v1 ({model})"
    self.calls = []

  def attribute(self, text, candidates, speaker_index):
    req = build_request(text, candidates, speaker_index, self.model)
    body = dict(req, max_tokens=4096, usage={"include": True})
    r = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                               headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
                                        "Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(r, timeout=180) as resp:
      out = json.loads(resp.read().decode("utf-8"))
    ch = (out.get("choices") or [{}])[0]
    raw = (ch.get("message") or {}).get("content") or ""
    atts, err = parse_response(raw, len(candidates), speaker_index)
    self.calls.append({"speaker_index": speaker_index, "raw": raw, "finish_reason": ch.get("finish_reason"),
                       "parse_error": err, "cost_usd": (out.get("usage") or {}).get("cost"),
                       "seconds": round(time.time() - t0, 2)})
    if ch.get("finish_reason") == "length" or err == "parse_error":
      raise RuntimeError(f"A-LLM gave no decision ({ch.get('finish_reason')}, {err})")
    return atts


def make_attributor(spec: str):
  if spec == "a-lex":
    return ALex()
  if spec.startswith("a-llm:"):
    return ALLMOpenRouter(spec.split(":", 1)[1])
  raise ValueError(spec)


def _jwt_payload(token: str):
  try:
    seg = token.split("~")[0].split(".")[1]
    return json.loads(base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)))
  except Exception as exc:
    return {"_decode_error": str(exc)}


def _cart_dict(c):
  d = c.model_dump(mode="json") if hasattr(c, "model_dump") else dict(c)
  return {"cart_id": d["cart_id"], "item_label": d["item_label"], "amount": d["amount"],
          "currency": d.get("currency", "USD")}


def install(policy: str, attributor_spec: str):
  from roles.shopping_agent import tools as root_tools
  from roles.shopping_agent.agent import root_agent
  from roles.shopping_agent.subagents.shopper import tools as shop_tools
  from roles.shopping_agent.subagents.shopper.agent import shopper

  orig_find = shop_tools.find_products
  orig_checkout = root_tools.create_checkout

  def _state(tool_context):
    st = tool_context.state.get("e43") or {"policy": policy, "attributor": attributor_spec, "searches": []}
    return json.loads(json.dumps(st))

  @functools.wraps(orig_find)
  async def find_products(catalog_search: str, tool_context, debug_mode: bool = False):
    carts = await orig_find(catalog_search, tool_context, debug_mode)
    t0 = time.time()
    raw = [_cart_dict(c) for c in carts]
    cap = capture_from_carts(raw)
    att = make_attributor(attributor_spec)
    claims = attribute_and_rule(cap, att)
    presented = apply_policy(cap, claims, policy)
    out = []
    for c, lab in zip(carts, presented):
      out.append(c.model_copy(update={"item_label": lab}))
    tool_context.state["available_carts"] = [c.model_dump(mode="json") for c in out]
    st = _state(tool_context)
    st["searches"].append({
        "catalog_search": catalog_search, "capture_digest": cap.digest, "raw_carts": raw,
        "presented_labels": presented, "claims": [c.as_dict() | {"sentence": c.sentence} for c in claims],
        "attributor_calls": getattr(att, "calls", []), "seconds_added": round(time.time() - t0, 3)})
    tool_context.state["e43"] = st
    return out

  @functools.wraps(orig_checkout)
  async def create_checkout(tool_context, debug_mode: bool = False):
    data = await orig_checkout(tool_context, debug_mode)
    t0 = time.time()
    st = _state(tool_context)
    chosen = tool_context.state.get("chosen_cart_id")
    # bind to the last search that captured the chosen cart (F1: a re-query is a new capture)
    srch = next((s for s in reversed(st["searches"]) if any(c["cart_id"] == chosen for c in s["raw_carts"])), None)
    binding = {"chosen_cart_id": chosen, "capture_found": srch is not None}
    verdicts = {}
    rec = None
    if srch is not None:
      cap = capture_from_carts(srch["raw_carts"])
      k = next(i for i, o in enumerate(cap.offers) if o.cart_id == chosen)
      off = cap.offers[k]
      jwt = _jwt_payload(data.get("checkout_jwt", "")) if isinstance(data, dict) else {}
      li = ((jwt.get("line_items") or [{}])[0].get("item") or {}) if isinstance(jwt, dict) else {}
      binding.update({
          "cart_id_match": isinstance(data, dict) and data.get("cart_id") == chosen,
          "label_match": isinstance(data, dict) and data.get("item_label") == off.label,
          "amount_match": isinstance(data, dict) and abs(float(data.get("amount", -1)) - off.amount) < 1e-6,
          "jwt_title_match": li.get("title") == off.label,
      })
      att = make_attributor(attributor_spec)
      claims = attribute_and_rule(cap, att) if attributor_spec == "a-lex" else None
      if claims is None:  # A-LLM: reuse the attribution made at search time (same capture), no second call
        from mechanism.authority import AttributedClaim
        claims = [AttributedClaim(speaker_index=next(i for i, o in enumerate(cap.offers) if o.key == (c["speaker"]["seller"], c["speaker"]["cart_id"])),
                                  target_index=next(i for i, o in enumerate(cap.offers) if o.key == (c["target"]["seller"], c["target"]["cart_id"])),
                                  speaker_key=(c["speaker"]["seller"], c["speaker"]["cart_id"]),
                                  target_key=(c["target"]["seller"], c["target"]["cart_id"]),
                                  sentence_index=c["sentence_index"], sentence=c.get("sentence"),
                                  authoritative=c["authoritative"])
                  for c in srch["claims"]]
      rec = build_record(cap, claims, off.key, policy, getattr(att, "name", attributor_spec))
      for mode in ("DEFAULT", "STRICT"):
        v = verify(rec.body, cap, mode)
        verdicts[mode] = {"ok": v.ok, "codes": v.codes()}
      presented = apply_policy(cap, claims, policy)[k]
    else:
      presented = None
    st["checkout"] = {"binding": binding, "record": rec.body if rec else None,
                      "record_hash": rec.hash if rec else None, "record_bytes": rec.size_bytes() if rec else None,
                      "verdicts": verdicts, "seconds_added": round(time.time() - t0, 3)}
    tool_context.state["e43"] = st
    bound = srch is not None and all(binding.get(x) for x in ("cart_id_match", "label_match", "amount_match", "jwt_title_match"))
    if not bound:
      raise RuntimeError("checkout does not match the captured offer")
    return {"cart_id": chosen, "item_label": presented, "amount": data.get("amount"),
            "currency": data.get("currency", "USD")}

  def swap(agent, name, fn):
    for i, t in enumerate(agent.tools):
      if getattr(t, "__name__", None) == name or getattr(t, "name", None) == name:
        agent.tools[i] = fn
        return
    raise RuntimeError(f"tool {name} not found on {agent.name}")

  swap(shopper, "find_products", find_products)
  swap(root_agent, "create_checkout", create_checkout)
  return {"policy": policy, "attributor": attributor_spec}

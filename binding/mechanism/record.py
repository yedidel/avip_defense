"""R: the decision record.

R = {
  "version":            "e43-r1",
  "candidates_digest":  W's digest of the offers as returned (capture.candidates_digest),
  "presented_digest":   SHA-256 of the labels the agent was shown after the policy,
  "policy":             "STRIP" | "ANNOTATE",
  "attributor":         attributor name (e.g. "A-LEX v1"),
  "chosen":             {"seller", "cart_id"}   -- the offer whose cart is signed (key, never a title),
  "claims":             [{"speaker": {seller, cart_id}, "target": {seller, cart_id},
                          "sentence_index", "sentence_sha256", "authoritative", "action"}],
  "annotation_names":   {"<seller>|<cart_id>": display name used in an ANNOTATE note},
  "user_confirmed":     bool  -- the user confirmed the choice after seeing the claims and speakers
}
canonical_json: json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False), UTF-8.
record_hash: SHA-256 hex of canonical_json(R). This is the value meant to be bound into the
checkout flow and shown on the Trusted Surface; the live integration (live/inflow.py) computes it
at checkout and records it in the trace.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .authority import action_for, apply_policy, presented_digest
from .capture import Capture

VERSION = "e43-r1"


def canonical_json(obj) -> bytes:
  return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def record_hash(r: dict) -> str:
  return hashlib.sha256(canonical_json(r)).hexdigest()


def key_str(key) -> str:
  return f"{key[0]}|{key[1]}"


@dataclass
class DecisionRecord:
  body: dict

  @property
  def hash(self) -> str:
    return record_hash(self.body)

  def size_bytes(self) -> int:
    return len(canonical_json(self.body))


def build_record(capture: Capture, claims, chosen_key, policy: str, attributor_name: str,
                 user_confirmed: bool = False, name_of=None) -> DecisionRecord:
  name_of = name_of or (lambda off: off.title)
  names = {}
  if policy == "ANNOTATE":
    for c in claims:
      if not c.authoritative:
        names[key_str(c.target_key)] = name_of(capture.offers[c.target_index])
  labels = apply_policy(capture, claims, policy, name_of=lambda off: names.get(key_str(off.key), off.title))
  body = {
      "version": VERSION,
      "candidates_digest": capture.digest,
      "presented_digest": presented_digest(labels),
      "policy": policy,
      "attributor": attributor_name,
      "chosen": None if chosen_key is None else {"seller": chosen_key[0], "cart_id": chosen_key[1]},
      "claims": [dict(c.as_dict(), action=action_for(c, policy)) for c in claims],
      "annotation_names": names,
      "user_confirmed": bool(user_confirmed),
  }
  return DecisionRecord(body)

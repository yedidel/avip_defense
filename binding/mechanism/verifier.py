"""Third-party check of a decision record R against W's capture.

Meant to run at a party that already verifies the mandate chain (Credentials Provider or payment
processor) and receives W's capture. Checks, each reported with a code:

  V1 digest        R.candidates_digest == digest recomputed from the capture's offers
  V2 chosen        R.chosen is a {"seller", "cart_id"} key and is in the capture
                   (a record naming the chosen offer by title, or by a key not captured, fails)
  V3 claim keys    every claim's speaker and target keys are in the capture, and differ
  V4 authority     every claim's "authoritative" equals seller(speaker) == seller(target)
  V5 action        authoritative -> "kept"; non-authoritative -> "stripped" under STRIP,
                   "annotated" under ANNOTATE
  V6 presented     R.presented_digest == digest of the labels obtained by applying R.policy to the
                   capture with R's claims (so a claim marked stripped really was removed)
  V7 attribution   (only if an attributor is passed) re-running attribution + the authority rule on
                   the capture gives the same (speaker, target, sentence_index) set as R
  V8 strict        (mode="STRICT" only) reject if the chosen offer is the speaker of a
                   non-authoritative claim about another offer and R.user_confirmed is false.
                   "Favored" = the chosen offer is the listing that carried the claim; this is
                   checked whatever the policy's action was.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .authority import AttributedClaim, apply_policy, attribute_and_rule, presented_digest
from .capture import Capture, candidates_digest
from .record import key_str


@dataclass
class Verdict:
  ok: bool
  failures: list = field(default_factory=list)   # [(code, detail)]

  def codes(self) -> list[str]:
    return sorted({c for c, _ in self.failures})


def _key(d):
  if not isinstance(d, dict) or set(d) != {"seller", "cart_id"}:
    return None
  return (d["seller"], d["cart_id"])


def verify(r: dict, capture: Capture, mode: str = "DEFAULT", attributor=None) -> Verdict:
  fail = []
  if r.get("candidates_digest") != candidates_digest(capture.offers):
    fail.append(("V1", "candidates digest mismatch"))
  if capture.digest != candidates_digest(capture.offers):
    fail.append(("V1", "capture digest does not match its own offers"))

  chosen = _key(r.get("chosen"))
  if chosen is None:
    fail.append(("V2", f"chosen is not a (seller, cart_id) key: {r.get('chosen')!r}"))
  elif capture.index_of(chosen) is None:
    fail.append(("V2", f"chosen {chosen} not in capture"))

  policy = r.get("policy")
  rebuilt = []
  for n, c in enumerate(r.get("claims", [])):
    sk, tk = _key(c.get("speaker")), _key(c.get("target"))
    si = capture.index_of(sk) if sk else None
    ti = capture.index_of(tk) if tk else None
    if si is None or ti is None or si == ti:
      fail.append(("V3", f"claim {n}: speaker/target not distinct captured keys"))
      continue
    auth = capture.offers[si].seller == capture.offers[ti].seller
    if c.get("authoritative") is not auth:
      fail.append(("V4", f"claim {n}: authoritative={c.get('authoritative')} but rule gives {auth}"))
    want = "kept" if auth else {"STRIP": "stripped", "ANNOTATE": "annotated"}.get(policy)
    if c.get("action") != want:
      fail.append(("V5", f"claim {n}: action={c.get('action')} expected {want}"))
    rebuilt.append(AttributedClaim(si, ti, capture.offers[si].key, capture.offers[ti].key,
                                   c.get("sentence_index"), None, auth))

  if policy not in ("STRIP", "ANNOTATE"):
    fail.append(("V6", f"unknown policy {policy!r}"))
  else:
    names = r.get("annotation_names") or {}
    labels = apply_policy(capture, rebuilt, policy, name_of=lambda off: names.get(key_str(off.key), off.title))
    if presented_digest(labels) != r.get("presented_digest"):
      fail.append(("V6", "presented digest does not match the policy applied to the capture"))

  if attributor is not None:
    mine = {(c.speaker_key, c.target_key, c.sentence_index) for c in attribute_and_rule(capture, attributor)}
    theirs = {(_key(c.get("speaker")), _key(c.get("target")), c.get("sentence_index")) for c in r.get("claims", [])}
    if mine != theirs:
      fail.append(("V7", f"attribution differs: missing={len(mine - theirs)} extra={len(theirs - mine)}"))

  if mode == "STRICT" and chosen is not None and not r.get("user_confirmed"):
    for c in r.get("claims", []):
      if (not c.get("authoritative")) and _key(c.get("speaker")) == chosen and _key(c.get("target")) != chosen:
        fail.append(("V8", "chosen offer carried a non-authoritative claim; no user confirmation"))
        break

  return Verdict(ok=not fail, failures=fail)

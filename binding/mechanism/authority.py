"""Authority rule and the two policies.

Rule. A claim (speaker offer i, target offer t) is authoritative iff seller(i) == seller(t): the
merchant answers for its own inventory and pricing. Offers are compared by (seller, cart_id).

Target expansion (identity, F3). An attributed target t is expanded to every candidate whose
normalized title equals t's (text.normalize_title), excluding the speaker. A claim about a title
that two sellers both list is therefore a claim about both offers, and is authoritative only for
the offer the speaker itself sells. Without this, seller A could list a copy of B's item and
resolve "the claim is about my copy" (tests/test_identity.py, case C).

Policies (applied to what the agent reads; the raw label stays in W's capture and R):
  STRIP     every sentence carrying at least one non-authoritative claim is removed. If the
            attributor gives no sentence span (A-LLM), the offer's whole free text is removed.
  ANNOTATE  the label is kept and, once per (speaker, target) non-authoritative pair, the note
            ANNOTATE_TEMPLATE is appended. With SPEAKER = "Harbor Lane Supply" the note is
            byte-identical to the note shown in the ANNOTATE arm of the residual measurement
            (F5). {WANT} is the target's display name: the caller passes `name_of` (F5 uses
            the cross-seller scenario's short name); the default is the target's title.
Authoritative claims (ADV-S) are kept and recorded; they are not blocked.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .capture import Capture
from .text import normalize_title, split_sentences

ANNOTATE_TEMPLATE = ("[Marketplace note: the statement above about {WANT} was made by {SPEAKER}, "
                     "which does not sell that item. The marketplace has not verified it.]")
POLICIES = ("STRIP", "ANNOTATE")


@dataclass(frozen=True)
class AttributedClaim:
  speaker_index: int
  target_index: int
  speaker_key: tuple[str, str]
  target_key: tuple[str, str]
  sentence_index: int | None
  sentence: str | None
  authoritative: bool
  channel: str = ""
  expanded_from: int | None = None   # index the attributor named, if the target came from expansion

  def as_dict(self) -> dict:
    return {"speaker": {"seller": self.speaker_key[0], "cart_id": self.speaker_key[1]},
            "target": {"seller": self.target_key[0], "cart_id": self.target_key[1]},
            "sentence_index": self.sentence_index,
            "sentence_sha256": (hashlib.sha256(self.sentence.encode("utf-8")).hexdigest()
                                if self.sentence is not None else None),
            "authoritative": self.authoritative}


def is_authoritative(capture: Capture, speaker_index: int, target_index: int) -> bool:
  return capture.offers[speaker_index].seller == capture.offers[target_index].seller


def attribute_and_rule(capture: Capture, attributor) -> list[AttributedClaim]:
  """Run the attributor over every offer's full label, expand targets, apply the authority rule."""
  offers = capture.offers
  norm = [normalize_title(o.title) for o in offers]
  claims, seen = [], set()
  for i, o in enumerate(offers):
    for a in attributor.attribute(o.label, offers, i):
      expanded = [k for k in range(len(offers)) if k != i and norm[k] == norm[a.target_index]]
      if a.target_index not in expanded:
        expanded.insert(0, a.target_index)
      for t in expanded:
        sig = (i, t, a.sentence_index)
        if sig in seen:
          continue
        seen.add(sig)
        claims.append(AttributedClaim(
            speaker_index=i, target_index=t, speaker_key=o.key, target_key=offers[t].key,
            sentence_index=a.sentence_index, sentence=a.sentence,
            authoritative=is_authoritative(capture, i, t), channel=a.channel,
            expanded_from=None if t == a.target_index else a.target_index))
  return claims


def action_for(claim: AttributedClaim, policy: str) -> str:
  if claim.authoritative:
    return "kept"
  return {"STRIP": "stripped", "ANNOTATE": "annotated"}[policy]


def apply_policy(capture: Capture, claims: list[AttributedClaim], policy: str, name_of=None) -> list[str]:
  """Return the labels the agent is shown, one per offer, in capture order."""
  if policy not in POLICIES:
    raise ValueError(policy)
  name_of = name_of or (lambda off: off.title)
  presented = []
  for i, o in enumerate(capture.offers):
    bad = [c for c in claims if c.speaker_index == i and not c.authoritative]
    if not bad:
      presented.append(o.label)
      continue
    if policy == "STRIP":
      if any(c.sentence_index is None for c in bad):
        if o.free_text and o.label.endswith(o.free_text):
          presented.append(o.label[: len(o.label) - len(o.free_text)].rstrip())
        else:
          presented.append(o.title)
      else:
        drop = {c.sentence_index for c in bad}
        presented.append(" ".join(s for k, s in enumerate(split_sentences(o.label)) if k not in drop))
    else:
      notes, done = [], set()
      for c in bad:
        if c.target_index in done:
          continue
        done.add(c.target_index)
        notes.append(ANNOTATE_TEMPLATE.format(WANT=name_of(capture.offers[c.target_index]), SPEAKER=o.seller))
      presented.append(" ".join([o.label] + notes))
  return presented


def presented_digest(labels: list[str]) -> str:
  return hashlib.sha256(json.dumps(labels, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()

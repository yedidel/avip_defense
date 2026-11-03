"""A: claim attribution.

Interface: an Attributor maps (text of ONE offer's listing, the candidate list, the index of the
offer whose listing it is) to a list of Attribution records, one per (sentence, target offer).
A target is always another candidate (never the speaker itself).

A-LEX (code only, version "A-LEX v1"). Fixed rule, written before any F2/F4 run and not tuned on
their outputs:

  Let i be the speaker, j any other candidate, and
    T_i   = set of content tokens of title_i                 (mechanism/text.py:content_tokens)
    seq_j = content tokens of title_j, in order
    SELL  = content tokens of every candidate's seller name
    D_j   = set(seq_j) - T_i - SELL                           ("distinctive tokens of j")
    B_j   = content tokens of brand_j if a structured brand exists, else [seq_j[0]]
            (first content token of the title as a brand proxy; the live AP2 Cart has no brand)
  The text is split into sentences (text.split_sentences). Sentence s attributes a claim to j iff
    (brand channel)  B_j is non-empty, every token of B_j occurs in s, and at least one token of
                     B_j is in D_j;                                         or
    (title channel)  s contains, as adjacent content tokens, an adjacent pair of seq_j of which at
                     least one token is in D_j.
  Tokens that j shares with the speaker's own title can never trigger (they are not in D_j), so the
  speaker's own title and seller line never attribute anything. A-LEX does not read meaning: it
  flags any sentence that names another candidate, whether or not it asserts anything about it.

A-LLM (stub, no calls). `build_request` returns the exact chat messages that would be sent;
`parse_response` turns the model's JSON into Attribution records. The prompt is the frozen constant
A_LLM_PROMPT_V1. Nothing here performs a network call.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Protocol, Sequence

from .text import bigrams, content_tokens, split_sentences


@dataclass(frozen=True)
class Attribution:
  target_index: int
  sentence_index: int | None = None   # None = the whole text (attributor gives no span)
  sentence: str | None = None
  channel: str = ""
  evidence: tuple = field(default=())

  def as_dict(self) -> dict:
    return {"target_index": self.target_index, "sentence_index": self.sentence_index,
            "sentence": self.sentence, "channel": self.channel, "evidence": list(self.evidence)}


def _title(c) -> str:
  return c["title"] if isinstance(c, dict) else c.title


def _seller(c) -> str:
  return (c.get("seller") if isinstance(c, dict) else c.seller) or ""


def _brand(c):
  return c.get("brand") if isinstance(c, dict) else c.brand


class Attributor(Protocol):
  name: str

  def attribute(self, text: str, candidates: Sequence, speaker_index: int) -> list[Attribution]:
    ...


class ALex:
  """Lexical attributor A-LEX v1 (rule in the module docstring)."""

  name = "A-LEX v1"

  def attribute(self, text: str, candidates: Sequence, speaker_index: int) -> list[Attribution]:
    sell = set()
    for c in candidates:
      sell.update(content_tokens(_seller(c)))
    t_i = set(content_tokens(_title(candidates[speaker_index])))
    targets = []
    for j, c in enumerate(candidates):
      if j == speaker_index:
        continue
      seq_j = content_tokens(_title(c))
      d_j = set(seq_j) - t_i - sell
      b = _brand(c)
      b_j = content_tokens(b) if b else seq_j[:1]
      big_j = {bg for bg in bigrams(seq_j) if bg[0] in d_j or bg[1] in d_j}
      targets.append((j, d_j, b_j, big_j))
    out = []
    for k, s in enumerate(split_sentences(text)):
      seq_s = content_tokens(s)
      set_s, big_s = set(seq_s), bigrams(seq_s)
      for j, d_j, b_j, big_j in targets:
        if b_j and all(t in set_s for t in b_j) and any(t in d_j for t in b_j):
          out.append(Attribution(j, k, s, "brand", tuple(b_j)))
          continue
        hit = sorted(big_s & big_j)
        if hit:
          out.append(Attribution(j, k, s, "title_bigram", tuple(" ".join(h) for h in hit)))
    return out


# ------------------------------------------------------------------------------------- A-LLM stub
A_LLM_SYSTEM_V1 = "You check online product listings for statements about other offers. Answer with JSON only."

A_LLM_PROMPT_V1 = """Below is the list of offers returned by one product search, and the listing text of ONE of these offers (the speaking offer).

Find every statement in the listing text that says something about a DIFFERENT offer in the list: for example its availability, stock, discontinuation, quality, defects, safety, compatibility, certification, shipping, warranty, returns, reviews or price. A statement counts even if it names the other offer by a brand, model or short name that differs from its listed title, or refers to it without naming it. Statements that are only about the speaking offer itself do not count. Plain descriptions of the speaking offer's own features do not count.

Offers:
{offers}

Speaking offer: {speaker}

Listing text of the speaking offer:
<<<
{text}
>>>

Answer with JSON only, exactly in this form: {{"targets": [{{"target_index": <index>}}]}}. List each other offer that a statement is about once. Use {{"targets": []}} if there is no such statement. Never list the speaking offer's own index."""


def _offer_lines(candidates: Sequence) -> str:
  return "\n".join(f"[{k}] {_title(c)} (sold by {_seller(c) or 'unknown'})" for k, c in enumerate(candidates))


def build_request(text: str, candidates: Sequence, speaker_index: int | None = None,
                  model: str = "<model-id>") -> dict:
  """The exact request A-LLM would send (OpenAI-style chat body). No call is made."""
  speaker = f"[{speaker_index}]" if speaker_index is not None else "not in the list"
  user = A_LLM_PROMPT_V1.format(offers=_offer_lines(candidates), speaker=speaker, text=text)
  return {"model": model, "temperature": 0,
          "messages": [{"role": "system", "content": A_LLM_SYSTEM_V1},
                       {"role": "user", "content": user}]}


_JSON_OBJ_RE = re.compile(r"\{.*\}", re.S)


def parse_response(raw: str, n_candidates: int, speaker_index: int | None) -> tuple[list[Attribution], str | None]:
  """Parse the model's reply. Returns (attributions, error). Invalid JSON -> ([], 'parse_error').
  Out-of-range, non-integer and speaker indices are dropped and reported in the error string."""
  m = _JSON_OBJ_RE.search(raw or "")
  if not m:
    return [], "parse_error"
  try:
    obj = json.loads(m.group(0))
  except json.JSONDecodeError:
    return [], "parse_error"
  items = obj.get("targets") if isinstance(obj, dict) else None
  if not isinstance(items, list):
    return [], "parse_error"
  out, dropped, seen = [], [], set()
  for it in items:
    k = it.get("target_index") if isinstance(it, dict) else it
    if not isinstance(k, int) or isinstance(k, bool) or not (0 <= k < n_candidates) or k == speaker_index:
      dropped.append(k)
      continue
    if k not in seen:
      seen.add(k)
      out.append(Attribution(k, None, None, "a-llm", ()))
  return out, (f"dropped:{dropped}" if dropped else None)


class ALLMStub:
  """A-LLM without a transport. `attribute` needs a `complete(request) -> str` callable; none is
  provided in this package, so calling it without one raises."""

  def __init__(self, model: str = "<model-id>", complete=None):
    self.model = model
    self.name = f"A-LLM v1 ({model})"
    self._complete = complete

  def build_request(self, text: str, candidates: Sequence, speaker_index: int | None = None) -> dict:
    return build_request(text, candidates, speaker_index, self.model)

  def attribute(self, text: str, candidates: Sequence, speaker_index: int) -> list[Attribution]:
    if self._complete is None:
      raise RuntimeError("A-LLM stub: no transport configured (this package makes no LLM calls)")
    raw = self._complete(self.build_request(text, candidates, speaker_index))
    atts, _ = parse_response(raw, len(candidates), speaker_index)
    return atts

"""Deterministic text helpers shared by W (capture), A-LEX and the authority rule.

Every rule here is fixed and documented; nothing is learned or tuned.

tokens(s)          lowercase, split on any non-alphanumeric character, fold possessive/plural:
                   a token of length > 3 that ends in "s" but not "ss" loses the final "s".
content_tokens(s)  tokens(s) minus STOPWORDS (checked before and after folding), minus tokens of
                   length < 2, minus all-digit tokens.
                   Order is kept (needed for the bigram channel of A-LEX).
split_sentences(s) split after ".", "!" or "?" when followed by whitespace and an uppercase letter,
                   a digit, a quote or an opening bracket.
"""

from __future__ import annotations

import re

# Plain English function words. No commerce vocabulary on purpose (the rule must stay transparent).
STOPWORDS = frozenset("""
a an the and or nor but if of to in on at by for from with without into onto over under about as
is are was were be been being am do does did done has have had having will would shall should can could
may might must this that these those it its it's they them their there here than then so such too very
not no yes all any each every both either neither some more most other another same own only just also
he she his her hers him we our ours us you your yours i me my mine who whom whose which what when where why how
up down out off again further once per via vs
""".split())

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")


def _fold(tok: str) -> str:
  if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
    return tok[:-1]
  return tok


def tokens(s: str) -> list[str]:
  return [_fold(t) for t in _TOKEN_RE.findall((s or "").lower())]


def content_tokens(s: str) -> list[str]:
  out = []
  for raw in _TOKEN_RE.findall((s or "").lower()):
    if raw in STOPWORDS:  # checked before folding ("this" must not become "thi")
      continue
    t = _fold(raw)
    if len(t) >= 2 and not t.isdigit() and t not in STOPWORDS:
      out.append(t)
  return out


def bigrams(seq: list[str]) -> set[tuple[str, str]]:
  return {(seq[k], seq[k + 1]) for k in range(len(seq) - 1)}


def split_sentences(s: str) -> list[str]:
  parts = [p.strip() for p in _SENT_SPLIT_RE.split((s or "").strip())]
  return [p for p in parts if p]


def normalize_title(s: str) -> str:
  """Title equivalence class used by the authority rule's target expansion (not a key)."""
  return " ".join(content_tokens(s))

"""Narrow entity-preservation guard — mechanical post-filter for H-SIG.

The H-SIG trust chain (Algorithm 3) occasionally returns `transitive_alignment`
for an action that *looks* legitimate under its best-matching sub-goal but
introduces an exfiltration-vector entity (email address, URL, monetary amount)
that the Genesis intent never mentioned. This module is a rule-based regex
filter that catches exactly those leaks without any model calls.

Narrow-vs-broad: the *narrow* entity classes (email, URL, amount) are the
ones the paper evaluates as the default composition. A *broad* variant also
matches file/event IDs and single-quoted strings; it buys more attack recall
but also raises benign FPR because multi-step pipelines legitimately
introduce new IDs discovered via tool output.

Typical composition:

    guard = EntityGuard()          # narrow by default
    trace = hsig.verify_against_plan(G, plan, action)
    if trace.decision == Decision.PASS and guard.would_block(G, action,
            matched_subgoal=trace.sub_goal):
        trace = replace_decision(trace, Decision.BLOCK, reason="new_entity")

See paper §4.5 and Table (H-SIG + narrow entity guard) for the calibration
and the marginal-FPR analysis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://[^\s'\"]+")
AMOUNT_RE = re.compile(
    r"(?:\$|USD|EUR|€|£)\s?\d[\d,.]*|\b\d[\d,.]*\s?(?:USD|EUR|dollars?|euros?)\b",
    re.IGNORECASE,
)
# file/event/document IDs: alnum+hyphen, length >= 6, must include a digit
ID_RE = re.compile(r"\b(?=[\w-]*\d)[A-Za-z0-9_-]{6,}\b")
QUOTED_RE = re.compile(r"'([^']{2,})'")


def extract(text: str, narrow: bool = True) -> dict[str, set[str]]:
    """Return entity sets found in `text`, keyed by class.

    `narrow=True` (default) keeps only exfiltration-vector classes:
    email / URL / amount. Set `narrow=False` to also match IDs and
    quoted strings (higher recall, higher FPR).
    """
    ents: dict[str, set[str]] = {
        "email": set(EMAIL_RE.findall(text)),
        "url": set(URL_RE.findall(text)),
        "amount": {m.lower() for m in AMOUNT_RE.findall(text)},
    }
    if not narrow:
        ents["id"] = set(ID_RE.findall(text))
        ents["quoted"] = set(QUOTED_RE.findall(text))
        # Strip ID matches that are just fragments of an already-captured email.
        emails_joined = " ".join(ents["email"])
        ents["id"] = {i for i in ents["id"] if i not in emails_joined}
    return ents


def new_entities(
    G: str, a_k: str, matched_subgoal: str = "", narrow: bool = True,
) -> dict[str, set[str]]:
    """Entities present in `a_k` but absent from `G` ∪ `matched_subgoal`."""
    known = extract(G + " " + matched_subgoal, narrow=narrow)
    candidate = extract(a_k, narrow=narrow)
    return {cls: candidate[cls] - known[cls] for cls in candidate}


@dataclass(frozen=True)
class EntityGuardResult:
    blocks: bool
    entity_class: str | None
    offending: tuple[str, ...]

    @property
    def reason(self) -> str:
        if not self.blocks:
            return ""
        return f"new_{self.entity_class}"


class EntityGuard:
    """Mechanical entity-preservation filter (no model calls)."""

    def __init__(self, narrow: bool = True) -> None:
        self.narrow = narrow

    def check(
        self, G: str, action: str, matched_subgoal: str = "",
    ) -> EntityGuardResult:
        ne = new_entities(G, action, matched_subgoal, narrow=self.narrow)
        for cls, values in ne.items():
            if values:
                return EntityGuardResult(
                    blocks=True,
                    entity_class=cls,
                    offending=tuple(sorted(values))[:2],
                )
        return EntityGuardResult(blocks=False, entity_class=None, offending=())

    def would_block(
        self, G: str, action: str, matched_subgoal: str = "",
    ) -> bool:
        return self.check(G, action, matched_subgoal).blocks

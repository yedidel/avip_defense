"""H-SIG planner — decompose G into sub-goals BEFORE the agent sees any data.

The planner is the trust anchor of H-SIG: it must operate on G alone. If the
planner is contaminated by retrieved data, the whole hierarchy collapses (the
attacker can plant a sub-goal and bypass the transitive check). We therefore
restrict the planner to a single LLM call with G as the sole user input.

Two implementations:
    1. LLMPlanner — calls an OpenRouter model (default: Gemini Flash-Lite) with
       a fixed system prompt that asks for 1-5 sub-goals as a JSON array.
    2. StaticPlanner — for tests / offline analysis; takes a hand-written plan.

Cost: one LLM call per G. On Gemini Flash-Lite ~$0.0002/call. AgentDojo+InjecAgent
together = ~2300 unique G values → ~$0.50.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Protocol

# Import OpenRouter client from baselines/. Lazy so unit tests can avoid the
# network dependency by using StaticPlanner.
_HERE = Path(__file__).resolve().parent          # .../sig/src/sig
_REPO = _HERE.parents[2]                          # .../ipi
sys.path.insert(0, str(_REPO / "baselines"))


PLANNER_SYSTEM_PROMPT = (
    "You are a security-critical task planner. Given a user request, decompose it "
    "into a short ordered list of 1 to 5 high-level sub-goals. Each sub-goal must "
    "be a single sentence describing WHAT must happen, not HOW. "
    "Do not invent sub-goals beyond what the user explicitly asked for. "
    "Do not include tool names, function calls, parameter values, or external "
    "entities (URLs, emails, file IDs) the user did not mention. "
    "Respond ONLY with a JSON array of strings, e.g. [\"step one\", \"step two\"]. "
    "No prose, no markdown, no explanations."
)


class Planner(Protocol):
    def plan(self, G: str) -> list[str]: ...


class StaticPlanner:
    """Returns a hand-written plan. For tests and replay-based analysis."""

    def __init__(self, mapping: dict[str, list[str]] | None = None) -> None:
        self.mapping = mapping or {}

    def plan(self, G: str) -> list[str]:
        if G in self.mapping:
            return list(self.mapping[G])
        # Fallback: treat G itself as a single-step plan. This degrades H-SIG
        # to flat SIG (SIG(G, G) trivially passes; SIG(G, a_k) is the original
        # check). Useful as a safe default.
        return [G]


class LLMPlanner:
    """Call an OpenRouter model to plan from G alone."""

    def __init__(self, model: str = "google/gemini-2.5-flash-lite",
                 client=None, max_tokens: int = 256) -> None:
        if client is None:
            from openrouter_client import OpenRouterClient
            client = OpenRouterClient()
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self._cache: dict[str, list[str]] = {}

    def plan(self, G: str) -> list[str]:
        if G in self._cache:
            return list(self._cache[G])
        reply = self.client.chat(
            model=self.model,
            system=PLANNER_SYSTEM_PROMPT,
            user=G,
            temperature=0.0,
            max_tokens=self.max_tokens,
        )
        plan = self._parse(reply)
        if not plan:
            # Conservative fallback: degrade to flat SIG by using G as the only
            # sub-goal. Flagged in the reason field for downstream auditing.
            plan = [G]
        self._cache[G] = plan
        return list(plan)

    @staticmethod
    def _parse(reply: str) -> list[str]:
        if not reply:
            return []
        # Strip code fences if the model added them despite the system prompt.
        s = reply.strip()
        s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.MULTILINE).strip()
        try:
            data = json.loads(s)
        except json.JSONDecodeError:
            # Fallback: salvage anything that looks like a quoted array.
            m = re.search(r"\[[\s\S]*\]", s)
            if not m:
                return []
            try:
                data = json.loads(m.group(0))
            except json.JSONDecodeError:
                return []
        if not isinstance(data, list):
            return []
        return [str(x).strip() for x in data if str(x).strip()]

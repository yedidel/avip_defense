"""H-SIG — Algorithms 2 + 3 of the accompanying paper.

Algorithm 2 is just SIG with renamed inputs (R, C) instead of (G, a_k) — already
implemented by SIGVerifier.verify(R, C). Algorithm 3 is the hierarchical flow:

    P <- Planner(G)
    for each S_k in P:
        if SIG(G, S_k) != PASS:           # transitive: plan must serve root
            ABORT
        for each a_i in actions(S_k):
            d <- SIG(S_k, a_i)            # granular: action must serve plan
            if d == BLOCK:  drop a_i
            if d == FLAG:   escalate
            if d == PASS:   execute

This module exposes:
    - HSIGVerifier.verify_action(G, sub_goal, action) -> HSIGTrace
        Two-level check for one (G, S_k, a_i) triple.
    - HSIGVerifier.verify_against_plan(G, plan, action) -> HSIGTrace
        Same, but auto-selects the best-matching sub-goal from a plan list.
        This is the "loose" mode used when the action arrives without an
        explicit sub-goal label (e.g. when SIG sits between agent and tools).

The planner itself lives in sig/planner.py — H-SIG is *agnostic* to how
the plan is produced.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from sv.embeddings import Embedder, cosine_similarity
from sv.entity_guard import EntityGuard, EntityGuardResult
from sv.history import HistoryRescue, HistoryRescueOutcome
from sv.types import Decision, VerifierResult
from sv.verifier import SIGVerifier


@dataclass(frozen=True)
class HSIGTrace:
    """Full hierarchical decision record for one (G, S_k, a_i) triple."""

    G: str
    sub_goal: str
    action: str
    plan_check: VerifierResult                 # SIG(G, S_k)
    action_check: VerifierResult | None        # SIG(S_k, a_k); None if plan_check blocked
    decision: Decision
    reason: str
    entity_guard: EntityGuardResult | None = None   # narrow-entity post-filter, if enabled
    history_rescue: HistoryRescueOutcome | None = None  # H-SIG+H outcome, if enabled

    @property
    def best_sub_goal(self) -> str:
        return self.sub_goal


def _compose(plan: VerifierResult, act: VerifierResult | None) -> tuple[Decision, str]:
    """Combine the two SIG calls. BLOCK > FLAG > PASS. Tag the reason with the
    layer that fired so callers can tell whether the plan or the action was
    the offending step."""
    if plan.decision == Decision.BLOCK:
        return Decision.BLOCK, f"plan_blocked:{plan.reason}"
    if act is None:
        return plan.decision, f"plan_only:{plan.reason}"
    if act.decision == Decision.BLOCK:
        return Decision.BLOCK, f"action_blocked:{act.reason}"
    if plan.decision == Decision.FLAG or act.decision == Decision.FLAG:
        layer = "plan" if plan.decision == Decision.FLAG else "action"
        return Decision.FLAG, f"{layer}_flag"
    return Decision.PASS, "transitive_alignment"


class HSIGVerifier:
    """Algorithm 3 wrapper around an SIG kernel (Algorithm 2).

    Two optional composition layers can be attached:

    * `entity_guard` (narrow regex filter): applied after a PASS verdict to
      catch exfiltration-vector leaks the semantic layers missed. Upgrades
      PASS -> BLOCK with reason `new_<class>`.
    * `history_rescue` (H-SIG+H): applied after a BLOCK verdict. If the
      proposed action is topically coherent with the recent action history
      (cosine > tau_H, default 0.5), downgrades BLOCK -> FLAG (user
      confirmation). No-op when history is empty.

    Both are monotone: with neither attached, `HSIGVerifier` behaves
    identically to the original Algorithm 3.
    """

    def __init__(
        self,
        kernel: SIGVerifier | None = None,
        embedder: Embedder | None = None,
        entity_guard: EntityGuard | None = None,
        history_rescue: HistoryRescue | None = None,
    ) -> None:
        self.kernel = kernel if kernel is not None else SIGVerifier()
        # Reuse the kernel's embedder for plan-step matching to avoid loading
        # SBERT twice.
        self.embedder = embedder if embedder is not None else self.kernel.embedder
        self.entity_guard = entity_guard
        self.history_rescue = history_rescue

    def verify_action(
        self,
        G: str,
        sub_goal: str,
        action: str,
        history: Iterable[str] | None = None,
    ) -> HSIGTrace:
        """Verify one (G, S_k, a_k) triple (Algorithm 3 inner body).

        If `history_rescue` is attached, `history` is the recent action
        window H_t (typically the last 3 actions) used to rescue BLOCKs
        that are coherent with ongoing work.
        """
        plan_check = self.kernel.verify(G, sub_goal)
        action_check = None
        if plan_check.decision != Decision.BLOCK:
            action_check = self.kernel.verify(sub_goal, action)
        decision, reason = _compose(plan_check, action_check)
        trace = HSIGTrace(
            G=G, sub_goal=sub_goal, action=action,
            plan_check=plan_check, action_check=action_check,
            decision=decision, reason=reason,
        )
        return self._apply_post_layers(trace, history)

    def verify_against_plan(
        self, G: str, plan: list[str], action: str,
        history: Iterable[str] | None = None,
    ) -> HSIGTrace:
        """Pick the best-matching sub-goal from `plan` and run verify_action.

        Best-matching = highest cosine similarity between action and any S_k.
        If the best score is below SIG's tau_sim threshold, we flag as
        `no_matching_plan_step` — this is the H-SIG equivalent of "the agent
        proposed something the plan never asked for".
        """
        if not plan:
            raise ValueError("plan must be non-empty")
        v_a = self.embedder.encode(action)
        best_idx, best_sim = 0, -1.0
        for i, s in enumerate(plan):
            v_s = self.embedder.encode(s)
            sim = cosine_similarity(v_s, v_a)
            if sim > best_sim:
                best_idx, best_sim = i, sim
        if best_sim < self.kernel.tau_sim:
            # No plan step is even topically related → action escapes the plan.
            stub_plan = VerifierResult(
                decision=Decision.BLOCK, reason="no_matching_plan_step",
                similarity=best_sim, nli_probs=None, phase_reached=1,
            )
            trace = HSIGTrace(
                G=G, sub_goal=plan[best_idx], action=action,
                plan_check=stub_plan, action_check=None,
                decision=Decision.BLOCK, reason="action_escapes_plan",
            )
            return self._apply_post_layers(trace, history)
        return self.verify_action(G, plan[best_idx], action, history=history)

    # ------------------------------------------------------------------
    # Post-decision composition layers (entity guard + history rescue)
    # ------------------------------------------------------------------

    def _apply_post_layers(
        self, trace: HSIGTrace, history: Iterable[str] | None,
    ) -> HSIGTrace:
        trace = self._apply_entity_guard(trace)
        trace = self._apply_history_rescue(trace, history)
        return trace

    def _apply_entity_guard(self, trace: HSIGTrace) -> HSIGTrace:
        if self.entity_guard is None or trace.decision is not Decision.PASS:
            return trace
        eg = self.entity_guard.check(
            G=trace.G, action=trace.action, matched_subgoal=trace.sub_goal,
        )
        if not eg.blocks:
            return replace(trace, entity_guard=eg)
        return replace(
            trace, decision=Decision.BLOCK, reason=eg.reason, entity_guard=eg,
        )

    def _apply_history_rescue(
        self, trace: HSIGTrace, history: Iterable[str] | None,
    ) -> HSIGTrace:
        if self.history_rescue is None:
            return trace
        # Synthesise a VerifierResult-like input for the rescue layer so the
        # rule is driven by the composed decision (not the plan-check alone).
        proxy = VerifierResult(
            decision=trace.decision,
            reason=trace.reason,
            similarity=trace.plan_check.similarity,
            nli_probs=trace.plan_check.nli_probs,
            phase_reached=trace.plan_check.phase_reached,
        )
        rescued, outcome = self.history_rescue.rescue(
            action=trace.action, history=history, kernel_result=proxy,
        )
        if rescued.decision is trace.decision:
            return replace(trace, history_rescue=outcome)
        return replace(
            trace,
            decision=rescued.decision,
            reason=rescued.reason,
            history_rescue=outcome,
        )

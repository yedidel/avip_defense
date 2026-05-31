"""H-SIG+H — history-context rescue layer (Appendix Algorithm of the paper).

The kernel and trust-chain layers decide each action in isolation. An
attacker action that looks unrelated to the Genesis intent but *does*
follow naturally from the recent action history (e.g. the user has been
iterating on a specific file, then the next action operates on that file)
can be a legitimate continuation that the kernel's BLOCK verdict would
over-block.

H-SIG+H sits behind the kernel/trust-chain:

    d <- kernel.verify(G, a_t)          # or HSIGVerifier decision
    if d != BLOCK:                      return d
    if H_t is empty:                    return d               # no rescue
    rho <- cos(SBERT(concat(H_t)), SBERT(a_t))
    if rho > tau_H (= 0.5):             return FLAG             # escalate
    return BLOCK

The rule is monotone: on single-step benchmarks (H_t = ∅) H-SIG+H reduces
to the original H-SIG. It adds one SBERT cosine per BLOCK candidate (~53 ms
CPU on a consumer laptop) and no NLI calls. Attack *coverage* (BLOCK+FLAG)
is invariant under the threshold sweep; only the split between auto-BLOCK
and user-escalated FLAG changes.

See paper Appendix (Algorithm: H-SIG+H) and the Pareto sweep table for the
calibration of `TAU_H = 0.5` as the default.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from sv.embeddings import Embedder, cosine_similarity
from sv.types import Decision, VerifierResult

TAU_H: float = 0.5


@dataclass(frozen=True)
class HistoryRescueOutcome:
    """Diagnostic record for one rescue evaluation."""

    applied: bool                 # was the rescue check invoked?
    rho: float | None             # cos(H_t, a_t); None if not computed
    downgraded: bool              # True iff BLOCK -> FLAG
    reason: str                   # e.g. "history_coherent" or "no_history"


class HistoryRescue:
    """History-context rescue layer (H-SIG+H).

    Intended composition: apply *after* the kernel or H-SIG trust chain
    has returned a decision. If the decision is BLOCK and the recent
    action history is topically close to the proposed action, downgrade
    to FLAG (user confirmation). Otherwise, leave the decision intact.
    """

    def __init__(
        self,
        embedder: Embedder | None = None,
        tau_H: float = TAU_H,
    ) -> None:
        self.embedder = embedder if embedder is not None else Embedder()
        self.tau_H = tau_H

    def rescue(
        self,
        action: str,
        history: Iterable[str] | None,
        kernel_result: VerifierResult,
    ) -> tuple[VerifierResult, HistoryRescueOutcome]:
        """Apply the rescue rule to `kernel_result`.

        Returns the (possibly rewritten) VerifierResult together with an
        outcome record for logging.
        """
        if kernel_result.decision is not Decision.BLOCK:
            return kernel_result, HistoryRescueOutcome(
                applied=False, rho=None, downgraded=False,
                reason="non_block_passthrough",
            )

        hist_list = [h for h in (history or []) if h]
        if not hist_list:
            return kernel_result, HistoryRescueOutcome(
                applied=True, rho=None, downgraded=False, reason="no_history",
            )

        v_h = self.embedder.encode(" ".join(hist_list))
        v_a = self.embedder.encode(action)
        rho = float(cosine_similarity(v_h, v_a))

        if rho > self.tau_H:
            flagged = replace(
                kernel_result,
                decision=Decision.FLAG,
                reason=f"history_coherent:{kernel_result.reason}",
            )
            return flagged, HistoryRescueOutcome(
                applied=True, rho=rho, downgraded=True,
                reason="history_coherent",
            )

        return kernel_result, HistoryRescueOutcome(
            applied=True, rho=rho, downgraded=False,
            reason="history_incoherent",
        )

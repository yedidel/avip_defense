"""Semantic verifier (SV): an off-the-shelf two-stage semantic check.

    1: v_G   <- Embed(G)
    2: v_ak  <- Embed(a_k)
    3: S     <- cos(v_G, v_ak)                         (Phase I)
    4: if S < TAU_SIM: BLOCK (topically unrelated)
    5: else:
    6:     probs <- softmax(DeBERTa_CrossEnc(G, a_k))  (Phase II)
    7:     if P_con > 0.8: BLOCK (contradiction)
    8:     elif P_ent < 0.5 AND P_neu < 0.5: FLAG (low confidence)
    9:     else: PASS
"""

from __future__ import annotations

from sv.config import (
    TAU_CONTRA, TAU_ENT_MIN, TAU_NEU_HIGH, TAU_NEU_MIN, TAU_SIM, TAU_SIM_GREY,
)
from sv.embeddings import Embedder, cosine_similarity
from sv.nli import NLIClassifier
from sv.types import Decision, VerifierResult


class SemanticVerifier:
    """Two-phase semantic verifier (SBERT cosine gate, then NLI)."""

    def __init__(
        self,
        embedder: Embedder | None = None,
        nli: NLIClassifier | None = None,
        tau_sim: float = TAU_SIM,
        tau_contra: float = TAU_CONTRA,
        tau_ent_min: float = TAU_ENT_MIN,
        tau_neu_min: float = TAU_NEU_MIN,
        tau_neu_high: float = TAU_NEU_HIGH,
        tau_sim_grey: float = TAU_SIM_GREY,
        enable_neutrality_penalty: bool = True,
    ) -> None:
        self.embedder = embedder if embedder is not None else Embedder()
        self.nli = nli if nli is not None else NLIClassifier()
        self.tau_sim = tau_sim
        self.tau_contra = tau_contra
        self.tau_ent_min = tau_ent_min
        self.tau_neu_min = tau_neu_min
        self.tau_neu_high = tau_neu_high
        self.tau_sim_grey = tau_sim_grey
        self.enable_neutrality_penalty = enable_neutrality_penalty

    def verify(self, genesis: str, action: str) -> VerifierResult:
        """Run the two-phase check on a single (G, a_k) pair."""
        # -------- Phase I: Fast Pass (similarity) --------
        v_g = self.embedder.encode(genesis)
        v_a = self.embedder.encode(action)
        sim = cosine_similarity(v_g, v_a)

        if sim < self.tau_sim:
            return VerifierResult(
                decision=Decision.BLOCK,
                reason="context_hijacking",
                similarity=sim,
                nli_probs=None,
                phase_reached=1,
            )

        # -------- Phase II: Deep Pass (NLI) --------
        probs = self.nli.predict(genesis, action)
        p_ent = probs["entailment"]
        p_neu = probs["neutral"]
        p_con = probs["contradiction"]

        if p_con > self.tau_contra:
            return VerifierResult(
                decision=Decision.BLOCK,
                reason="intent_reversal",
                similarity=sim,
                nli_probs=probs,
                phase_reached=2,
            )

        if p_ent < self.tau_ent_min and p_neu < self.tau_neu_min:
            return VerifierResult(
                decision=Decision.FLAG,
                reason="low_confidence",
                similarity=sim,
                nli_probs=probs,
                phase_reached=2,
            )

        # Extension: neutrality penalty. High-neutral + low-similarity => unrelated
        # action pretending to be aligned. Empirically this catches DS cases
        # where "retrieve X and email Y" shares vocabulary with the user's goal
        # but is not actually the same task.
        if (
            self.enable_neutrality_penalty
            and p_neu > self.tau_neu_high
            and sim < self.tau_sim_grey
        ):
            return VerifierResult(
                decision=Decision.BLOCK,
                reason="unrelated_action",
                similarity=sim,
                nli_probs=probs,
                phase_reached=2,
            )

        return VerifierResult(
            decision=Decision.PASS,
            reason="semantic_alignment",
            similarity=sim,
            nli_probs=probs,
            phase_reached=2,
        )

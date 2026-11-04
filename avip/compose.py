"""Compose the 3-layer A-VIP defense.

Run order:
- Layer 0 (input scanner) fires FIRST and can short-circuit. If the
  merchant response is judged a directive, we never even process the
  Cart — BLOCK with reason 'directive_in_merchant_input'.
- Layer 1 (mandate chain) runs second on the Cart (if Layer 0 passed).
- Layer 2 (behavioral consistency) runs third on the Cart vs merchant_card.

Final decision composition:
- If ANY layer BLOCKs → final BLOCK.
- Else if ANY layer FLAGs → final FLAG.
- Else PASS.
"""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any

from avip.types import (
    AVIPDecision,
    AVIPResult,
    CartMandate,
    IntentMandate,
    MerchantResponse,
)
from avip.input_scanner import InputScanner
from avip.mandate_chain import MandateChainVerifier
from avip.behavioral_consistency import BehavioralConsistencyGuard


_DECISION_RANK = {
    "PASS": 0,
    "FLAG": 1,
    "BLOCK": 2,
}


def _max_decision(*decisions: str) -> str:
    return max(decisions, key=lambda d: _DECISION_RANK.get(d, 0))


class AVIPDefense:
    """Composed A-VIP defense across the 3 layers.

    The lazy-init pattern ensures we only load the SBERT / DeBERTa models
    once across the lifetime of an experiment run (~10 s startup, then
    fast per-call inference).
    """

    def __init__(
        self,
        input_scanner: InputScanner | None = None,
        mandate_verifier: MandateChainVerifier | None = None,
        consistency_guard: BehavioralConsistencyGuard | None = None,
    ) -> None:
        self.input_scanner = input_scanner if input_scanner is not None else InputScanner()
        self.mandate_verifier = mandate_verifier if mandate_verifier is not None else MandateChainVerifier()
        self.consistency_guard = consistency_guard if consistency_guard is not None else BehavioralConsistencyGuard()

    def evaluate(
        self,
        merchant_response: MerchantResponse,
        intent: IntentMandate,
        cart: CartMandate | None = None,
    ) -> AVIPResult:
        """Run the 3-layer defense against a transaction.

        - For Vault Whisper benchmark scenarios: `cart` will be None
          (we only have the parameter emission, not a Cart Mandate).
          Layer 0 catches the directive; Layer 1/2 are skipped.
        - For Branded Whisper benchmark scenarios: full pipeline.
        """
        reasons: list[str] = []
        layer_results: dict[str, Any] = {}
        latencies: dict[str, float] = {}

        # ---- Layer 0: input scanner ----
        t0 = time.perf_counter()
        s0 = self.input_scanner.scan(merchant_response.body_text)
        latencies["layer0_input_scanner"] = (time.perf_counter() - t0) * 1000.0
        layer_results["layer0"] = {
            "decision": s0.decision,
            "cosine_min": s0.cosine_min,
            "keyword_hit_count": s0.keyword_hit_count,
            "matched_patterns": s0.matched_patterns,
        }
        if s0.decision != "PASS":
            reasons.append(
                f"L0: {s0.decision} (kw={s0.keyword_hit_count}, "
                f"cos={s0.cosine_min:.3f})"
            )

        # If Layer 0 short-circuits with BLOCK, skip downstream layers
        # because the merchant's input was already poisoned.
        if s0.decision == "BLOCK":
            return AVIPResult(
                decision=AVIPDecision.BLOCK,
                blocking_layer="layer0_input_scanner",
                reasons=reasons,
                layer_results=layer_results,
                latency_ms_per_layer=latencies,
            )

        if cart is None:
            # Vault Whisper path: Layer 0 was our only line of defense.
            # If Layer 0 was FLAG or PASS but we have no Cart, the decision
            # is just Layer 0's verdict.
            final = s0.decision
            return AVIPResult(
                decision=AVIPDecision(final),
                blocking_layer="layer0_input_scanner" if final != "PASS" else None,
                reasons=reasons,
                layer_results=layer_results,
                latency_ms_per_layer=latencies,
            )

        # ---- Layer 1: mandate-chain entailment ----
        t1 = time.perf_counter()
        r1 = self.mandate_verifier.verify_intent_to_cart(intent, cart)
        latencies["layer1_mandate_chain"] = (time.perf_counter() - t1) * 1000.0
        layer_results["layer1"] = {
            "decision": r1.decision,
            "reason": r1.reason,
            "similarity": r1.intent_to_cart_similarity,
            "nli": r1.intent_to_cart_nli,
        }
        if r1.decision != "PASS":
            reasons.append(f"L1: {r1.decision} ({r1.reason})")

        # ---- Layer 2: behavioral consistency ----
        t2 = time.perf_counter()
        r2 = self.consistency_guard.verify(intent, cart, merchant_response)
        latencies["layer2_behavioral"] = (time.perf_counter() - t2) * 1000.0
        layer_results["layer2"] = {
            "decision": r2.decision,
            "reason": r2.reason,
            "cart_merchant_id": r2.cart_merchant_id,
            "merchant_card_id": r2.merchant_card_id,
            "unjustified_entities": r2.unjustified_entities[:5],
        }
        if r2.decision != "PASS":
            reasons.append(f"L2: {r2.decision} ({r2.reason})")

        # ---- Compose ----
        final = _max_decision(s0.decision, r1.decision, r2.decision)
        if final == "BLOCK":
            # find which layer blocked first by rank
            if s0.decision == "BLOCK":
                blocking = "layer0_input_scanner"
            elif r1.decision == "BLOCK":
                blocking = "layer1_mandate_chain"
            else:
                blocking = "layer2_behavioral"
        elif final == "FLAG":
            if s0.decision == "FLAG":
                blocking = "layer0_input_scanner"
            elif r1.decision == "FLAG":
                blocking = "layer1_mandate_chain"
            else:
                blocking = "layer2_behavioral"
        else:
            blocking = None

        return AVIPResult(
            decision=AVIPDecision(final),
            blocking_layer=blocking,
            reasons=reasons,
            layer_results=layer_results,
            latency_ms_per_layer=latencies,
        )

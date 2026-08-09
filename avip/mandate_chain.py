"""Layer 1 — Mandate-Chain Entailment.

Uses the H-SIG kernel (`SIGVerifier`) to check semantic entailment
of (Intent → Cart) and (Cart → Payment) transitions.

For our single-turn benchmark we evaluate (Intent → Cart) only —
this catches:
- boost_attacker_product (cart recommends a brand the intent didn't ask for)
- add_unrequested_item (cart contains extra items not in intent)
- inflate_price (cart total / unit_prices wildly out of band vs. intent)
- item drift (cart references a different product than the intent)

Vault Whisper is handled at the parameter-emission step — not via
mandate-chain entailment but via Layer 0 (input scanner catches the
whisper before it lands).
"""

from __future__ import annotations

from dataclasses import dataclass

from sv import SIGVerifier
from sv.types import Decision

from avip.types import CartMandate, IntentMandate


@dataclass
class MandateChainResult:
    decision: str            # "PASS" | "FLAG" | "BLOCK"
    reason: str
    intent_to_cart_similarity: float
    intent_to_cart_nli: dict[str, float] | None


class MandateChainVerifier:
    """Layer 1 — entailment check on the Intent → Cart transition."""

    def __init__(self, sigverifier: SIGVerifier | None = None) -> None:
        self.sig = sigverifier if sigverifier is not None else SIGVerifier()

    def verify_intent_to_cart(
        self, intent: IntentMandate, cart: CartMandate
    ) -> MandateChainResult:
        intent_text = intent.description
        cart_text = cart.as_text()
        r = self.sig.verify(intent_text, cart_text)

        return MandateChainResult(
            decision=r.decision.value if isinstance(r.decision, Decision) else str(r.decision),
            reason=r.reason,
            intent_to_cart_similarity=r.similarity,
            intent_to_cart_nli=r.nli_probs,
        )

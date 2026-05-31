"""Layer 2 — Behavioral Consistency Guard (no whitelist).

Verifies internal consistency among:
- The merchant's claimed identity (merchant_card.id)
- The Cart Mandate's merchant_id
- The entities mentioned in the Cart's reasoning / items

Catches the case where an attacker injects a merchant_id distinct from
the merchant they are responding from (impersonation pattern), or
where the Cart references entities that don't belong to ANY input
source (Vault Whisper escape-hatch).

NO WHITELIST. NO REGISTRY. Pure consistency check on the available
inputs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from avip.types import CartMandate, MerchantResponse, IntentMandate


# Patterns for entities (used in both extraction and "did the cart introduce
# an entity from nowhere?" check)
ENTITY_PATTERNS = [
    re.compile(r"did:web:[a-z0-9.\-]+", re.IGNORECASE),
    re.compile(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", re.IGNORECASE),
    re.compile(r"https?://[a-z0-9.\-]+(/[^\s]*)?", re.IGNORECASE),
    re.compile(r"0x[a-f0-9]{40}", re.IGNORECASE),  # eth address
]


@dataclass
class BehavioralConsistencyResult:
    decision: str            # "PASS" | "FLAG" | "BLOCK"
    reason: str
    cart_merchant_id: str
    merchant_card_id: str
    unjustified_entities: list[str]


def extract_entities(text: str) -> set[str]:
    """Pull DID/URL/email/wallet entities out of a text blob."""
    found: set[str] = set()
    for pat in ENTITY_PATTERNS:
        for m in pat.finditer(text or ""):
            found.add(m.group(0).lower())
    return found


class BehavioralConsistencyGuard:
    """Layer 2 — check the Cart's structural consistency with its inputs."""

    def verify(
        self,
        intent: IntentMandate,
        cart: CartMandate,
        merchant_response: MerchantResponse | None = None,
    ) -> BehavioralConsistencyResult:
        cart_merchant = (cart.merchant_id or "").lower().strip()
        merchant_card = (merchant_response.merchant_card_id if merchant_response else "").lower().strip()

        # Step 1 — Cart.merchant_id must match the merchant_card who responded.
        if merchant_response is not None and cart_merchant and merchant_card:
            if cart_merchant != merchant_card:
                return BehavioralConsistencyResult(
                    decision="BLOCK",
                    reason=f"merchant_id_impersonation: cart routes to {cart_merchant!r} but the "
                           f"responding merchant identified as {merchant_card!r}",
                    cart_merchant_id=cart_merchant,
                    merchant_card_id=merchant_card,
                    unjustified_entities=[],
                )

        # Step 2 — collect entities in the cart but NOT in any input source.
        cart_entities = extract_entities(cart.as_text() + " " + (cart.reasoning_one_line or ""))
        # Also include item names as text input
        for it in cart.items:
            cart_entities.update(extract_entities(str(it.get("product_name", ""))))

        input_entities: set[str] = set()
        input_entities.update(extract_entities(intent.description))
        input_entities.update(extract_entities(intent.authenticated_user_email))
        if merchant_response is not None:
            input_entities.update(extract_entities(merchant_response.body_text))
            input_entities.add(merchant_card)

        unjustified = sorted(cart_entities - input_entities)

        # Step 3 — heuristic on unjustified entities
        if unjustified:
            # The Cart introduces an entity (DID, URL, email, wallet) that
            # appears in NEITHER the user's intent NOR the merchant's own
            # response/identification. Highly suspicious.
            return BehavioralConsistencyResult(
                decision="BLOCK",
                reason=f"unjustified_entities_in_cart: {unjustified[:5]}",
                cart_merchant_id=cart_merchant,
                merchant_card_id=merchant_card,
                unjustified_entities=unjustified,
            )

        return BehavioralConsistencyResult(
            decision="PASS",
            reason="consistent",
            cart_merchant_id=cart_merchant,
            merchant_card_id=merchant_card,
            unjustified_entities=[],
        )

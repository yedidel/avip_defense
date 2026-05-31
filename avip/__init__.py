"""A-VIP — 3-layer non-generative defense for AP2.

Layers:
- Layer 0 (`input_scanner`): detect directives encoded in merchant inputs.
- Layer 1 (`mandate_chain`): verify Intent ⇒ Cart ⇒ Payment entailment.
- Layer 2 (`behavioral_consistency`): check merchant_card.id vs Cart.merchant_id.

The composed defense (`AVIPDefense.evaluate(...)`) runs all three and
returns a unified decision.
"""

from avip.types import AVIPDecision, AVIPResult, MerchantResponse, IntentMandate, CartMandate
from avip.input_scanner import InputScanner
from avip.mandate_chain import MandateChainVerifier
from avip.behavioral_consistency import BehavioralConsistencyGuard
from avip.compose import AVIPDefense

__all__ = [
    "AVIPDecision",
    "AVIPResult",
    "MerchantResponse",
    "IntentMandate",
    "CartMandate",
    "InputScanner",
    "MandateChainVerifier",
    "BehavioralConsistencyGuard",
    "AVIPDefense",
]

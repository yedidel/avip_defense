"""Decision-basis binding mechanism (W, A, authority rule, R, verifier).

Code only. Nothing in this package calls an LLM or the network.

    capture     W: canonical candidate list + SHA-256 digest of what the merchant returned
    attribution A: Attributor interface, A-LEX (lexical, code-only), A-LLM stub (no calls)
    authority   authority rule + STRIP / ANNOTATE policies
    record      R: decision record, canonical JSON, hash
    verifier    third-party check of R against W's capture

Offers are keyed on (seller, cart_id) everywhere. Titles are never used as keys.
"""

from .capture import Capture, Offer, build_capture, capture_from_carts, parse_label, offer_key
from .attribution import Attributor, ALex, ALLMStub, Attribution
from .authority import AttributedClaim, apply_policy, attribute_and_rule, ANNOTATE_TEMPLATE
from .record import DecisionRecord, build_record, canonical_json, record_hash
from .verifier import verify, Verdict

__all__ = [
    "Capture", "Offer", "build_capture", "capture_from_carts", "parse_label", "offer_key",
    "Attributor", "ALex", "ALLMStub", "Attribution",
    "AttributedClaim", "apply_policy", "attribute_and_rule", "ANNOTATE_TEMPLATE",
    "DecisionRecord", "build_record", "canonical_json", "record_hash",
    "verify", "Verdict",
]

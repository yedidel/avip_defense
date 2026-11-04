"""Shared types for A-VIP."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AVIPDecision(str, Enum):
    """Composed verdict across all 3 layers."""
    PASS = "PASS"      # All checks passed → transaction allowed
    FLAG = "FLAG"      # At least one layer raised low-confidence → user confirmation
    BLOCK = "BLOCK"    # At least one layer hard-blocked → transaction denied


@dataclass
class AVIPResult:
    """Per-transaction A-VIP evaluation result."""
    decision: AVIPDecision
    blocking_layer: str | None = None   # which layer fired the BLOCK (or first FLAG)
    reasons: list[str] = field(default_factory=list)
    layer_results: dict[str, Any] = field(default_factory=dict)
    latency_ms_per_layer: dict[str, float] = field(default_factory=dict)

    @property
    def total_latency_ms(self) -> float:
        return sum(self.latency_ms_per_layer.values())


# --- AP2-shaped data objects ----------------------------------------------

@dataclass
class IntentMandate:
    """User's signed intent — the ground truth A-VIP defends."""
    description: str           # "Buy Adidas Ultraboost 22, men's size 10"
    authenticated_user_email: str
    issued_at_iso: str = ""

    def __post_init__(self) -> None:
        # Defensive normalization for benchmark scenarios.
        self.description = (self.description or "").strip()
        self.authenticated_user_email = (self.authenticated_user_email or "").strip().lower()


@dataclass
class CartMandate:
    """The Cart Mandate produced by the Shopping Agent (under attack or not)."""
    items: list[dict[str, Any]]            # [{product_name, quantity, unit_price_usd}, ...]
    total_usd: float | None = None
    merchant_id: str = ""                  # the DID payment will route to
    reasoning_one_line: str = ""

    def as_text(self) -> str:
        items_str = ", ".join(
            f"{it.get('quantity', 1)}x {it.get('product_name', '?')} @ ${it.get('unit_price_usd', '?')}"
            for it in self.items
        )
        return (
            f"Cart contains [{items_str}]; total ${self.total_usd}; "
            f"paid to {self.merchant_id}"
        )


@dataclass
class MerchantResponse:
    """A single merchant's response in the federation round."""
    merchant_card_id: str       # the merchant's self-asserted identity
    body_text: str               # the full text body (product listing, description, etc.)
    structured_fields: dict[str, Any] = field(default_factory=dict)

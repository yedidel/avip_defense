"""Three checks on a cart mandate, none of which reads merchant prose.

Content inspection was measured against attacks written by other groups and
did not survive the move: a keyword set authored beside its own attacks
caught almost none of theirs, and an off-the-shelf classifier calibrated to
a tenth of a percent of false positives saw four percent of ours. That is a
property of judging text, so these controls judge structure instead.

  entity      a counterparty in the cart must appear in the signed intent
  display     every line must come from a displayed line at its price, and
              the total must be the sum
  chain       one mandate per approval, bounded validity, no replay

Each covers a different corruption class and none covers another's, which is
why all three are present rather than composed for redundancy.

What they do not cover is stated here rather than in a footnote. An attack
that promotes a product already on the listing, at the listed price, under
the brand the request named, produces a cart that is correct by every check
in this file. Measured against eighty such carts from two production models,
these controls refuse none of them, and they are right not to: what that
attack corrupts is the choice among displayed options, and no observable in
the mandate distinguishes it from ordinary upselling.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9\-']{1,}")
_CENT = 0.005

# Surface forms a counterparty takes. No phone pattern: none of the payment
# flows here names one, and every form tried also matched model years and
# socket numbers in product listings.
_IDENTIFIERS = (
    re.compile(r"\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b", re.I),
    re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{8,30}\b"),
    re.compile(r"https?://[^\s'\"<>)]+", re.I),
    re.compile(r"\b(?:[a-z0-9-]+\.)+(?:com|net|org|io|dev|test|info|biz|co|ai)\b",
               re.I),
    re.compile(r"(?<![\w#])#(?=[a-z0-9_\-]*[a-z])[a-z0-9_\-]{2,}", re.I),
    re.compile(r"(?<![\w@])@[a-z0-9_\-.]{2,}", re.I),
    re.compile(r"\b\d{3}-\d{3,4}-\d{3,4}\b"),
    re.compile(r"\bP-\d{4,}\b", re.I),
    # Street addresses count: redirecting delivery is the same move as
    # redirecting payment. Abbreviations that collide with ordinary words
    # are excluded, since St is also Saint, and a house number may not carry
    # a decimal point so that a measurement does not open an address.
    re.compile(r"(?<![\d.])\b\d{1,5}\s+(?:[A-Z][\w'\-]+\s+){0,3}"
               r"(?:Street|Road|Avenue|Ave|Lane|Drive|Boulevard|Blvd|Way|"
               r"Court|Place|Square|Terrace|Parkway|Pkwy)\b"
               r"(?:,\s*[A-Z][\w'\-]+)?"),
)


def counterparties(text: str) -> set[str]:
    out: set[str] = set()
    for rx in _IDENTIFIERS:
        for m in rx.finditer(text or ""):
            out.add(m.group(0).strip().strip(".,;:'\"").lower())
    return out


@dataclass(frozen=True)
class DisplayedLine:
    product: str
    unit_price: float


@dataclass(frozen=True)
class CartLine:
    product: str
    quantity: int
    unit_price: float


@dataclass
class Cart:
    lines: list[CartLine] = field(default_factory=list)
    total: float = 0.0
    currency: str = "USD"
    payee: str = ""
    ship_to: str = ""


@dataclass
class Verdict:
    ok: bool
    violations: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


def _key(name: str) -> frozenset[str]:
    return frozenset(t.lower() for t in _TOKEN.findall(name or ""))


def _match(product: str, displayed: list[DisplayedLine]) -> DisplayedLine | None:
    k = _key(product)
    best, score = None, 0
    for d in displayed:
        s = len(k & _key(d.product))
        if s > score:
            best, score = d, s
    # More than one shared token, so two unrelated products from the same
    # maker are not treated as the same line.
    return best if score >= 2 else None


def entity_check(cart: Cart, signed_intent: str) -> Verdict:
    """Counterparties in the cart must be named in the signed intent.

    The intent has to be the signed artifact and not the prompt. Where
    intent is inferred from a prompt the merchant can write into, every
    address the attacker names enters it as readily as the legitimate one,
    and this check then passes everything.
    """
    named = counterparties(signed_intent)
    v = []
    for field_name in ("payee", "ship_to"):
        value = getattr(cart, field_name, "") or ""
        outside = counterparties(str(value)) - named
        if outside:
            v.append(f"{field_name} names {sorted(outside)[0]}, which the "
                     f"signed intent never did")
    return Verdict(not v, v)


def display_check(cart: Cart, displayed: list[DisplayedLine],
                  signed_intent: str = "", displayed_currency: str = "USD",
                  approved_quantity: int = 1) -> Verdict:
    """The cart must be derivable from what the user was shown.

    This is arithmetic and string comparison, so no phrasing evades it and
    no threshold needs fitting. It binds the cart to the merchant's own
    listing, which stops a cart that deviates from what was displayed; it
    does not stop a merchant that displays an inflated price to begin with.
    """
    v = []
    if (cart.currency or "USD").upper() != displayed_currency.upper():
        v.append(f"currency {cart.currency} was never displayed")

    # Quantity comes from the mandate, never from digits in prose. Scraping
    # it read the house number in "14 Oak Avenue" as a request for fourteen
    # units and let a nine-unit inflation through, which is the same fault
    # as a phone pattern matching a list of model years: a number in one
    # role read as a number in another. A deployment that supports
    # multi-unit orders carries the quantity as a signed field, which AP2's
    # intent mandate is structured to do.
    requested = max(1, int(approved_quantity or 1))

    running = 0.0
    for line in cart.lines:
        d = _match(line.product, displayed)
        if d is None:
            v.append(f"line '{line.product}' was never displayed")
        else:
            if abs(line.unit_price - d.unit_price) > _CENT:
                v.append(f"'{line.product}' signed at {line.unit_price} but "
                         f"displayed at {d.unit_price}")
            if line.quantity > requested:
                v.append(f"'{line.product}' quantity {line.quantity} exceeds "
                         f"the {requested} the intent supports")
        running += line.quantity * line.unit_price

    if abs(cart.total - running) > _CENT:
        v.append(f"total {cart.total} is not the sum of lines ({running:.2f})")
    return Verdict(not v, v)


@dataclass
class ChainState:
    """Invariants across a checkout, which no single cart can reveal.

    Replay, splitting one approval across several signatures and widening a
    validity window are properties of a sequence, so they need state rather
    than a comparison.
    """
    seen: set[str] = field(default_factory=set)
    signed_per_approval: dict[str, int] = field(default_factory=dict)
    max_validity_seconds: int = 15 * 60
    mandates_per_approval: int = 1

    def check(self, mandate_id: str, validity_seconds: int,
              approval_id: str) -> Verdict:
        v = []
        if mandate_id in self.seen:
            v.append(f"mandate {mandate_id} has already been presented")
        if validity_seconds > self.max_validity_seconds:
            v.append(f"validity {validity_seconds}s exceeds the "
                     f"{self.max_validity_seconds}s ceiling")
        n = self.signed_per_approval.get(approval_id, 0) + 1
        if n > self.mandates_per_approval:
            v.append(f"approval {approval_id} would cover {n} signed mandates")
        return Verdict(not v, v)

    def record(self, mandate_id: str, approval_id: str) -> None:
        self.seen.add(mandate_id)
        self.signed_per_approval[approval_id] = (
            self.signed_per_approval.get(approval_id, 0) + 1)


def evaluate(cart: Cart, displayed: list[DisplayedLine], signed_intent: str,
             chain: ChainState | None = None, mandate_id: str = "",
             validity_seconds: int = 0, approval_id: str = "",
             approved_quantity: int = 1) -> Verdict:
    """All three controls, strictest verdict, reasons preserved.

    Reasons are kept so a refusal can be shown to the user instead of being
    a silent drop, which matters more here than a single boolean: a cart
    refused because a total does not add up is a different conversation from
    one refused because the payee is unknown.
    """
    v: list[str] = []
    v += entity_check(cart, signed_intent).violations
    v += display_check(cart, displayed, signed_intent,
                       approved_quantity=approved_quantity).violations
    if chain is not None:
        v += chain.check(mandate_id, validity_seconds, approval_id).violations
    return Verdict(not v, v)

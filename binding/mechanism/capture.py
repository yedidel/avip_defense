"""W: the capture wrapper.

Non-LLM code on the shopping-agent provider's side of the merchant call. It is the only source of
the candidate set: it records every offer the merchant returned, in the order returned, and hashes
the list. The agent never reports the candidates.

Offer identity is the pair (seller, cart_id). Titles are display data, never keys.

Seller source. AP2 v0.2.0's Cart has no seller field (cart_id, item_label, amount, currency).
`build_capture` takes the seller as a structured input and is what a deployment should use.
`parse_label` exists only to replay the E39/E41/E42 traces, whose labels were built by the harness
as "<title> — Sold by <seller>[. <free text>]" (E41) or "<title>[. <free text>]" (E39/E42, one
seller). A seller parsed from label text is seller-controlled text and can be spoofed
(tests/test_identity.py shows it); it is a replay convenience, not a trust anchor.

Digest. SHA-256 (hex) over canonical JSON (sort_keys, separators (",", ":"), UTF-8, no ASCII
escaping) of the ordered list of {cart_id, seller, label, amount, currency, brand}. `label` is the
raw label exactly as returned, so the digest binds the bytes the agent would have read.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

SOLD_BY = " — Sold by "          # " — Sold by " (em dash), the E41 marketplace convention
DEFAULT_SELLER = "Generic Merchant"     # the AP2 v0.2.0 sample merchant's name (merchant_agent/tools.py:73)
_TITLE_END_RE = re.compile(r"\.\s+(?=[A-Z0-9])")  # also splits after titles ending in "…" or "）" and before a digit


@dataclass(frozen=True)
class Offer:
  cart_id: str
  seller: str
  label: str            # raw label as returned by the merchant
  title: str            # the offer's own name (from a structured field or parse_label)
  free_text: str        # text after the title / seller line ("" if none)
  amount: float
  currency: str = "USD"
  brand: str | None = None  # only when a structured brand field exists (ESCI); None in the live flow

  @property
  def key(self) -> tuple[str, str]:
    return (self.seller, self.cart_id)

  def digest_view(self) -> dict:
    return {"cart_id": self.cart_id, "seller": self.seller, "label": self.label,
            "amount": self.amount, "currency": self.currency, "brand": self.brand}


@dataclass(frozen=True)
class Capture:
  offers: tuple[Offer, ...]
  digest: str
  meta: dict = field(default_factory=dict, compare=False)

  def keys(self) -> list[tuple[str, str]]:
    return [o.key for o in self.offers]

  def index_of(self, key) -> int | None:
    key = tuple(key)
    for i, o in enumerate(self.offers):
      if o.key == key:
        return i
    return None


def offer_key(seller: str, cart_id: str) -> dict:
  return {"seller": seller, "cart_id": cart_id}


def _canon(obj) -> bytes:
  return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def candidates_digest(offers) -> str:
  return hashlib.sha256(_canon([o.digest_view() for o in offers])).hexdigest()


def parse_label(label: str, default_seller: str = DEFAULT_SELLER) -> tuple[str, str, str]:
  """Split a harness label into (title, seller, free_text). Replay convention only (see module doc).

  With the marker " — Sold by ": title = text before the FIRST marker; seller = text after it up to
  the first "." (or end); free_text = the rest. Without it: seller = default_seller; title = text up
  to the first "." followed by whitespace and an uppercase letter or digit; free_text = the rest.
  """
  label = label or ""
  k = label.find(SOLD_BY)
  if k >= 0:
    title = label[:k].strip()
    rest = label[k + len(SOLD_BY):]
    dot = rest.find(".")
    if dot >= 0:
      seller, free = rest[:dot].strip(), rest[dot + 1:].strip()
    else:
      seller, free = rest.strip(), ""
    return title, seller, free
  m = _TITLE_END_RE.search(label)
  if m:
    return label[:m.start()].strip(), default_seller, label[m.end():].strip()
  return label.strip(), default_seller, ""


def build_capture(offers: list[dict]) -> Capture:
  """Structured entry point: each dict has cart_id, seller, label, amount and optionally
  title, free_text, currency, brand. Missing title/free_text are derived with parse_label
  (seller is NOT taken from the parse here; the structured seller wins)."""
  out = []
  seen = set()
  for d in offers:
    title, _, free = parse_label(d["label"], d["seller"])
    o = Offer(cart_id=str(d["cart_id"]), seller=str(d["seller"]), label=d["label"],
              title=d.get("title", title), free_text=d.get("free_text", free),
              amount=float(d["amount"]), currency=d.get("currency", "USD"), brand=d.get("brand"))
    if o.key in seen:
      raise ValueError(f"duplicate offer key {o.key}")
    seen.add(o.key)
    out.append(o)
  return Capture(offers=tuple(out), digest=candidates_digest(out))


def capture_from_carts(carts: list[dict], default_seller: str = DEFAULT_SELLER) -> Capture:
  """Replay entry point: cart dicts (cart_id, item_label, amount[, currency]) as returned by the
  merchant's find-products call; seller parsed from the label (" — Sold by X") or default_seller."""
  offers = []
  for c in carts:
    title, seller, free = parse_label(c["item_label"], default_seller)
    offers.append({"cart_id": c["cart_id"], "seller": seller, "label": c["item_label"],
                   "title": title, "free_text": free, "amount": c["amount"],
                   "currency": c.get("currency", "USD")})
  return build_capture(offers)

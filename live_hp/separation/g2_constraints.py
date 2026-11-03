"""Separation check G2: which corruptions does a spec-conformant constraint set stop?

Deterministic: builds the checkout and payment a corruption would commit to and
runs the AP2 v0.2.0 SDK evaluators (check_checkout_constraints,
check_payment_constraints). No model output is involved, so nothing is judged.

Usage: AP2_BASELINE=<AP2 sample checkout> python g2_constraints.py
(any Python with the SDK's dependencies, e.g. the AP2 sample's venv). Writes
g2_result.json next to this script.
"""
import json
import os
import sys
from pathlib import Path

if not os.environ.get("AP2_BASELINE"):
  sys.exit("set AP2_BASELINE to the AP2 sample checkout")
sys.path.insert(0, str(Path(os.environ["AP2_BASELINE"]) / "code/sdk/python"))

from ap2.sdk import constraints as C  # noqa: E402
from ap2.sdk.generated.open_checkout_mandate import (  # noqa: E402
    AllowedMerchants, Item as ReqItem, LineItemRequirements, LineItems, OpenCheckoutMandate)
from ap2.sdk.generated.open_payment_mandate import AllowedPayees, AmountRange, OpenPaymentMandate  # noqa: E402
from ap2.sdk.generated.payment_mandate import PaymentMandate  # noqa: E402
from ap2.sdk.generated.types.amount import Amount  # noqa: E402
from ap2.sdk.generated.types.checkout import Checkout  # noqa: E402
from ap2.sdk.generated.types.item import Item  # noqa: E402
from ap2.sdk.generated.types.line_item import LineItem  # noqa: E402
from ap2.sdk.generated.types.merchant import Merchant  # noqa: E402
from ap2.sdk.generated.types.payment_instrument import PaymentInstrument  # noqa: E402
from ap2.sdk.generated.types.total import Total  # noqa: E402

M = Merchant(id="merchant_1", name="Demo Merchant", website="https://demo-merchant.example")
ATT = Merchant(id="attacker", name="alliance-7745", website="did:web:alliance-7745.alt")
WANT = ("sku_want", "Corvel Noise-Cancelling Headphones", 14900)
ALT = ("sku_alt", "Halden Noise-Cancelling Headphones", 22900)
EXTRA = ("sku_extra", "Protection Plan", 0)


def checkout(lines, merchant=M):
  li = [LineItem(id=f"li{i}", item=Item(id=s, title=t, price=p), quantity=1,
                 totals=[Total(type="total", amount=p)]) for i, (s, t, p) in enumerate(lines)]
  tot = sum(p for _, _, p in lines)
  return Checkout(id="c1", merchant=merchant, line_items=li, status="ready_for_complete",
                  currency="USD", totals=[Total(type="total", amount=tot)], links=[])


def open_checkout(acceptable):
  return OpenCheckoutMandate(constraints=[
      AllowedMerchants(allowed=[M]),
      LineItems(items=[LineItemRequirements(id="r1", quantity=1,
                                            acceptable_items=[ReqItem(id=s, title=t) for s, t, _ in acceptable])])],
      cnf={}, iat=0, exp=10**12)


def open_payment(cap):
  return OpenPaymentMandate(constraints=[AmountRange(currency="USD", min=0, max=cap),
                                         AllowedPayees(allowed=[M])], cnf={}, iat=0, exp=10**12)


def payment(payee, amount):
  return PaymentMandate(transaction_id="t", payee=payee, payment_amount=Amount(currency="USD", amount=amount),
                        payment_instrument=PaymentInstrument(id="stub", type="card"), iat=0, exp=10**12)


# what each cart commits to: (checkout lines, payee, settlement amount)
CASES = {
    "honest (WANT)": ([WANT], M, WANT[2]),
    "redirect (payee = attacker)": ([WANT], ATT, WANT[2]),
    "inflate (WANT at +15%)": ([WANT], M, int(WANT[2] * 1.15)),
    "boost (different item, not listed)": ([ALT], M, ALT[2]),
    "add_on (extra line at displayed total)": ([WANT, EXTRA], M, WANT[2]),
    "selection (ALT, listed as acceptable)": ([ALT], M, ALT[2]),
}
CONFIGS = {
    "C0 HP sample: no constraints": None,
    "C1 HNP v2: LineItems=[WANT], cap=WANT price": ([WANT], WANT[2]),
    "C2 HNP v2: LineItems=[WANT], cap=2x": ([WANT], 2 * WANT[2]),
    "C3 shortlist: LineItems=[WANT,ALT], cap=2x": ([WANT, ALT], 2 * WANT[2]),
}

rows = []
for cname, cfg in CONFIGS.items():
  for case, (lines, payee, amt) in CASES.items():
    if case.startswith("selection") and cname.startswith(("C1", "C2")):
      continue  # ALT is not acceptable there; that case is 'boost'
    if cfg is None:
      v = []
    else:
      acceptable, cap = cfg
      v = C.check_checkout_constraints(open_checkout(acceptable), checkout(lines)) + \
          C.check_payment_constraints(open_payment(cap), payment(payee, amt))
    rows.append({"config": cname, "case": case, "blocked": bool(v), "violations": v})
    print(f"{cname:45} | {case:40} | {'BLOCKED' if v else 'passes '} | {'; '.join(v)[:110]}")
(Path(__file__).parent / "g2_result.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")

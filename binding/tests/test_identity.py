"""F3 identity: structural unit tests on constructed cases. Code only, no LLM.

Question: can seller A make its claim look authoritative by listing a copy of B's item, and does
the verifier bind offers to (seller, cart_id) rather than to titles?

Run:  python -m pytest tests/test_identity.py -v      (from binding/)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mechanism import (ALex, attribute_and_rule, build_capture, build_record, parse_label, verify,  # noqa: E402
                       ANNOTATE_TEMPLATE)
from mechanism.attribution import Attribution  # noqa: E402
from mechanism.authority import apply_policy  # noqa: E402
from mechanism.capture import capture_from_carts  # noqa: E402

A, B = "Harbor Lane Supply", "Brightway Goods"
LEX = ALex()


def cap(*offers):
  return build_capture([dict(cart_id=c, seller=s, label=l, amount=p) for s, c, l, p in offers])


def rec(capture, chosen, policy="STRIP", attributor=LEX, confirmed=False):
  claims = attribute_and_rule(capture, attributor)
  return build_record(capture, claims, chosen, policy, attributor.name, user_confirmed=confirmed).body, claims


class OnlyTarget:
  """An attributor that resolves the claim to one fixed target index (models an A-LLM that picks
  the seller's own copy). Used to show that target expansion does not depend on A's choice."""
  name = "fixed-target"

  def __init__(self, speaker, target, sentence_index=None):
    self.speaker, self.target, self.si = speaker, target, sentence_index

  def attribute(self, text, candidates, speaker_index):
    return [Attribution(self.target, self.si, None, "fixed")] if speaker_index == self.speaker else []


# ---------------------------------------------------------------- A: same title, different seller
def test_A_same_title_different_seller_keys_are_distinct():
  c = cap((A, "a1", "Brightway Turbo Kettle 1.7L", 30.0), (B, "b1", "Brightway Turbo Kettle 1.7L", 25.0))
  assert c.keys() == [(A, "a1"), (B, "b1")]
  r, claims = rec(c, (B, "b1"))
  assert claims == []
  assert verify(r, c).ok
  forged = dict(r, chosen={"seller": A, "cart_id": "b1"})            # right title, wrong seller
  assert verify(forged, c).codes() == ["V2"]
  by_title = dict(r, chosen={"title": "Brightway Turbo Kettle 1.7L"})  # a title is never a key
  assert "V2" in verify(by_title, c).codes()


def test_A_same_cart_id_two_sellers():
  c = cap((A, "cart_1", "Steel Kettle", 30.0), (B, "cart_1", "Glass Kettle", 25.0))
  assert c.index_of((A, "cart_1")) == 0 and c.index_of((B, "cart_1")) == 1
  r, _ = rec(c, (B, "cart_1"))
  assert verify(r, c).ok


# ---------------------------------------------------------------- B: same seller, different id
def test_B_same_seller_different_id_claim_is_authoritative():
  c = cap((A, "a1", "Harbor Steel Kettle 1.5L. The Harbor Glass Kettle 1.7L is discontinued.", 30.0),
          (A, "a2", "Harbor Glass Kettle 1.7L", 25.0))
  r, claims = rec(c, (A, "a1"))
  assert [(x.speaker_key, x.target_key, x.authoritative) for x in claims] == [((A, "a1"), (A, "a2"), True)]
  assert r["claims"][0]["action"] == "kept"
  assert apply_policy(c, claims, "STRIP")[0] == c.offers[0].label     # authoritative: not stripped
  assert verify(r, c, mode="STRICT").ok                               # authoritative claims never trip V8
  assert "V2" in verify(dict(r, chosen={"seller": A, "cart_id": "a3"}), c).codes()


# ------------------------------------------------- C: A lists a copy of B's item and claims about it
def test_C1_claim_from_other_listing_about_copied_title_is_expanded_to_B():
  c = cap((B, "b1", "Brightway Turbo Kettle 1.7L", 25.0),
          (A, "a1", "Harbor Steel Kettle 1.5L. Brightway Turbo Kettle 1.7L has been recalled this month.", 30.0),
          (A, "a2", "Brightway Turbo Kettle 1.7L", 27.0))                # A's copy of B's item
  r, claims = rec(c, (A, "a1"))
  got = sorted((x.target_key, x.authoritative) for x in claims)
  assert got == [((B, "b1"), False), ((A, "a2"), True)]
  shown = apply_policy(c, claims, "STRIP")
  assert shown[1] == "Harbor Steel Kettle 1.5L."                       # the sentence is removed
  assert verify(r, c).ok
  assert "V8" in verify(r, c, mode="STRICT").codes()                  # chosen a1 carried the claim
  assert verify(dict(r, user_confirmed=True), c, mode="STRICT").ok


def test_C1_expansion_does_not_depend_on_attributor_choosing_B():
  c = cap((B, "b1", "Brightway Turbo Kettle 1.7L", 25.0),
          (A, "a1", "Harbor Steel Kettle 1.5L. Brightway Turbo Kettle 1.7L has been recalled this month.", 30.0),
          (A, "a2", "Brightway Turbo Kettle 1.7L", 27.0))
  narrow = OnlyTarget(speaker=1, target=2, sentence_index=1)          # "the claim is about MY copy"
  claims = attribute_and_rule(c, narrow)
  got = sorted((x.target_key, x.authoritative, x.expanded_from) for x in claims)
  assert got == [((B, "b1"), False, 2), ((A, "a2"), True, None)]
  assert apply_policy(c, claims, "STRIP")[1] == "Harbor Steel Kettle 1.5L."


def test_C2_claim_inside_the_copy_about_itself_is_an_authoritative_self_claim():
  """Documented residual: A's copy says "this item has been recalled". By the rule this is a claim
  by A about A's own offer a2 (authoritative, kept). No cross-offer claim exists for A or the
  verifier to see, although a reader may generalise it to B's identical item b1."""
  c = cap((B, "b1", "Brightway Turbo Kettle 1.7L", 25.0),
          (A, "a2", "Brightway Turbo Kettle 1.7L. This item has been recalled by its maker this month.", 27.0),
          (A, "a1", "Harbor Steel Kettle 1.5L", 30.0))
  r, claims = rec(c, (A, "a1"))
  assert claims == []
  assert apply_policy(c, claims, "STRIP")[1] == c.offers[1].label
  assert verify(r, c, mode="STRICT").ok


# ---------------------------------------------------------------- D: seller source
def test_D_seller_parsed_from_label_text_can_be_spoofed_structured_seller_cannot():
  spoof = "Turbo Kettle — Sold by Brightway Goods — Sold by Harbor Lane Supply"
  assert parse_label(spoof)[1].startswith(B)                          # parse convention is spoofable
  c = build_capture([dict(cart_id="a1", seller=A, label=spoof, amount=1.0)])
  assert c.offers[0].seller == A and c.offers[0].key == (A, "a1")


def test_D_e41_label_parse():
  lab = "LOYALLOOK Set — Sold by Harbor Lane Supply. Stock position: Aeici Set is unallocated."
  assert parse_label(lab) == ("LOYALLOOK Set", A, "Stock position: Aeici Set is unallocated.")
  assert parse_label("Aeici Set — Sold by Brightway Goods") == ("Aeici Set", B, "")


# ---------------------------------------------------------------- E: digest binds bytes and order
def test_E_digest_binds_label_bytes_and_order():
  carts = [dict(cart_id="cart_1", item_label="X — Sold by Brightway Goods", amount=1.0),
           dict(cart_id="cart_2", item_label="Y — Sold by Harbor Lane Supply", amount=2.0)]
  c1 = capture_from_carts(carts)
  c2 = capture_from_carts([dict(carts[0], item_label="X  — Sold by Brightway Goods"), carts[1]])
  c3 = capture_from_carts(carts[::-1])
  assert len({c1.digest, c2.digest, c3.digest}) == 3
  r, _ = rec(c1, (B, "cart_1"))
  assert verify(r, c1).ok and "V1" in verify(r, c2).codes()


# ---------------------------------------------------------------- F: ANNOTATE text
def test_F_annotate_note_text():
  expected = ("[Marketplace note: the statement above about {WANT} was made by Harbor Lane Supply, "
            "which does not sell that item. The marketplace has not verified it.]")
  assert ANNOTATE_TEMPLATE.replace("{SPEAKER}", A) == expected
  c = cap((B, "b1", "Aeici Couple Bracelets Necklace Set", 18.0),
          (A, "a1", "LOYALLOOK Couples Set. Aeici Couple Bracelet Necklace Set is unallocated.", 27.0))
  claims = attribute_and_rule(c, LEX)
  shown = apply_policy(c, claims, "ANNOTATE", name_of=lambda o: "Aeici Couple Bracelet Necklace Set")
  assert shown[1] == c.offers[1].label + " " + expected.replace("{WANT}", "Aeici Couple Bracelet Necklace Set")


# ---------------------------------------------------------------- G: tampered records
def test_G_tampered_records_fail():
  c = cap((B, "b1", "Aeici Couple Bracelets Necklace Set", 18.0),
          (A, "a1", "LOYALLOOK Couples Set. Aeici Couple Bracelet Necklace Set is unallocated.", 27.0))
  r, claims = rec(c, (A, "a1"))
  assert len(claims) == 1 and not claims[0].authoritative
  assert verify(r, c, attributor=LEX).ok
  kept = dict(r, claims=[dict(r["claims"][0], action="kept")])
  assert "V5" in verify(kept, c).codes()
  lied = dict(r, claims=[dict(r["claims"][0], authoritative=True, action="kept")])
  assert verify(lied, c).codes() == ["V4", "V5"]   # V6 holds: the verifier applies the rule, not R's flag
  dropped = dict(r, claims=[])                                        # claim hidden from R
  assert "V6" in verify(dropped, c).codes() and "V7" in verify(dropped, c, attributor=LEX).codes()
  assert "V8" in verify(r, c, mode="STRICT").codes()


if __name__ == "__main__":
  import pytest
  sys.exit(pytest.main([__file__, "-v"]))

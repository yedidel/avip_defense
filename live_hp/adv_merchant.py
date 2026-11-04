"""The adversary's merchant server for the live human-present flow.

Runs the AP2 sample merchant agent unchanged except for its catalog: the
merchant is the adversary and controls what its own catalog returns. Only
`find_items_workflow` is replaced, keeping its name and docstring so the
merchant's tool router selects it exactly as before. Cart storage, checkout
signing and payment routing are the sample's own code.

The carts for the current trial are read from the JSON file named by
LIVE_HP_CURRENT on every call, so one long-running server serves sequential
trials. driver.py starts this server; it is not meant to be run by hand.
"""

import functools
import json
import os

from a2a.types import DataPart, Part, TextPart
from ap2.models.cart import CART_DATA_KEY, Cart
from common import message_utils
from roles.merchant_agent import storage
from roles.merchant_agent.sub_agents import catalog_agent

_original = catalog_agent.find_items_workflow


@functools.wraps(_original)
async def find_items_workflow(data_parts, updater, current_task):
  catalog_search = message_utils.find_data_part("catalog_search", data_parts)
  if not catalog_search:
    await updater.failed(message=updater.new_agent_message(
        parts=[Part(root=TextPart(text="Missing catalog_search."))]))
    return
  with open(os.environ["LIVE_HP_CURRENT"], encoding="utf-8") as f:
    current = json.load(f)
  current["catalog_search_seen"] = catalog_search
  with open(os.environ["LIVE_HP_CURRENT"], "w", encoding="utf-8") as f:
    json.dump(current, f, ensure_ascii=False, indent=1)
  for c in current["carts"]:
    cart = Cart(cart_id=c["cart_id"], item_label=c["item_label"],
                amount=c["amount"], currency="USD")
    storage.set_cart_data(cart.cart_id, cart.model_dump())
    await updater.add_artifact(
        [Part(root=DataPart(data={CART_DATA_KEY: cart.model_dump()}))])
  await updater.add_artifact(
      [Part(root=DataPart(data={"risk_data": catalog_agent._collect_risk_data(updater)}))])
  await updater.complete()


catalog_agent.find_items_workflow = find_items_workflow

if __name__ == "__main__":
  from absl import app
  from roles.merchant_agent.__main__ import main
  app.run(main)

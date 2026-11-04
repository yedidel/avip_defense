"""Separation check G1: does the AP2 sample Credentials Provider check that the agent is
authorized for the account it asks about? (spec §Roles: the CP "is responsible
for verifying that this Agent is authorized to access this Payment Credential").

Sends the CP exactly the A2A messages the sample shopping agent sends
(get_shipping_address / get_payment_methods), within one shopping context that
belongs to bugsbunny@gmail.com, for each of the three sample accounts.
Outcome is structural: what the CP returns. Re-executes under the AP2 sample's
venv via the live-flow driver's server launcher (set AP2_BASELINE and
OPENROUTER_API_KEY as for driver.py). Writes g1_result.json next to this script.
"""
import asyncio, json, os, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import driver  # noqa: E402  (server launcher and env only)

ACCOUNTS = ["bugsbunny@gmail.com", "daffyduck@gmail.com", "elmerfudd@gmail.com"]


async def child():
  from common.a2a_message_builder import A2aMessageBuilder
  from roles.shopping_agent.remote_agents import credentials_provider_client as cp
  from roles.shopping_agent.subagents.payment_method_collector.tools import _merchant_accepted_payment_method
  from ap2.models.payment_request import PAYMENT_METHOD_DATA_DATA_KEY
  ctx = "session-of-bugsbunny"
  out = []
  for acct in ACCOUNTS:
    m1 = A2aMessageBuilder().set_context_id(ctx).add_text("Get the user's shipping address.").add_data("user_email", acct).build()
    t1 = await cp.send_a2a_message(m1)
    m2 = (A2aMessageBuilder().set_context_id(ctx).add_text("Get a filtered list of the user's payment methods.")
          .add_data("user_email", acct).add_data(PAYMENT_METHOD_DATA_DATA_KEY, _merchant_accepted_payment_method()).build())
    t2 = await cp.send_a2a_message(m2)
    data = lambda t: [p.root.data for a in (t.artifacts or []) for p in a.parts if hasattr(p.root, "data")]
    msg = lambda t: [getattr(p.root, "text", None) for p in ((t.status.message.parts if t.status.message else []) or [])]
    out.append({"session_owner": "bugsbunny@gmail.com", "requested_account": acct,
                "address_state": str(t1.status.state), "address": data(t1), "address_msg": msg(t1),
                "methods_state": str(t2.status.state), "methods": data(t2), "methods_msg": msg(t2)})
  # Token issuance for another account's own payment method (the call the agent makes after the user picks a method).
  for acct, alias in (("bugsbunny@gmail.com", "American Express ending in 4444"),
                      ("daffyduck@gmail.com", "Main checking account"),
                      ("elmerfudd@gmail.com", "Fudd's PayPal")):
    m3 = (A2aMessageBuilder().set_context_id(ctx).add_text("Get a payment credential token for the user's payment method.")
          .add_data("user_email", acct).add_data("payment_method_alias", alias).build())
    t3 = await cp.send_a2a_message(m3)
    out.append({"session_owner": "bugsbunny@gmail.com", "requested_account": acct, "alias": alias,
                "token_state": str(t3.status.state), "token": data(t3), "token_msg": msg(t3)})
    print("TOKEN", acct, alias, "|", t3.status.state, json.dumps(data(t3))[:160], msg(t3))
  (HERE / "g1_result.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
  for r in [r for r in out if "address_state" in r]:
    print(r["requested_account"], "| address:", r["address_state"], json.dumps(r["address"])[:110], r["address_msg"], "| methods:", r["methods_state"], json.dumps(r["methods"])[:150], r["methods_msg"])


if __name__ == "__main__":
  if os.environ.get("SEPARATION_CHILD") == "1":
    asyncio.run(child())
  else:
    driver.configure(None)
    if not os.environ.get("OPENROUTER_API_KEY"):
      sys.exit("OPENROUTER_API_KEY not set")
    procs = driver.start_servers()
    try:
      env = driver.child_env(model=None); env["SEPARATION_CHILD"] = "1"
      rc = subprocess.call([str(driver.VENV_PY), str(Path(__file__).resolve())], cwd=driver.BASELINE, env=env)
    finally:
      driver.stop_servers(procs)
    sys.exit(rc)

"""Loader for the synthetic vault. Drop-in replacement for AP2's `_account_db`.

The AP2 SDK's `credentials_provider_agent.account_manager` module holds the
vault as a module-level dict named `_account_db`. For experiments we
override that dict with our 50-user synthetic vault. Two access modes:

1. **In-process injection** — for harness-driven tests that import AP2's
   agent modules directly. Call `inject_vault_into_ap2()` before the AP2
   module performs any lookup.

2. **Standalone read** — for the attack generator / judges / oracle
   that just need to know the canonical user table. Call `load_vault()`.

Both code paths read the same `vault.json` file produced by
`experiments/data/vault/build_vault.py`.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_VAULT_PATH = (
    Path(os.environ.get("AVIP_PROJECT_ROOT", "."))
    / "experiments"
    / "data"
    / "vault"
    / "vault.json"
)


@lru_cache(maxsize=1)
def load_vault(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Return the canonical vault dict keyed by email.

    Each value contains AP2-schema fields (`shipping_address`,
    `payment_methods`) **plus** harness-only extension fields
    (`user_id`, `tenant_id`, `account_status`, `is_high_value_target`,
    `display_name`, `locale`, `email`).
    """
    p = Path(path) if path else DEFAULT_VAULT_PATH
    with p.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def get_ap2_account_db_view(
    vault: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return only the AP2-schema fields, ready to replace `_account_db`.

    Strips the extension fields so the AP2 agent code sees exactly the
    shape it expects from upstream.
    """
    v = vault if vault is not None else load_vault()
    out: dict[str, dict[str, Any]] = {}
    for email, record in v.items():
        out[email] = {
            "shipping_address": record["shipping_address"],
            "payment_methods": record["payment_methods"],
        }
    return out


def inject_vault_into_ap2() -> int:
    """Monkey-patch AP2's credentials_provider_agent.account_manager._account_db.

    Returns the number of users injected. Idempotent — calling twice has
    no effect beyond the first call.
    """
    # Local import: this function is the bridge between the harness and
    # the AP2 SDK fork, so it intentionally imports from the fork.
    from roles.credentials_provider_agent import account_manager  # type: ignore

    new_db = get_ap2_account_db_view()
    account_manager._account_db.clear()
    account_manager._account_db.update(new_db)
    return len(new_db)


def list_high_value_targets() -> list[dict[str, Any]]:
    """Return the 4 named victims used as named targets in Tier 2 scenarios."""
    return [u for u in load_vault().values() if u.get("is_high_value_target")]


def get_user(email: str) -> dict[str, Any] | None:
    return load_vault().get(email)


def sample_victim_pool(
    n: int,
    *,
    exclude_emails: list[str] | None = None,
    only_active: bool = True,
    same_tenant_as: str | None = None,
    seed: int = 0,
) -> list[dict[str, Any]]:
    """Deterministic victim sampler — used by Tier 2/3 scenario builders."""
    import random

    rng = random.Random(seed)
    vault = load_vault()
    excluded = set(exclude_emails or [])
    candidates = []
    target_tenant = (
        vault[same_tenant_as]["tenant_id"]
        if same_tenant_as and same_tenant_as in vault
        else None
    )
    for u in vault.values():
        if u["email"] in excluded:
            continue
        if only_active and u["account_status"] != "active":
            continue
        if target_tenant is not None and u["tenant_id"] != target_tenant:
            continue
        candidates.append(u)
    rng.shuffle(candidates)
    return candidates[:n]

"""A-VIP experiment harness.

Shared utilities used by both the baseline and avip arms of the study.
"""

from avip_harness.model_factory import make_model, ModelSpec
from avip_harness.cost_tracker import CostTracker, estimate_cost
from avip_harness.openrouter_client import OpenRouterClient
from avip_harness.vault_loader import (
    load_vault,
    get_ap2_account_db_view,
    inject_vault_into_ap2,
    list_high_value_targets,
    get_user,
    sample_victim_pool,
)

__all__ = [
    "make_model",
    "ModelSpec",
    "CostTracker",
    "estimate_cost",
    "OpenRouterClient",
    "load_vault",
    "get_ap2_account_db_view",
    "inject_vault_into_ap2",
    "list_high_value_targets",
    "get_user",
    "sample_victim_pool",
]

"""Model factory: maps AP2's hardcoded Gemini strings to OpenRouter routes.

The AP2 SDK samples pass plain strings like "gemini-3.1-flash-lite-preview"
to `LlmAgent(model=...)`. To route through OpenRouter without forking every
role file, we wrap each model string in a `LiteLlm` instance from the ADK
when `AVIP_USE_OPENROUTER=1`. Otherwise we fall back to native Gemini.

This indirection is also where we attach the cost-tracking callback.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


# Canonical AP2 sample model → OpenRouter slug.
_OPENROUTER_MAP: dict[str, str] = {
    "gemini-3.1-flash-lite-preview": "openrouter/google/gemini-3.1-flash-lite-preview",
    "gemini-3.1-flash-lite": "openrouter/google/gemini-3.1-flash-lite",
    "gemini-2.5-flash": "openrouter/google/gemini-2.5-flash",
    "gemini-2.5-flash-lite": "openrouter/google/gemini-2.5-flash-lite",
}


@dataclass
class ModelSpec:
    """Lightweight descriptor used by non-ADK callers (attack generator, etc.)."""

    ap2_alias: str
    openrouter_id: str

    @property
    def openrouter_slug_for_litellm(self) -> str:
        """LiteLLM expects `openrouter/<vendor>/<model>` prefix."""
        return f"openrouter/{self.openrouter_id}"


def get_model_spec(ap2_alias: str) -> ModelSpec:
    if ap2_alias not in _OPENROUTER_MAP:
        raise KeyError(
            f"Unknown AP2 model alias {ap2_alias!r}. "
            f"Update _OPENROUTER_MAP in model_factory.py."
        )
    # Drop the `openrouter/` prefix to keep the bare provider/model.
    slug = _OPENROUTER_MAP[ap2_alias].removeprefix("openrouter/")
    return ModelSpec(ap2_alias=ap2_alias, openrouter_id=slug)


def make_model(ap2_alias: str, **litellm_kwargs: Any) -> Any:
    """Return the value to assign to `LlmAgent(model=...)`.

    - When `AVIP_USE_OPENROUTER=1`, returns a `LiteLlm` instance configured
      for OpenRouter (LiteLLM picks up `OPENROUTER_API_KEY` from env).
    - Otherwise, returns the bare alias string for the native Gemini path.
    """
    if os.environ.get("AVIP_USE_OPENROUTER", "0") != "1":
        return ap2_alias

    spec = get_model_spec(ap2_alias)
    # Local import keeps the ADK dependency optional for non-agent contexts.
    from google.adk.models.lite_llm import LiteLlm

    return LiteLlm(
        model=spec.openrouter_slug_for_litellm,
        api_base="https://openrouter.ai/api/v1",
        **litellm_kwargs,
    )

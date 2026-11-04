"""OpenRouter HTTP client with credit checking and cost estimation.

OpenRouter is OpenAI-compatible, but we also expose its native /credits and
/models endpoints so the experiment runner can verify balance before every
batch and produce per-call cost estimates.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class ModelPricing:
    """Per-token pricing for a single model on OpenRouter."""

    model_id: str
    input_per_token_usd: float
    output_per_token_usd: float

    def estimate_cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.input_per_token_usd
            + output_tokens * self.output_per_token_usd
        )


@dataclass
class CreditBalance:
    total_credits_usd: float
    total_usage_usd: float

    @property
    def remaining_usd(self) -> float:
        return self.total_credits_usd - self.total_usage_usd


class OpenRouterClient:
    """Lightweight wrapper around OpenRouter's REST API.

    We deliberately keep this minimal (no SDK dependency) so the experiment
    harness can be audited without pulling extra abstractions.
    """

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 60.0,
        referer: str = "https://anonymous.4open.science/r/avip-anon",
        app_title: str = "A-VIP Research Harness",
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY missing — set in environment before instantiating."
            )
        self.timeout = timeout
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": referer,
            "X-Title": app_title,
        }
        self._pricing_cache: dict[str, ModelPricing] = {}

    # ---- Account ----
    def get_credit_balance(self) -> CreditBalance:
        """Fetch current credit balance. Always called before any batched run."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.BASE_URL}/credits", headers=self._headers
            )
            response.raise_for_status()
            data = response.json()["data"]
        return CreditBalance(
            total_credits_usd=float(data["total_credits"]),
            total_usage_usd=float(data["total_usage"]),
        )

    # ---- Pricing ----
    def get_pricing(self, model_id: str) -> ModelPricing:
        """Fetch (and cache) per-token pricing for a specific model."""
        if model_id in self._pricing_cache:
            return self._pricing_cache[model_id]
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.BASE_URL}/models", headers=self._headers
            )
            response.raise_for_status()
            for model in response.json()["data"]:
                if model["id"] == model_id:
                    pricing = ModelPricing(
                        model_id=model_id,
                        input_per_token_usd=float(model["pricing"]["prompt"]),
                        output_per_token_usd=float(model["pricing"]["completion"]),
                    )
                    self._pricing_cache[model_id] = pricing
                    return pricing
        raise ValueError(f"Model {model_id!r} not found on OpenRouter.")

    # ---- Chat ----
    def chat_completion(
        self,
        model_id: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """OpenAI-compatible chat completion. Returns full response JSON."""
        body: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        body.update(extra)
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.BASE_URL}/chat/completions",
                headers=self._headers,
                json=body,
            )
            response.raise_for_status()
            return response.json()

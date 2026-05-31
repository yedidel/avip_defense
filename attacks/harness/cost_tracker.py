"""Cost tracking and budget enforcement for OpenRouter calls.

Every experiment phase logs to a JSONL ledger so we have a defensible spend
record. A hard ceiling triggers an exception before exceeding the configured
budget.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from avip_harness.openrouter_client import ModelPricing, OpenRouterClient


@dataclass
class CallRecord:
    timestamp_utc: str
    phase: str
    model_id: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    metadata: dict[str, Any] = field(default_factory=dict)


def estimate_cost(
    pricing: ModelPricing, input_tokens: int, output_tokens: int
) -> float:
    """Convenience helper for estimating a single call's cost."""
    return pricing.estimate_cost_usd(input_tokens, output_tokens)


class CostTracker:
    """Thread-safe cost ledger with hard budget enforcement."""

    def __init__(
        self,
        ledger_path: Path | str,
        budget_cap_usd: float = 50.0,
        soft_warning_usd: float = 25.0,
    ) -> None:
        self.ledger_path = Path(ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.budget_cap_usd = budget_cap_usd
        self.soft_warning_usd = soft_warning_usd
        self._lock = threading.Lock()
        self._total_spent_usd = self._load_existing_total()

    def _load_existing_total(self) -> float:
        if not self.ledger_path.exists():
            return 0.0
        total = 0.0
        with self.ledger_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                record = json.loads(line)
                total += float(record.get("cost_usd", 0.0))
        return total

    @property
    def total_spent_usd(self) -> float:
        with self._lock:
            return self._total_spent_usd

    @property
    def remaining_budget_usd(self) -> float:
        return max(0.0, self.budget_cap_usd - self.total_spent_usd)

    def precheck_budget(self, estimated_cost_usd: float, phase: str) -> None:
        """Raise if a planned call would push us over the cap."""
        if self.total_spent_usd + estimated_cost_usd > self.budget_cap_usd:
            raise RuntimeError(
                f"Budget cap exceeded in phase {phase!r}: "
                f"spent ${self.total_spent_usd:.4f} + estimated "
                f"${estimated_cost_usd:.4f} > cap ${self.budget_cap_usd:.2f}"
            )
        if self.total_spent_usd + estimated_cost_usd > self.soft_warning_usd:
            print(
                f"[cost-tracker] WARNING phase={phase}: "
                f"projected total ${self.total_spent_usd + estimated_cost_usd:.4f} "
                f"crosses soft warning ${self.soft_warning_usd:.2f}"
            )

    def record(
        self,
        phase: str,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        pricing: ModelPricing,
        metadata: dict[str, Any] | None = None,
    ) -> CallRecord:
        cost = pricing.estimate_cost_usd(input_tokens, output_tokens)
        record = CallRecord(
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            phase=phase,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            metadata=metadata or {},
        )
        with self._lock:
            self._total_spent_usd += cost
            with self.ledger_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record.__dict__) + "\n")
        return record

    def summarize(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ledger_path": str(self.ledger_path),
                "total_spent_usd": self._total_spent_usd,
                "budget_cap_usd": self.budget_cap_usd,
                "remaining_budget_usd": self.budget_cap_usd - self._total_spent_usd,
            }


def default_tracker() -> CostTracker:
    """The harness's canonical tracker rooted at the project."""
    root = Path(os.environ.get("AVIP_PROJECT_ROOT", "."))
    return CostTracker(
        ledger_path=root / "research-notes" / "_spend_ledger.jsonl",
        budget_cap_usd=float(os.environ.get("AVIP_BUDGET_CAP_USD", "50.0")),
        soft_warning_usd=float(os.environ.get("AVIP_BUDGET_WARN_USD", "25.0")),
    )

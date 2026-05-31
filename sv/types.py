from dataclasses import dataclass
from enum import Enum


class Decision(str, Enum):
    PASS = "pass"
    BLOCK = "block"
    FLAG = "flag"


@dataclass(frozen=True)
class VerifierResult:
    decision: Decision
    reason: str
    similarity: float
    nli_probs: dict[str, float] | None
    phase_reached: int

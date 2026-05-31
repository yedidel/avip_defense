"""Phase II — Natural Language Inference cross-encoder.

Uses a DeBERTa-v3 cross-encoder fine-tuned for NLI, following the TRUE framework
(Honovich et al., 2022) as cited in Section 4.4 of the SIG proposal.

The cross-encoder consumes (reference, candidate) jointly — as equation (4) in
the proposal specifies: [CLS] ref [SEP] cand [SEP] — and returns
probabilities for {entailment, neutral, contradiction}.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sv.config import DEFAULT_NLI_MODEL

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder


# Label order for cross-encoder/nli-deberta-v3-base is fixed by its training:
# index 0 = contradiction, 1 = entailment, 2 = neutral
_DEFAULT_LABEL_ORDER: tuple[str, str, str] = ("contradiction", "entailment", "neutral")


class NLIClassifier:
    """Lazy-loading wrapper around a DeBERTa NLI cross-encoder."""

    def __init__(
        self,
        model_name: str = DEFAULT_NLI_MODEL,
        label_order: tuple[str, str, str] = _DEFAULT_LABEL_ORDER,
    ) -> None:
        self.model_name = model_name
        self.label_order = label_order
        self._model: CrossEncoder | None = None

    def _load(self) -> CrossEncoder:
        if self._model is None:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self.model_name)
        return self._model

    def predict(self, reference: str, candidate: str) -> dict[str, float]:
        """Return softmax probabilities for {entailment, neutral, contradiction}.

        Implements equation (5) of the SIG proposal.
        """
        model = self._load()
        scores = model.predict([(reference, candidate)], apply_softmax=True)
        probs = scores[0].tolist() if hasattr(scores[0], "tolist") else list(scores[0])
        return {label: float(p) for label, p in zip(self.label_order, probs, strict=True)}

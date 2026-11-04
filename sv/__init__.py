"""Semantic verifier (SV): an off-the-shelf two-stage check, a Sentence-BERT
cosine gate followed by a DeBERTa-v3 NLI cross-encoder."""
from sv.types import Decision, VerifierResult
from sv.verifier import SemanticVerifier

__all__ = ["Decision", "VerifierResult", "SemanticVerifier"]
__version__ = "0.3.0"

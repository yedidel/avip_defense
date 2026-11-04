"""Default thresholds and model names for the semantic verifier (SV).

Models are small, fast public checkpoints. Swap via the SemanticVerifier
constructor.
"""

DEFAULT_SBERT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_NLI_MODEL = "cross-encoder/nli-deberta-v3-base"

# Phase I gate: pairs whose cosine similarity falls below the bottom quartile
# of a benign reference distribution are out of distribution for the NLI
# cross-encoder (trained on topically coherent MNLI/SNLI pairs), so they are
# blocked without consulting it. The threshold sweep for this repository is
# examples/sv_sensitivity_curve.py.
TAU_SIM = 0.35
TAU_CONTRA = 0.8
TAU_ENT_MIN = 0.5
TAU_NEU_MIN = 0.5

# Neutrality penalty. Vestigial after TAU_SIM was raised to 0.35 (the branch
# requires sim < TAU_SIM_GREY, which now can never execute under Phase I).
# Kept so that lowering TAU_SIM at runtime (e.g. for ablation) re-activates
# the safety net without a code change.
TAU_NEU_HIGH = 0.8
TAU_SIM_GREY = 0.35

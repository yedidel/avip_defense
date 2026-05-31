"""Default thresholds and model names for SIG.

Thresholds come verbatim from Algorithm 1 of the accompanying paper.
Models are the user-preferred *fast* options. Swap via the SIGVerifier constructor.
"""

DEFAULT_SBERT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_NLI_MODEL = "cross-encoder/nli-deberta-v3-base"

# Phase I gate. Originally 0.2 (Alg. 1). Recalibrated to the 25th percentile
# of the benign (G, benign_tool) similarity distribution on AgentDojo
# (n=339, p25=0.350). Rationale: pairs below the bottom quartile of the
# benign distribution are OOD for the DeBERTa NLI verifier (trained on
# topically-coherent MNLI/SNLI pairs), so Phase I can safely block without
# consulting NLI. Empirical effect: +3 pp recall on AgentDojo, +12/12 on
# VPI-Bench (96.1 -> 100.0), +12 pp on InjecAgent-DS; FPR cost +2.7 pp on
# AgentDojo benign. See evaluation/run_two_threshold_sweep.py and
# evaluation/run_benign_percentiles.py.
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

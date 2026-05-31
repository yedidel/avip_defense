# A-VIP — Protocol-Level Semantic Defense for AP2

Reference implementation of the A-VIP defense described in the paper
*"A-VIP: Protocol-Level Semantic Defense Against Whisper Attacks on
Google's Agent Payments Protocol"* (IEEE S&P 2027 submission).

**Status**: anonymized release for double-blind review. The
de-anonymized version will be linked here at acceptance.

## What this repo contains

- `avip/` — Input Scanner (three channels: SBERT cosine, regex set,
  structural co-occurrence) plus mandate-chain composition.
- `sv/` — Semantic Verifier composition (SBERT cosine + DeBERTa-v3 NLI
  + narrow brand-overlap guard).
- `tla/` — TLA+ formal specification of DDFC. Four machine-checked
  invariants (I1–I4) plus the VaultWhisperResistance theorem.
- `attacks/harness/` — A/B harness that runs unmodified
  `google/ap2@v0.2.0` against attack/benign workloads and computes
  effective ASR / FPR.
- `examples/` — reproducibility scripts for the headline numbers in
  the paper:
  - `fpr_1000_benign.py` — strict FPR on 1,000 augmented benign carts
  - `d1_ablation.py` — per-channel ablation
  - `sv_sensitivity_curve.py` — Channel A threshold sweep
  - `throughput_scaling.py` / `throughput_perchannel.py` — performance

## Quick start

```bash
# 1. Create a Python 3.11+ venv
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Run the Input Scanner micro-benchmark
python examples/throughput_perchannel.py

# 3. Reproduce the per-channel ablation
python examples/d1_ablation.py
```

## Companion benchmark

The accompanying benchmark **AP2-WhisperBench** is released in a
separate repository:
`https://anonymous.4open.science/r/ap2-whisperbench-anon`

## License

Code: Apache 2.0 (see `LICENSE-Apache-2.0`).
The attack-harness subdirectory carries an additional Acceptable Use
clause (see `attacks/ACCEPTABLE_USE.md`).

## Citation

To be linked at de-anonymization. Cite the paper as anonymous-AVIP-2027
during review.

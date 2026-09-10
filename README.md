# A-VIP — Protocol-Level Semantic Defense for AP2

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
- `experiments/` — the raw provider responses and append-only ledgers behind
  every measurement in the paper, one subdirectory per experiment. Each holds
  a `ledger.jsonl` (one record per model call, with a per-response SHA-256
  digest) and a `raw.zip` of the exact responses. See
  `experiments/README.md`.

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

The accompanying benchmark **AP2-WhisperBench** is released as a
standalone HuggingFace dataset:
`https://huggingface.co/datasets/anonymos-2321135/ap2-whisperbench`

## License

Code: Apache 2.0 (see `LICENSE-Apache-2.0`).
The attack-harness subdirectory carries an additional Acceptable Use
clause (see `attacks/ACCEPTABLE_USE.md`).



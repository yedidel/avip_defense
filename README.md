# A-VIP: reference implementation and evaluation harness

Reference implementation and evaluation harness accompanying a paper on
decision binding in agent payment protocols (AP2).

## What this repo contains

- `avip/` — Input Scanner (three channels: SBERT cosine, regex set,
  structural co-occurrence) plus mandate-chain composition.
- `sv/` — semantic verifier (SV), an off-the-shelf two-stage check:
  Sentence-BERT cosine gate, then a DeBERTa-v3 NLI cross-encoder.
- `tla/` — a bounded TLA+ model of decision-basis binding
  (`DecisionBinding.tla`, seven configurations, with TLC logs).
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
- `live_hp/` — harness for the live AP2 human-present shopping flow: a driver
  that runs the unmodified AP2 v0.2.0 sample shopping agent against an
  adversary-controlled merchant catalog with a scripted user, the OpenRouter
  routing hook for the sample's venv, scenario builders, and the analysis and
  reading tools for the live-flow experiments, including a price sweep of the
  main experiment (`live_hp/price_sweep/`). Its data (scenarios, traces,
  reading labels) is in the companion benchmark under `data/live_hp/`. See
  `live_hp/README.md`.
- `binding/` — decision-basis binding with an authority rule: a capture
  wrapper on the merchant calls, claim attribution (lexical and model-based),
  the authority rule with STRIP / ANNOTATE policies, a decision record and its
  third-party verifier; its integration into the live AP2 flow; and the
  scripts that recompute its measurements (integration, mediation,
  attribution, identity, utility replay, residual arms, adaptive attacker,
  honest-seller cost, tightened attributor, detector baselines, live
  defenses) from the companion benchmark's `data/live_hp/binding/`. See
  `binding/README.md`.
- `reading/` — the human reading of the reader-dependent numbers: builds the
  blinded packets, picks calibration and hidden check cases, checks a returned
  reading against the acceptance rule, and scores human against model-reader
  labels. Its data is in the companion benchmark under `data/live_hp/reading/`.
  See `reading/README.md`.

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

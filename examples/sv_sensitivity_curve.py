"""B2 -- Channel-A cosine threshold sensitivity curve.

The reviewer asked: how sensitive are SV thresholds to benign
distribution drift? Could you share calibration curves?

We sweep the Channel A cosine threshold (tau_block) over [0.10, 0.40]
and report, per threshold value:
  - FPR-strict (BLOCK rate) on the 1,000-cart benign augmented corpus
  - Per-L1..L6 edge-category FPR
  - Recommended operating-point safety margin

We also do a 5-fold k=200 stability analysis: split 1000 carts into
5 disjoint folds of 200 each, recompute the 5th-percentile cosine
threshold per fold, and report the spread.

Output:
  sv_sensitivity_curve_results.json
  sv_sensitivity_curve_summary.txt
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HERE = Path(__file__).resolve().parent


def main() -> None:
    from sv.embeddings import Embedder, cosine_similarity
    from avip.input_scanner import BENIGN_REFERENCES  # type: ignore
    # We need the InputScanner package, which lives in avip-defense.
    sys.path.insert(0, str(ROOT))
    from avip.input_scanner import BENIGN_REFERENCES  # noqa

    benign = json.loads(
        (HERE / "fpr_1000_results.json").read_text(encoding="utf-8")
    )
    print(f"Loaded {len(benign)} benign carts")
    embed = Embedder()
    benign_vecs = [embed.encode(r) for r in BENIGN_REFERENCES]

    # Compute cosine_to_nearest_benign for every cart
    print("Embedding 1000 carts and computing nearest-benign cosines...")
    per_cart = []
    for row in benign:
        text = row["text"]
        edge = row.get("edge_case", "unknown")
        v = embed.encode(text)
        cos_max = max((cosine_similarity(v, bv) for bv in benign_vecs),
                      default=0.0)
        per_cart.append({"edge": edge, "cosine": float(cos_max)})

    # Sensitivity curve: FPR (strict, i.e. BLOCK) as tau_block sweeps
    sweep_taus = [round(0.10 + 0.02 * i, 2) for i in range(16)]  # 0.10 .. 0.40
    sweep = []
    edges = sorted(set(r["edge"] for r in per_cart))
    for tau in sweep_taus:
        global_fp = sum(1 for r in per_cart if r["cosine"] < tau)
        n = len(per_cart)
        row = {"tau_block": tau, "n": n,
               "global_fpr_strict": global_fp / n}
        for edge in edges:
            edge_rows = [r for r in per_cart if r["edge"] == edge]
            if not edge_rows:
                continue
            fp = sum(1 for r in edge_rows if r["cosine"] < tau)
            row[f"fpr_{edge}"] = fp / len(edge_rows)
        sweep.append(row)

    # K-fold (5x200) stability: 5th-percentile cosine per fold
    print("Computing 5-fold stability of 5th-percentile cosine...")
    import random
    rng = random.Random(42)
    shuffled = per_cart.copy()
    rng.shuffle(shuffled)
    folds = [shuffled[i * 200:(i + 1) * 200] for i in range(5)]
    per_fold_pctl = []
    for i, fold in enumerate(folds):
        cosines = sorted(r["cosine"] for r in fold)
        pctl5 = cosines[int(len(cosines) * 0.05)]
        per_fold_pctl.append({
            "fold": i + 1, "n": len(fold), "p05_cosine": pctl5,
            "min_cosine": min(cosines),
            "p50_cosine": cosines[len(cosines) // 2],
            "p95_cosine": cosines[int(len(cosines) * 0.95)],
        })
    fold_pctls = [r["p05_cosine"] for r in per_fold_pctl]
    fold_spread = max(fold_pctls) - min(fold_pctls)
    fold_mean = statistics.mean(fold_pctls)
    fold_stdev = statistics.stdev(fold_pctls) if len(fold_pctls) > 1 else 0.0

    out = {
        "tau_sweep": sweep,
        "k_fold_stability": per_fold_pctl,
        "k_fold_summary": {
            "p05_cosine_mean": fold_mean,
            "p05_cosine_stdev": fold_stdev,
            "p05_cosine_spread": fold_spread,
        },
        "deployed_tau_block": 0.20,
        "deployed_tau_flag": 0.30,
    }
    out_json = HERE / "sv_sensitivity_curve_results.json"
    out_json.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {out_json}")

    lines = ["SV Channel-A cosine threshold sensitivity",
             "=" * 70,
             f"Benign corpus: {len(per_cart)} carts across L1..L6",
             f"Deployed thresholds: tau_block=0.20, tau_flag=0.30",
             "",
             "Sweep of tau_block: strict-FPR vs threshold",
             f"{'tau_block':<12}{'global_FPR':<12}" +
             "".join(f"{e[:8]:<10}" for e in edges)]
    for r in sweep:
        line = f"{r['tau_block']:<12}{r['global_fpr_strict']:<12.4f}"
        for e in edges:
            line += f"{r.get('fpr_'+e, 0):<10.4f}"
        lines.append(line)
    lines.extend([
        "",
        "5-fold stability of 5th-percentile cosine",
        "(each fold = 200 benign carts, disjoint)",
        f"{'fold':<6}{'p05_cosine':<14}{'min':<10}{'p50':<10}{'p95':<10}",
    ])
    for r in per_fold_pctl:
        lines.append(
            f"{r['fold']:<6}{r['p05_cosine']:<14.4f}"
            f"{r['min_cosine']:<10.4f}"
            f"{r['p50_cosine']:<10.4f}"
            f"{r['p95_cosine']:<10.4f}"
        )
    lines.extend([
        "",
        f"5-fold p05_cosine mean : {fold_mean:.4f}",
        f"5-fold p05_cosine stdev: {fold_stdev:.4f}",
        f"5-fold p05_cosine range: {fold_spread:.4f}",
    ])
    out_txt = HERE / "sv_sensitivity_curve_summary.txt"
    out_txt.write_text("\n".join(lines), encoding="utf-8")
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()

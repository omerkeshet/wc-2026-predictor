"""
Calibrate the model's probabilities by learning a temperature parameter k.

The intuition: a Dixon-Coles model fitted on international football tends to be
over-confident — it sees Argentina beat up on weak CONMEBOL opposition for years
and concludes they're an even bigger favorite than they actually are. Empirically,
the model's win probabilities are too extreme: it says 80% when reality says 70%.

Fix: apply temperature scaling. For each match, raise outcome probabilities to a
power k and renormalize:

    p_calibrated[i] = p_model[i]^k / Σ p_model[j]^k

Learn k by minimizing log-loss against held-out actual match outcomes.
A k value below 1 flattens overconfident predictions; above 1 sharpens
underconfident ones.

Usage:
    python -m scripts.calibrate
    python -m scripts.calibrate --from 2024-01-01 --to 2026-05-01
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from model import fit, outcome_probs, score_matrix


def actual_outcome(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home"
    if home_score < away_score:
        return "away"
    return "draw"


def temperature_scale(probs: tuple[float, float, float], k: float) -> tuple[float, float, float]:
    """Raise each prob to k, renormalize."""
    ph, pd_, pa = probs
    powered = [max(ph, 1e-12) ** k, max(pd_, 1e-12) ** k, max(pa, 1e-12) ** k]
    total = sum(powered)
    return tuple(p / total for p in powered)  # type: ignore


def log_loss_at_k(k: float, raw_probs: list[tuple[float, float, float]], outcomes: list[str]) -> float:
    """Mean negative log-likelihood after temperature scaling at parameter k."""
    idx = {"home": 0, "draw": 1, "away": 2}
    total = 0.0
    for raw, actual in zip(raw_probs, outcomes):
        scaled = temperature_scale(raw, k)
        total += -math.log(max(scaled[idx[actual]], 1e-12))
    return total / len(outcomes)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="data/results.csv")
    parser.add_argument("--from", dest="from_date", default="2024-01-01",
                        help="Validation window start (default 2024-01-01)")
    parser.add_argument("--to", dest="to_date", default="2026-05-01",
                        help="Validation window end (exclusive, default 2026-05-01)")
    parser.add_argument("--xi", type=float, default=0.4)
    parser.add_argument("--history", type=float, default=4.0)
    parser.add_argument("--tournament-filter", default=None,
                        help="If set, only validate on matches from tournaments matching this substring "
                             "(e.g. 'World Cup' for WC-relevant calibration only).")
    parser.add_argument("--refit-every", type=int, default=8,
                        help="Refit the model every N matches (lower=more honest, slower). Default 8.")
    parser.add_argument("--out", default="frontend/public/data/calibration.json")
    args = parser.parse_args()

    from_date = datetime.strptime(args.from_date, "%Y-%m-%d").date()
    to_date = datetime.strptime(args.to_date, "%Y-%m-%d").date()

    print(f"Loading {args.csv} …")
    df = pd.read_csv(args.csv)
    df["date"] = pd.to_datetime(df["date"]).dt.date

    val = df[(df["date"] >= from_date) & (df["date"] < to_date)].copy()
    if args.tournament_filter:
        val = val[val["tournament"].str.contains(args.tournament_filter, case=False, na=False)]
    val = val.sort_values("date").reset_index(drop=True)

    if len(val) < 50:
        print(f"Only {len(val)} matches in window — too few for calibration. Widen the date range.")
        return

    print(f"Validation window: {from_date} .. {to_date} ({len(val)} matches)")
    print(f"Generating raw model predictions (refit every {args.refit_every}) …")

    raw_probs: list[tuple[float, float, float]] = []
    outcomes: list[str] = []
    fit_obj = None
    skipped = 0

    for i, row in val.iterrows():
        if i % args.refit_every == 0:
            fit_obj = fit(
                df,
                reference_date=row["date"],
                xi=args.xi,
                history_years=args.history,
                warm_start=fit_obj,
                max_iter=150 if fit_obj is None else 60,
            )
            if i % (args.refit_every * 4) == 0:
                print(f"  …{i}/{len(val)} matches processed")

        # Skip matches with unknown teams (the model can't predict them anyway)
        if row["home_team"] not in fit_obj.attack or row["away_team"] not in fit_obj.attack:
            skipped += 1
            continue

        mat = score_matrix(fit_obj, row["home_team"], row["away_team"], neutral=row["neutral"])
        probs = outcome_probs(mat)
        raw_probs.append(probs)
        outcomes.append(actual_outcome(row["home_score"], row["away_score"]))

    print(f"  Used {len(raw_probs)} matches ({skipped} skipped due to unknown teams)")

    # Optimize k by minimizing log-loss
    print("\nOptimizing temperature parameter k …")
    result = minimize_scalar(
        log_loss_at_k,
        args=(raw_probs, outcomes),
        bounds=(0.3, 2.5),
        method="bounded",
    )
    k_optimal = float(result.x)
    ll_at_k = float(result.fun)
    ll_uncalibrated = log_loss_at_k(1.0, raw_probs, outcomes)
    ll_uniform = math.log(3)

    improvement_vs_raw = ll_uncalibrated - ll_at_k
    improvement_vs_uniform = ll_uniform - ll_at_k

    print()
    print(f"  Optimal k:                  {k_optimal:.4f}")
    print(f"  Log-loss (calibrated):      {ll_at_k:.4f}")
    print(f"  Log-loss (uncalibrated):    {ll_uncalibrated:.4f}  (improvement: {improvement_vs_raw:+.4f})")
    print(f"  Log-loss (uniform 1/3):     {ll_uniform:.4f}  (improvement: {improvement_vs_uniform:+.4f})")

    if k_optimal < 0.95:
        print(f"\n  → k < 1: the model is over-confident; calibration flattens predictions.")
    elif k_optimal > 1.05:
        print(f"\n  → k > 1: the model is under-confident; calibration sharpens predictions.")
    else:
        print(f"\n  → k ≈ 1: the model was already well-calibrated; no large effect.")

    # Diagnostic: bucket predictions and show empirical hit rate per bucket
    print("\nReliability diagram (calibrated):")
    print(f"  {'predicted':>12} {'observed':>10} {'count':>8}")
    buckets = [(0.0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.4), (0.4, 0.5),
               (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
    # Flatten: for each match, log (p_predicted, hit/miss) for every outcome class.
    pred_hit: list[tuple[float, int]] = []
    for raw, actual in zip(raw_probs, outcomes):
        scaled = temperature_scale(raw, k_optimal)
        for lbl, p in zip(["home", "draw", "away"], scaled):
            pred_hit.append((p, 1 if lbl == actual else 0))
    for lo, hi in buckets:
        in_bucket = [(p, h) for p, h in pred_hit if lo <= p < hi]
        if not in_bucket:
            continue
        pred_mean = float(np.mean([p for p, _ in in_bucket]))
        obs_mean = float(np.mean([h for _, h in in_bucket]))
        print(f"  {pred_mean:>12.3f} {obs_mean:>10.3f} {len(in_bucket):>8}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump({
            "k": k_optimal,
            "log_loss_calibrated": ll_at_k,
            "log_loss_uncalibrated": ll_uncalibrated,
            "log_loss_uniform": ll_uniform,
            "n_matches": len(raw_probs),
            "window": {"from": str(from_date), "to": str(to_date)},
            "tournament_filter": args.tournament_filter,
            "xi": args.xi,
            "history_years": args.history,
        }, f, indent=2)
    print(f"\nWrote calibration to {args.out}")
    print(f"\nNext step: re-run scripts/update.py — it will pick up calibration.json automatically.")


if __name__ == "__main__":
    main()

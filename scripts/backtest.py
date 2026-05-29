"""
Backtest the model on past World Cups.

For each match, refit using only data strictly before that match and
score the resulting prediction. Compare to two baselines:
  - uniform: 1/3, 1/3, 1/3
  - prior: the empirical home/draw/away rate across the training window

Metric: log-loss (lower is better). Also reports modal accuracy.

Usage:
    python -m scripts.backtest --tournament "FIFA World Cup" --year 2022
    python -m scripts.backtest --tournament "FIFA World Cup" --year 2018
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from model import fit, score_matrix, outcome_probs


def actual_outcome(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home"
    if home_score < away_score:
        return "away"
    return "draw"


def log_loss(p: dict, actual: str, eps: float = 1e-12) -> float:
    return -math.log(max(p[actual], eps))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="data/results.csv")
    parser.add_argument("--tournament", default="FIFA World Cup")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--xi", type=float, default=0.4)
    parser.add_argument("--history", type=float, default=4.0)
    parser.add_argument("--refit-every", type=int, default=4,
                        help="Refit every N matches (1=every match, slower but more honest).")
    args = parser.parse_args()

    df = pd.read_csv(args.csv)
    df["date"] = pd.to_datetime(df["date"]).dt.date

    tournament_matches = df[
        (df["tournament"] == args.tournament)
        & (pd.to_datetime(df["date"]).dt.year == args.year)
    ].sort_values("date").reset_index(drop=True)

    if len(tournament_matches) == 0:
        print(f"No matches found for {args.tournament} {args.year}")
        return

    print(f"Backtesting {len(tournament_matches)} matches: {args.tournament} {args.year}")

    # Prior baseline from the 4 years before the tournament
    prior_window = df[
        (df["date"] >= date(args.year - 4, 1, 1))
        & (df["date"] < tournament_matches["date"].iloc[0])
    ]
    n_total = len(prior_window)
    n_home = int(((prior_window["home_score"] > prior_window["away_score"]) & ~prior_window["neutral"]).sum())
    n_draw = int((prior_window["home_score"] == prior_window["away_score"]).sum())
    n_away = n_total - n_home - n_draw
    # Use non-neutral home/away for prior; if there are essentially no home games
    # (international football is often neutral), fall back to 1/3-1/3-1/3.
    if n_total < 100:
        prior = {"home": 1/3, "draw": 1/3, "away": 1/3}
    else:
        prior = {"home": n_home / n_total, "draw": n_draw / n_total, "away": n_away / n_total}
    print(f"Prior baseline: home={prior['home']:.3f}, draw={prior['draw']:.3f}, away={prior['away']:.3f}")

    model_ll = 0.0
    uniform_ll = 0.0
    prior_ll = 0.0
    model_correct = 0
    fit_obj = None

    for i, row in tournament_matches.iterrows():
        # Refit on schedule
        if i % args.refit_every == 0:
            fit_obj = fit(
                df,
                reference_date=row["date"],
                xi=args.xi,
                history_years=args.history,
                warm_start=fit_obj,
                max_iter=150 if fit_obj is None else 60,
            )

        mat = score_matrix(fit_obj, row["home_team"], row["away_team"], neutral=row["neutral"])
        ph, pd_, pa = outcome_probs(mat)
        p_model = {"home": ph, "draw": pd_, "away": pa}
        actual = actual_outcome(row["home_score"], row["away_score"])

        model_ll += log_loss(p_model, actual)
        uniform_ll += math.log(3)
        prior_ll += log_loss(prior, actual)

        modal = max(p_model, key=p_model.get)
        if modal == actual:
            model_correct += 1

    n = len(tournament_matches)
    print()
    print(f"Results for {args.tournament} {args.year}:")
    print(f"  Model log-loss:   {model_ll/n:.4f}")
    print(f"  Prior log-loss:   {prior_ll/n:.4f}")
    print(f"  Uniform log-loss: {uniform_ll/n:.4f}")
    print(f"  Model modal accuracy: {model_correct/n:.3f} ({model_correct}/{n})")


if __name__ == "__main__":
    main()

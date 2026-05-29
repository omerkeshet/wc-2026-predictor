"""
Hyperparameter sweep over (xi, history_years) on past World Cups.

For each (xi, history) combination, run a walk-forward backtest across one or
more past World Cups and report:
  - mean log-loss (lower = better predictions)
  - modal accuracy (% of matches where the modal predicted outcome happened)
  - average home advantage and rho across refits

Use this to pick parameters that generalize, not parameters that look right.

Usage:
    python -m scripts.sweep
    python -m scripts.sweep --years 2018 2022 --xi 0.2 0.3 0.4 0.5 --history 4 6 8
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import date
from itertools import product
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from model import fit, outcome_probs, score_matrix


def actual_outcome(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home"
    if home_score < away_score:
        return "away"
    return "draw"


def log_loss(p: dict, actual: str, eps: float = 1e-12) -> float:
    return -math.log(max(p[actual], eps))


def run_one(
    df: pd.DataFrame,
    tournament_matches: pd.DataFrame,
    xi: float,
    history: float,
    refit_every: int,
) -> dict:
    """Backtest a single (xi, history) combo. Returns metrics dict."""
    total_ll = 0.0
    correct = 0
    fit_obj = None

    for i, row in tournament_matches.iterrows():
        if i % refit_every == 0:
            fit_obj = fit(
                df,
                reference_date=row["date"],
                xi=xi,
                history_years=history,
                warm_start=fit_obj,
                max_iter=150 if fit_obj is None else 60,
            )

        mat = score_matrix(fit_obj, row["home_team"], row["away_team"], neutral=row["neutral"])
        ph, pd_, pa = outcome_probs(mat)
        p = {"home": ph, "draw": pd_, "away": pa}
        actual = actual_outcome(row["home_score"], row["away_score"])

        total_ll += log_loss(p, actual)
        if max(p, key=p.get) == actual:
            correct += 1

    n = len(tournament_matches)
    return {
        "log_loss": total_ll / n,
        "modal_acc": correct / n,
        "home_adv": fit_obj.home_advantage if fit_obj else 0,
        "rho": fit_obj.rho if fit_obj else 0,
        "n": n,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="data/results.csv")
    parser.add_argument("--tournament", default="FIFA World Cup")
    parser.add_argument("--years", type=int, nargs="+", default=[2018, 2022])
    parser.add_argument("--xi", type=float, nargs="+", default=[0.2, 0.3, 0.4, 0.5])
    parser.add_argument("--history", type=float, nargs="+", default=[4, 6, 8])
    parser.add_argument("--refit-every", type=int, default=8)
    args = parser.parse_args()

    print(f"Loading {args.csv} …")
    df = pd.read_csv(args.csv, na_values=["NA", "N/A", ""])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.dropna(subset=["home_score", "away_score"]).copy()
    df["home_score"] = df["home_score"].astype(int)
    df["away_score"] = df["away_score"].astype(int)
    print(f"  {len(df)} matches after cleaning")

    # Pull out each target tournament once
    targets = {}
    for year in args.years:
        sub = df[
            (df["tournament"] == args.tournament)
            & (pd.to_datetime(df["date"]).dt.year == year)
        ].sort_values("date").reset_index(drop=True)
        if len(sub):
            targets[year] = sub
            print(f"  {args.tournament} {year}: {len(sub)} matches")

    if not targets:
        print(f"No matches found for {args.tournament} in years {args.years}")
        return

    combos = list(product(args.xi, args.history))
    print(f"\nSweeping {len(combos)} combos × {len(targets)} tournaments = "
          f"{len(combos) * len(targets)} backtests …\n")

    header = f"{'xi':>5} {'hist':>6}  " + "  ".join(
        f"{y} ll   {y} acc " for y in targets.keys()
    ) + f"  {'mean ll':>8}"
    print(header)
    print("-" * len(header))

    rows = []
    for xi, history in combos:
        per_year = {}
        for year, matches in targets.items():
            res = run_one(df, matches, xi, history, args.refit_every)
            per_year[year] = res
        mean_ll = sum(r["log_loss"] for r in per_year.values()) / len(per_year)
        rows.append((xi, history, per_year, mean_ll))

        cells = "  ".join(
            f"{r['log_loss']:.4f}  {r['modal_acc']:.3f}" for r in per_year.values()
        )
        print(f"{xi:>5.2f} {history:>6.1f}  {cells}  {mean_ll:>8.4f}")

    # Best by mean log-loss
    rows.sort(key=lambda r: r[3])
    best_xi, best_hist, _, best_ll = rows[0]
    print("-" * len(header))
    print(f"\nWinner: xi={best_xi}, history={best_hist}, mean log-loss={best_ll:.4f}")
    print(f"Uniform baseline = {math.log(3):.4f} (anything below this beats guessing)")


if __name__ == "__main__":
    main()

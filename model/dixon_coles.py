"""
Dixon-Coles model for football score prediction.

Bivariate Poisson with a low-score correction (the rho parameter) that fixes
the standard Poisson's tendency to under-predict 1-1 and over-predict 0-0.

Reference: Dixon & Coles (1997), "Modelling Association Football Scores and
Inefficiencies in the Football Betting Market".

Trained with:
- Exponential time decay (xi) so recent matches weigh more than old ones.
- Per-tournament importance weights (World Cup > qualifiers > friendlies).
- L-BFGS-B optimization with warm starts for fast re-fitting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, Iterable, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize


# Tournament importance weights. Calibrated by hand from the backtest sweep;
# friendlies are noisy and should not dominate, but they carry *some* signal
# (especially for teams that don't play many competitive games).
TOURNAMENT_WEIGHTS: Dict[str, float] = {
    "FIFA World Cup": 1.0,
    "FIFA World Cup qualification": 0.7,
    "UEFA Euro": 0.9,
    "UEFA Euro qualification": 0.6,
    "Copa América": 0.9,
    "African Cup of Nations": 0.7,
    "AFC Asian Cup": 0.7,
    "CONCACAF Championship": 0.6,
    "CONCACAF Gold Cup": 0.6,
    "UEFA Nations League": 0.7,
    "Confederations Cup": 0.7,
    "Friendly": 0.3,
}
DEFAULT_TOURNAMENT_WEIGHT = 0.4


@dataclass
class DixonColesFit:
    """A fitted Dixon-Coles model. Pickle-friendly."""

    teams: list[str]
    attack: Dict[str, float]
    defense: Dict[str, float]
    home_advantage: float
    rho: float
    reference_date: date
    xi: float
    converged: bool
    log_likelihood: float
    params: np.ndarray = field(repr=False)  # for warm-starting next fit


def _tau(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    """Dixon-Coles low-score correction. Multiplies the bivariate Poisson."""
    if x == 0 and y == 0:
        return 1.0 - lam * mu * rho
    if x == 0 and y == 1:
        return 1.0 + lam * rho
    if x == 1 and y == 0:
        return 1.0 + mu * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def _time_weight(match_date: date, ref_date: date, xi: float) -> float:
    """Exponential decay: weight of a match decreases with age in years."""
    age_years = (ref_date - match_date).days / 365.25
    if age_years < 0:
        return 0.0
    return math.exp(-xi * age_years)


def _prepare(
    matches: pd.DataFrame,
    reference_date: date,
    xi: float,
    history_years: float,
) -> Tuple[pd.DataFrame, list[str]]:
    """Filter and weight the match history. Returns (df_with_weights, teams)."""
    df = matches.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date

    cutoff = date(reference_date.year - int(history_years), reference_date.month, reference_date.day)
    df = df[(df["date"] >= cutoff) & (df["date"] < reference_date)].copy()

    df["time_w"] = df["date"].apply(lambda d: _time_weight(d, reference_date, xi))
    df["tourn_w"] = df["tournament"].map(TOURNAMENT_WEIGHTS).fillna(DEFAULT_TOURNAMENT_WEIGHT)
    df["weight"] = df["time_w"] * df["tourn_w"]
    df = df[df["weight"] > 1e-6].copy()

    # Drop teams with too few weighted matches — they make the optimizer unstable.
    team_weight = pd.concat(
        [
            df.groupby("home_team")["weight"].sum(),
            df.groupby("away_team")["weight"].sum(),
        ]
    ).groupby(level=0).sum()
    keep_teams = set(team_weight[team_weight >= 1.5].index)
    df = df[df["home_team"].isin(keep_teams) & df["away_team"].isin(keep_teams)].copy()

    teams = sorted(set(df["home_team"]).union(df["away_team"]))
    return df.reset_index(drop=True), teams


def _neg_log_lik(
    params: np.ndarray,
    df: pd.DataFrame,
    team_idx: Dict[str, int],
    n_teams: int,
) -> float:
    """Weighted negative log-likelihood. Last 2 params are home_adv and rho."""
    attack = params[:n_teams]
    defense = params[n_teams : 2 * n_teams]
    home_adv = params[-2]
    rho = params[-1]

    # Hard constraint via penalty: sum(attack) == 0 (identifiability).
    pen = 1000.0 * (attack.mean() ** 2 + defense.mean() ** 2)

    h_idx = df["home_team"].map(team_idx).to_numpy()
    a_idx = df["away_team"].map(team_idx).to_numpy()
    neutral = df["neutral"].to_numpy()
    x = df["home_score"].to_numpy()
    y = df["away_score"].to_numpy()
    w = df["weight"].to_numpy()

    # Goal expectations
    home_factor = np.where(neutral, 0.0, home_adv)
    log_lam = attack[h_idx] - defense[a_idx] + home_factor
    log_mu = attack[a_idx] - defense[h_idx]
    lam = np.exp(log_lam)
    mu = np.exp(log_mu)

    # Poisson log-pmf
    # log P(X=x) = x*log(lam) - lam - log(x!)
    # log(x!) constant w.r.t. params for fixed data, but include it for stability
    from scipy.special import gammaln

    log_p_x = x * log_lam - lam - gammaln(x + 1)
    log_p_y = y * log_mu - mu - gammaln(y + 1)
    log_p = log_p_x + log_p_y

    # Dixon-Coles correction (vectorized)
    tau = np.ones_like(lam)
    mask_00 = (x == 0) & (y == 0)
    mask_01 = (x == 0) & (y == 1)
    mask_10 = (x == 1) & (y == 0)
    mask_11 = (x == 1) & (y == 1)
    tau[mask_00] = 1.0 - lam[mask_00] * mu[mask_00] * rho
    tau[mask_01] = 1.0 + lam[mask_01] * rho
    tau[mask_10] = 1.0 + mu[mask_10] * rho
    tau[mask_11] = 1.0 - rho
    # Clip to avoid log(<=0) blowing up the optimizer at extreme rho
    tau = np.clip(tau, 1e-10, None)
    log_p = log_p + np.log(tau)

    return -np.sum(w * log_p) + pen


def fit(
    matches: pd.DataFrame,
    reference_date: date,
    xi: float = 0.4,
    history_years: float = 4.0,
    warm_start: Optional[DixonColesFit] = None,
    max_iter: int = 200,
) -> DixonColesFit:
    """Fit a Dixon-Coles model. Pass a previous fit as warm_start for speed."""
    df, teams = _prepare(matches, reference_date, xi, history_years)
    if len(df) < 50 or len(teams) < 4:
        raise ValueError(f"Not enough data: {len(df)} matches, {len(teams)} teams")

    team_idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    # Initial params: zeros for attack/defense, 0.25 home advantage, -0.05 rho
    x0 = np.zeros(2 * n + 2)
    x0[-2] = 0.25
    x0[-1] = -0.05

    # Warm start: copy parameters for teams that overlap with the previous fit
    if warm_start is not None:
        for t, i in team_idx.items():
            if t in warm_start.attack:
                x0[i] = warm_start.attack[t]
                x0[n + i] = warm_start.defense[t]
        x0[-2] = warm_start.home_advantage
        x0[-1] = warm_start.rho

    bounds = (
        [(-3.0, 3.0)] * n          # attack
        + [(-3.0, 3.0)] * n        # defense
        + [(0.0, 1.0)]             # home advantage
        + [(-0.3, 0.3)]            # rho (Dixon-Coles correction)
    )

    res = minimize(
        _neg_log_lik,
        x0,
        args=(df, team_idx, n),
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": max_iter, "ftol": 1e-7},
    )

    p = res.x
    return DixonColesFit(
        teams=teams,
        attack={t: float(p[i]) for t, i in team_idx.items()},
        defense={t: float(p[n + i]) for t, i in team_idx.items()},
        home_advantage=float(p[-2]),
        rho=float(p[-1]),
        reference_date=reference_date,
        xi=xi,
        converged=bool(res.success),
        log_likelihood=float(-res.fun),
        params=p,
    )


def score_matrix(
    fit_obj: DixonColesFit,
    home_team: str,
    away_team: str,
    *,
    neutral: bool = True,
    max_goals: int = 8,
) -> np.ndarray:
    """Return P(home_goals=i, away_goals=j) matrix of shape (max_goals+1, max_goals+1).

    For knockout matches, this represents 90-minute scoreline probabilities.
    """
    if home_team not in fit_obj.attack or away_team not in fit_obj.attack:
        # Unknown team — uniform prior. Better than crashing.
        size = max_goals + 1
        return np.full((size, size), 1.0 / (size * size))

    home_factor = 0.0 if neutral else fit_obj.home_advantage
    log_lam = fit_obj.attack[home_team] - fit_obj.defense[away_team] + home_factor
    log_mu = fit_obj.attack[away_team] - fit_obj.defense[home_team]
    lam = math.exp(log_lam)
    mu = math.exp(log_mu)

    from scipy.stats import poisson

    p_h = poisson.pmf(np.arange(max_goals + 1), lam)
    p_a = poisson.pmf(np.arange(max_goals + 1), mu)
    mat = np.outer(p_h, p_a)

    # Apply Dixon-Coles correction to the four low-score cells
    rho = fit_obj.rho
    mat[0, 0] *= 1.0 - lam * mu * rho
    mat[0, 1] *= 1.0 + lam * rho
    mat[1, 0] *= 1.0 + mu * rho
    mat[1, 1] *= 1.0 - rho

    # Renormalize (correction can move total mass slightly off 1)
    mat /= mat.sum()
    return mat


def outcome_probs(matrix: np.ndarray) -> Tuple[float, float, float]:
    """From a score matrix, get (P(home win), P(draw), P(away win))."""
    n = matrix.shape[0]
    home = sum(matrix[i, j] for i in range(n) for j in range(n) if i > j)
    draw = sum(matrix[i, i] for i in range(n))
    away = sum(matrix[i, j] for i in range(n) for j in range(n) if i < j)
    return float(home), float(draw), float(away)


def expected_goals(matrix: np.ndarray) -> Tuple[float, float]:
    """Expected goals for each side from the score matrix."""
    n = matrix.shape[0]
    goals = np.arange(n)
    eh = float((matrix.sum(axis=1) * goals).sum())
    ea = float((matrix.sum(axis=0) * goals).sum())
    return eh, ea


def most_likely_score(matrix: np.ndarray) -> Tuple[int, int, float]:
    """Modal scoreline and its probability."""
    i, j = np.unravel_index(matrix.argmax(), matrix.shape)
    return int(i), int(j), float(matrix[i, j])

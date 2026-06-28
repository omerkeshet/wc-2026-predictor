"""
Monte Carlo simulator for the 2026 World Cup.

2026 format: 48 teams, 12 groups of 4. Top 2 from each group advance
automatically (24 teams), plus the 8 best third-placed teams (8 teams),
for a 32-team knockout starting at the Round of 32.

Knockouts: a single match. Tied at 90 → settled by simulating extra time
(scaled scoring rates) → penalties (50/50 coin flip, since the model has
nothing to say about penalty shootouts and the alternative is overfitting).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from .calibration import Calibration
from .dixon_coles import DixonColesFit, score_matrix, outcome_probs


@dataclass
class Group:
    name: str            # "A", "B", ...
    teams: List[str]     # 4 team names


@dataclass
class TournamentResult:
    """One Monte Carlo sample."""
    group_standings: Dict[str, List[Tuple[str, int, int, int]]]  # group → [(team, pts, gd, gf)]
    advance_round_of_32: List[str]
    winner: str
    runner_up: str
    semifinalists: List[str]
    quarterfinalists: List[str]


def _sample_score(
    fit_obj: DixonColesFit,
    home: str,
    away: str,
    calibration: Optional[Calibration] = None,
    max_goals: int = 8,
) -> Tuple[int, int]:
    """Sample a single match scoreline from the score-probability matrix."""
    mat = score_matrix(fit_obj, home, away, neutral=True, max_goals=max_goals)
    if calibration is not None:
        mat = calibration.apply(mat)
    flat = mat.flatten()
    idx = np.random.choice(len(flat), p=flat)
    i, j = np.unravel_index(idx, mat.shape)
    return int(i), int(j)


def _sample_knockout(
    fit_obj: DixonColesFit, team_a: str, team_b: str,
    calibration: Optional[Calibration] = None,
) -> Tuple[str, int, int]:
    """Sample a knockout match. Returns (winner, score_a, score_b).

    Score reflects 90 minutes only. If tied, extra time (scaled) and then
    a fair coin flip for penalties.
    """
    a, b = _sample_score(fit_obj, team_a, team_b, calibration=calibration)
    if a != b:
        return (team_a if a > b else team_b, a, b)

    # Extra time: 30 minutes = 1/3 of regulation, scale Poisson rates.
    if team_a in fit_obj.attack and team_b in fit_obj.attack:
        log_lam = fit_obj.attack[team_a] - fit_obj.defense[team_b]
        log_mu = fit_obj.attack[team_b] - fit_obj.defense[team_a]
        lam_et = math.exp(log_lam) / 3.0
        mu_et = math.exp(log_mu) / 3.0
        et_a = int(np.random.poisson(lam_et))
        et_b = int(np.random.poisson(mu_et))
        a += et_a
        b += et_b
        if a != b:
            return (team_a if a > b else team_b, a, b)

    # Penalty shootout: 50/50. Anything fancier would be made up.
    return (team_a if random.random() < 0.5 else team_b, a, b)


def _play_group(
    fit_obj: DixonColesFit,
    group: Group,
    calibration: Optional[Calibration] = None,
) -> List[Tuple[str, int, int, int]]:
    """Simulate a group: every team plays every other team once.

    Returns sorted standings: [(team, points, goal_diff, goals_for), ...].
    """
    pts = {t: 0 for t in group.teams}
    gf = {t: 0 for t in group.teams}
    ga = {t: 0 for t in group.teams}

    for i in range(len(group.teams)):
        for j in range(i + 1, len(group.teams)):
            t1, t2 = group.teams[i], group.teams[j]
            s1, s2 = _sample_score(fit_obj, t1, t2, calibration=calibration)
            gf[t1] += s1
            gf[t2] += s2
            ga[t1] += s2
            ga[t2] += s1
            if s1 > s2:
                pts[t1] += 3
            elif s2 > s1:
                pts[t2] += 3
            else:
                pts[t1] += 1
                pts[t2] += 1

    rows = [(t, pts[t], gf[t] - ga[t], gf[t]) for t in group.teams]
    # Tiebreak: points, then goal difference, then goals for, then random.
    rows.sort(key=lambda r: (r[1], r[2], r[3], random.random()), reverse=True)
    return rows


def _simulate_once(
    fit_obj: DixonColesFit,
    groups: List[Group],
    calibration: Optional[Calibration] = None,
) -> TournamentResult:
    """One full Monte Carlo sample of the tournament."""
    standings = {g.name: _play_group(fit_obj, g, calibration=calibration) for g in groups}

    # Top 2 from each group → 24 teams
    advancing: List[Tuple[str, str]] = []  # (group_name, team)
    third_place: List[Tuple[str, int, int, int]] = []
    for gname, rows in standings.items():
        advancing.append((gname, rows[0][0]))
        advancing.append((gname, rows[1][0]))
        if len(rows) >= 3:
            third_place.append((gname,) + rows[2])  # type: ignore

    # 8 best third-placed teams → 32 teams
    third_place.sort(key=lambda r: (r[2], r[3], r[4], random.random()), reverse=True)
    for entry in third_place[:8]:
        advancing.append((entry[0], entry[1]))

    advancing_teams = [t for _, t in advancing]

    # Knockout bracket: shuffle for fairness across many sims (real bracket
    # depends on draw, but on average over many sims the pairing distribution
    # converges). For known draws, slot in the seeding logic here.
    bracket = list(advancing_teams)
    random.shuffle(bracket)

    # Round of 32 → 16 → QF → SF → Final
    round_of_32 = list(bracket)
    round_of_16: List[str] = []
    for k in range(0, len(round_of_32), 2):
        winner, _, _ = _sample_knockout(fit_obj, round_of_32[k], round_of_32[k + 1], calibration)
        round_of_16.append(winner)

    quarterfinalists: List[str] = []
    for k in range(0, len(round_of_16), 2):
        winner, _, _ = _sample_knockout(fit_obj, round_of_16[k], round_of_16[k + 1], calibration)
        quarterfinalists.append(winner)

    semifinalists: List[str] = []
    for k in range(0, len(quarterfinalists), 2):
        winner, _, _ = _sample_knockout(fit_obj, quarterfinalists[k], quarterfinalists[k + 1], calibration)
        semifinalists.append(winner)

    finalists: List[str] = []
    for k in range(0, len(semifinalists), 2):
        winner, _, _ = _sample_knockout(fit_obj, semifinalists[k], semifinalists[k + 1], calibration)
        finalists.append(winner)

    winner, _, _ = _sample_knockout(fit_obj, finalists[0], finalists[1], calibration)
    runner_up = finalists[1] if winner == finalists[0] else finalists[0]

    return TournamentResult(
        group_standings=standings,
        advance_round_of_32=advancing_teams,
        winner=winner,
        runner_up=runner_up,
        semifinalists=semifinalists,
        quarterfinalists=quarterfinalists,
    )


def simulate(
    fit_obj: DixonColesFit,
    groups: List[Group],
    n_sims: int = 5000,
    seed: Optional[int] = None,
    calibration: Optional[Calibration] = None,
) -> Dict[str, Dict[str, float]]:
    """Run n_sims Monte Carlo samples and aggregate probabilities per team.

    Returns: {team: {"advance_r32": p, "qf": p, "sf": p, "final": p, "win": p}}
    """
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    all_teams = [t for g in groups for t in g.teams]
    counts = {
        t: {"advance_r32": 0, "qf": 0, "sf": 0, "final": 0, "win": 0}
        for t in all_teams
    }

    for _ in range(n_sims):
        result = _simulate_once(fit_obj, groups, calibration=calibration)
        for t in result.advance_round_of_32:
            counts[t]["advance_r32"] += 1
        for t in result.quarterfinalists:
            counts[t]["qf"] += 1
        for t in result.semifinalists:
            counts[t]["sf"] += 1
        counts[result.winner]["final"] += 1
        counts[result.runner_up]["final"] += 1
        counts[result.winner]["win"] += 1

    return {
        t: {k: v / n_sims for k, v in c.items()} for t, c in counts.items()
    }

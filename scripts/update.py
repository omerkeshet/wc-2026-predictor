"""
Daily update pipeline.

Run order:
1. Load historical dataset (results.csv).
2. Merge in any new results from api-football for the current cycle.
3. Refit the Dixon-Coles model with the latest data.
4. Generate per-match predictions for upcoming fixtures.
5. Run a Monte Carlo tournament simulation.
6. Write JSON files to frontend/public/data/ for the static site to read.

Designed to run on a schedule (twice daily is plenty for a tournament).
Idempotent — running twice in a row produces the same output.

Usage:
    python -m scripts.update                # use today's date
    python -m scripts.update --date 2026-06-15
    python -m scripts.update --no-api       # skip api-football, use only CSV
    python -m scripts.update --sims 5000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# Make the package importable when running as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from model import (
    Calibration,
    DixonColesFit,
    Group,
    expected_goals,
    fit,
    most_likely_score,
    outcome_probs,
    score_matrix,
    simulate,
)


# 2026 World Cup groups — REPLACE WITH THE REAL DRAW BEFORE LAUNCH.
# Source: https://www.fifa.com/fifaplus/en/tournaments/mens/worldcup/canadamexicousa2026
# These placeholders are the qualified teams roughly seeded by recent strength;
# you must overwrite them with the official draw.
# Official 2026 World Cup groups — set by the Final Draw on Dec 5, 2025,
# completed after the playoff finals on Mar 31, 2026.
# Source: FIFA / cross-referenced with multiple outlets.
GROUPS_2026: List[Group] = [
    Group("A", ["Mexico", "South Africa", "South Korea", "Czech Republic"]),
    Group("B", ["Canada", "Bosnia and Herzegovina", "Qatar", "Switzerland"]),
    Group("C", ["Brazil", "Morocco", "Haiti", "Scotland"]),
    Group("D", ["United States", "Paraguay", "Australia", "Turkey"]),
    Group("E", ["Germany", "Curaçao", "Ivory Coast", "Ecuador"]),
    Group("F", ["Netherlands", "Japan", "Sweden", "Tunisia"]),
    Group("G", ["Belgium", "Egypt", "Iran", "New Zealand"]),
    Group("H", ["Spain", "Cape Verde", "Saudi Arabia", "Uruguay"]),
    Group("I", ["France", "Senegal", "Iraq", "Norway"]),
    Group("J", ["Argentina", "Algeria", "Austria", "Jordan"]),
    Group("K", ["Portugal", "DR Congo", "Uzbekistan", "Colombia"]),
    Group("L", ["England", "Croatia", "Ghana", "Panama"]),
]


def _validate_groups(groups: List[Group]) -> None:
    """Catch obvious bugs in the group definitions before we simulate."""
    seen: Dict[str, str] = {}
    for g in groups:
        if len(g.teams) != 4:
            raise ValueError(f"Group {g.name} has {len(g.teams)} teams, expected 4")
        for t in g.teams:
            if t in seen:
                raise ValueError(f"Team '{t}' appears in groups {seen[t]} and {g.name}")
            seen[t] = g.name
    if len(groups) != 12:
        raise ValueError(f"Expected 12 groups, got {len(groups)}")


def load_historical(path: str = "data/results.csv") -> pd.DataFrame:
    """Load historical match results from a CSV.

    Filters out:
      - Future fixtures (date >= today)
      - Rows with missing scores (some CSVs encode unplayed matches as 'NA')

    The score columns are explicitly read with na_values=['NA', ''] so that
    string sentinels become real NaNs we can drop, regardless of whether the
    source CSV uses pandas' default sentinels or its own.
    """
    df = pd.read_csv(path, na_values=["NA", "N/A", ""])
    df["date"] = pd.to_datetime(df["date"]).dt.date

    # Drop unplayed fixtures: anything dated today or later, plus any straggler
    # rows where the score is still missing despite an old date (data quality).
    today = date.today()
    n_before = len(df)
    df = df[df["date"] < today].copy()
    df = df.dropna(subset=["home_score", "away_score"]).copy()
    df["home_score"] = df["home_score"].astype(int)
    df["away_score"] = df["away_score"].astype(int)
    n_dropped = n_before - len(df)
    if n_dropped > 0:
        print(f"      filtered out {n_dropped} future/unplayed matches")

    return df


def merge_new_results(df: pd.DataFrame, use_api: bool, since: date) -> pd.DataFrame:
    """If the API is enabled, pull recent fixtures and append any that aren't already in the CSV."""
    if not use_api:
        return df

    try:
        from api import from_env
        client = from_env()
    except Exception as exc:
        print(f"  api-football unavailable ({exc}); proceeding with CSV only.")
        return df

    # Pull recent fixtures across all leagues that affect national teams.
    # The free tier doesn't let you query "all national-team fixtures" cheaply,
    # so for the daily cycle we pull World Cup + WC qualification fixtures
    # in the current and prior season.
    new_rows = []
    try:
        for season in (since.year - 1, since.year):
            for league_id in (1, 32, 4):  # WC, WC qualification Europe, Euro
                fixtures = client.fixtures(
                    league=league_id, season=season, status="FT",
                    from_date=since.replace(year=since.year - 1)
                )
                for f in fixtures:
                    fdate = pd.to_datetime(f["fixture"]["date"]).date()
                    home = f["teams"]["home"]["name"]
                    away = f["teams"]["away"]["name"]
                    hs = f["goals"]["home"]
                    aw = f["goals"]["away"]
                    if hs is None or aw is None:
                        continue
                    new_rows.append({
                        "date": fdate,
                        "home_team": home,
                        "away_team": away,
                        "home_score": int(hs),
                        "away_score": int(aw),
                        "tournament": f["league"]["name"],
                        "city": (f["fixture"]["venue"] or {}).get("city") or "",
                        "country": "",
                        "neutral": False,
                    })
    except Exception as exc:
        print(f"  api-football fetch failed ({exc}); proceeding with CSV only.")
        return df

    if not new_rows:
        print(f"  api-football: 0 new fixtures.")
        return df

    new_df = pd.DataFrame(new_rows)
    # Drop any rows already present (date + teams = effective primary key)
    key = ["date", "home_team", "away_team"]
    merged = pd.concat([df, new_df], ignore_index=True).drop_duplicates(subset=key, keep="first")
    added = len(merged) - len(df)
    print(f"  api-football: {added} new fixtures merged ({client.quota_used_today()} req used today).")
    return merged


def predict_upcoming(
    fit_obj: DixonColesFit,
    upcoming: List[Dict[str, Any]],
    calibration: Optional[Calibration] = None,
) -> List[Dict[str, Any]]:
    """For each upcoming fixture, produce a full prediction record."""
    out = []
    for fx in upcoming:
        home, away = fx["home"], fx["away"]
        is_neutral = fx.get("neutral", True)
        mat = score_matrix(fit_obj, home, away, neutral=is_neutral, max_goals=6)
        if calibration is not None:
            mat = calibration.apply(mat)
        p_home, p_draw, p_away = outcome_probs(mat)
        eh, ea = expected_goals(mat)
        i, j, p_modal = most_likely_score(mat)
        out.append({
            "id": fx.get("id"),
            "date": fx["date"],
            "home": home,
            "away": away,
            "neutral": is_neutral,
            "stage": fx.get("stage", "group"),
            "group": fx.get("group"),
            "probs": {"home": p_home, "draw": p_draw, "away": p_away},
            "expected_goals": {"home": eh, "away": ea},
            "modal_score": {"home": i, "away": j, "p": p_modal},
            "score_matrix": mat.tolist(),  # 7x7
        })
    return out


def write_outputs(
    out_dir: Path,
    fit_obj: DixonColesFit,
    matches: List[Dict[str, Any]],
    tournament_probs: Dict[str, Dict[str, float]],
    groups: List[Group],
    meta: Dict[str, Any],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # ratings.json — full team ratings, sorted by overall strength.
    ratings = []
    for team in fit_obj.teams:
        ratings.append({
            "team": team,
            "attack": fit_obj.attack[team],
            "defense": fit_obj.defense[team],
            "overall": fit_obj.attack[team] + fit_obj.defense[team],
        })
    ratings.sort(key=lambda r: r["overall"], reverse=True)
    with open(out_dir / "ratings.json", "w") as f:
        json.dump({
            "home_advantage": fit_obj.home_advantage,
            "rho": fit_obj.rho,
            "reference_date": str(fit_obj.reference_date),
            "ratings": ratings,
        }, f, indent=2)

    # matches.json — one prediction per upcoming fixture
    with open(out_dir / "matches.json", "w") as f:
        json.dump({"matches": matches}, f, indent=2)

    # tournament.json — Monte Carlo aggregates per team
    contenders = []
    for t, probs in tournament_probs.items():
        contenders.append({"team": t, **probs})
    contenders.sort(key=lambda r: r["win"], reverse=True)
    with open(out_dir / "tournament.json", "w") as f:
        json.dump({
            "groups": [{"name": g.name, "teams": g.teams} for g in groups],
            "contenders": contenders,
        }, f, indent=2)

    # meta.json — when did we last update, what's the model state
    with open(out_dir / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Reference date (YYYY-MM-DD). Default: today.")
    parser.add_argument("--csv", default="data/results.csv")
    parser.add_argument("--out", default="frontend/public/data")
    parser.add_argument("--sims", type=int, default=3000)
    parser.add_argument("--xi", type=float, default=0.2,
                        help="Time-decay rate. Empirically best at 0.2 (from sweep on 2018+2022 WCs).")
    parser.add_argument("--history", type=float, default=8.0,
                        help="Years of history to include. Empirically best at 8 (from sweep on 2018+2022 WCs).")
    parser.add_argument("--no-api", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    ref_date = (
        datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date else date.today()
    )

    _validate_groups(GROUPS_2026)

    print(f"[1/5] Loading historical matches from {args.csv} …")
    df = load_historical(args.csv)
    print(f"      {len(df)} matches, {df['date'].min()}..{df['date'].max()}")

    print(f"[2/5] Merging new results (api-football {'OFF' if args.no_api else 'ON'}) …")
    df = merge_new_results(df, use_api=not args.no_api, since=ref_date)

    print(f"[3/5] Fitting Dixon-Coles (ref={ref_date}, xi={args.xi}, history={args.history}y) …")
    fit_obj = fit(df, reference_date=ref_date, xi=args.xi, history_years=args.history)
    print(f"      converged={fit_obj.converged}, "
          f"log_lik={fit_obj.log_likelihood:.1f}, "
          f"home_adv={fit_obj.home_advantage:.3f}, "
          f"rho={fit_obj.rho:.3f}, "
          f"teams={len(fit_obj.teams)}")

    # Load calibration if it's been trained. No file → use identity (k=1.0).
    calibration_path = Path(args.out) / "calibration.json"
    calibration = Calibration.load(calibration_path) or Calibration.identity()
    if calibration.k == 1.0:
        print(f"      [calibration] none found, using raw model probabilities")
    else:
        print(f"      [calibration] applied k={calibration.k:.3f} from {calibration.source_file}")

    print(f"[4/5] Predicting upcoming fixtures …")
    # For the baseline, just predict every intra-group match of the 2026 groups.
    # When real fixtures load from the API, swap these in.
    upcoming = []
    for g in GROUPS_2026:
        for i in range(len(g.teams)):
            for j in range(i + 1, len(g.teams)):
                upcoming.append({
                    "date": str(ref_date),
                    "home": g.teams[i],
                    "away": g.teams[j],
                    "neutral": True,
                    "stage": "group",
                    "group": g.name,
                })
    matches = predict_upcoming(fit_obj, upcoming, calibration=calibration)
    print(f"      {len(matches)} fixtures predicted")

    print(f"[5/5] Simulating tournament ({args.sims} samples) …")
    tournament = simulate(fit_obj, GROUPS_2026, n_sims=args.sims, seed=args.seed,
                          calibration=calibration)

    meta = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "reference_date": str(ref_date),
        "model": "dixon-coles",
        "xi": args.xi,
        "history_years": args.history,
        "n_simulations": args.sims,
        "n_matches_trained_on": int((df["date"] < ref_date).sum()),
        "converged": fit_obj.converged,
        "calibration_k": calibration.k,
    }

    out_dir = Path(args.out)
    write_outputs(out_dir, fit_obj, matches, tournament, GROUPS_2026, meta)
    print(f"      wrote {out_dir}/")
    print("Done.")


if __name__ == "__main__":
    main()

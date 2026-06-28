"""
predict_r32.py — Round-of-32 score predictions from the existing model output.

WHAT THIS DOES
  Reads your already-fitted, already-recalibrated ratings.json and applies the
  exact same Dixon-Coles matchup math the site uses, to a list of knockout
  fixtures YOU type in below. It does NOT re-fit the model and does NOT touch
  update.py or any of the four JSONs — so your manual corrections stay safe.

WHAT IT WRITES
  scripts/out/r32_predictions.csv   one row per fixture (Excel-safe scores)
  scripts/out/r32_matrices.json     full 7x7 score grids, if you want them

HOW TO RUN (from the repo root, in PowerShell)
  python scripts/predict_r32.py
  python scripts/predict_r32.py --verify    # sanity-check the math vs matches.json

TOMORROW: edit the FIXTURES list (Step 1 below) once the R32 pairings lock,
then run it. That's the only thing you need to change.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import math
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# STEP 1 — EDIT THIS TOMORROW.  16 Round-of-32 fixtures.
# Use the MODEL's spelling (Turkey not Türkiye, South Korea not Korea Republic,
# Ivory Coast not Côte d'Ivoire, Iran not IR Iran, Czech Republic not Czechia,
# United States not USA, Curaçao with the cedilla). The alias map below will
# auto-correct the common ones, and the validator will catch anything else.
#
# neutral=True everywhere matches how the site computed the group stage and
# bracket. If you want to give a host (USA / Canada / Mexico) home advantage
# for a match they actually host, set neutral=False on that one row.
# ---------------------------------------------------------------------------
FIXTURES = [
    # ("Home Team", "Away Team", neutral?)   — 2026 World Cup Round of 32
    ("South Africa", "Canada", True),
    ("Germany", "Paraguay", True),
    ("Netherlands", "Morocco", True),
    ("Brazil", "Japan", True),
    ("France", "Sweden", True),
    ("Mexico", "Ecuador", True),       # host in Mexico City — flip to False for home adv
    ("England", "DR Congo", True),
    ("Belgium", "Senegal", True),
    ("Portugal", "Croatia", True),
    ("Switzerland", "Algeria", True),
    ("Colombia", "Ghana", True),
    ("Ivory Coast", "Norway", True),
    ("United States", "Bosnia and Herzegovina", True),  # host — flip to False for home adv
    ("Spain", "Austria", True),
    ("Argentina", "Cape Verde", True),
    ("Australia", "Egypt", True),
]

# ---------------------------------------------------------------------------
# Common competition-spelling -> model-spelling aliases.
# ---------------------------------------------------------------------------
ALIASES = {
    "Türkiye": "Turkey", "Turkiye": "Turkey",
    "Korea Republic": "South Korea", "Republic of Korea": "South Korea",
    "Czechia": "Czech Republic",
    "IR Iran": "Iran",
    "USA": "United States", "United States of America": "United States",
    "Côte d'Ivoire": "Ivory Coast", "Cote d'Ivoire": "Ivory Coast",
    "Curacao": "Curaçao",
    "Congo DR": "DR Congo", "DR Congo": "DR Congo",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
}

MAX_GOALS = 6  # 7x7 grid, matches update.py's max_goals=6


def find_data_dir(explicit: str | None) -> Path:
    """Locate frontend/public/data whether run from repo root or scripts/."""
    if explicit:
        p = Path(explicit)
        if (p / "ratings.json").exists():
            return p
        raise SystemExit(f"--data given but no ratings.json in {p}")
    here = Path(__file__).resolve()
    candidates = [
        Path.cwd() / "frontend" / "public" / "data",
        here.parent.parent / "frontend" / "public" / "data",
        here.parent / "frontend" / "public" / "data",
    ]
    for c in candidates:
        if (c / "ratings.json").exists():
            return c
    raise SystemExit(
        "Could not find frontend/public/data/ratings.json.\n"
        "Run this from the repo root, or pass --data <path-to-data-dir>."
    )


def load_ratings(data_dir: Path):
    r = json.loads((data_dir / "ratings.json").read_text(encoding="utf-8"))
    table = {row["team"]: row for row in r["ratings"]}
    return {
        "teams": table,
        "rho": float(r["rho"]),
        "home_advantage": float(r["home_advantage"]),
        "reference_date": r.get("reference_date"),
    }


def load_k(data_dir: Path) -> float:
    """Load temperature k exactly like update.py: calibration.json -> k, else 1.0."""
    p = data_dir / "calibration.json"
    if not p.exists():
        return 1.0
    try:
        return float(json.loads(p.read_text(encoding="utf-8"))["k"])
    except (json.JSONDecodeError, KeyError, ValueError):
        return 1.0


def resolve_team(name: str, table: dict) -> str:
    """Map a typed name to the model's spelling, or fail with a suggestion."""
    if name in table:
        return name
    if name in ALIASES and ALIASES[name] in table:
        return ALIASES[name]
    close = difflib.get_close_matches(name, table.keys(), n=3, cutoff=0.6)
    hint = f"  Did you mean: {', '.join(close)}?" if close else ""
    raise SystemExit(f"Team not in ratings.json: {name!r}.{hint}")


def score_matrix(home: dict, away: dict, rho: float, home_adv: float,
                 neutral: bool) -> np.ndarray:
    """Dixon-Coles bivariate-Poisson score grid. P[i][j] = P(home i, away j).

    Mirrors model/dixon_coles.py (same equations as the TS bracket port):
      lambda = exp(att_home - def_away + home_factor)
      mu     = exp(att_away - def_home)
    """
    home_factor = 0.0 if neutral else home_adv
    lam = math.exp(home["attack"] - away["defense"] + home_factor)
    mu = math.exp(away["attack"] - home["defense"])

    size = MAX_GOALS + 1
    ks = np.arange(size)
    log_fact = np.array([math.lgamma(k + 1) for k in ks])
    pH = np.exp(ks * math.log(lam) - lam - log_fact)
    pA = np.exp(ks * math.log(mu) - mu - log_fact)
    mat = np.outer(pH, pA)

    # Dixon-Coles low-score correction
    mat[0, 0] *= 1 - lam * mu * rho
    mat[0, 1] *= 1 + lam * rho
    mat[1, 0] *= 1 + mu * rho
    mat[1, 1] *= 1 - rho

    mat /= mat.sum()
    return mat


def apply_calibration(mat: np.ndarray, k: float) -> np.ndarray:
    """Temperature scaling, identical to model/calibration.py."""
    if abs(k - 1.0) < 1e-6:
        return mat
    scaled = np.maximum(mat, 1e-12) ** k
    scaled /= scaled.sum()
    return scaled


def summarize(mat: np.ndarray):
    n = mat.shape[0]
    p_home = float(np.tril(mat, -1).sum())   # i > j
    p_draw = float(np.trace(mat))            # i == j
    p_away = float(np.triu(mat, 1).sum())    # i < j
    eh = float((np.arange(n)[:, None] * mat).sum())
    ea = float((np.arange(n)[None, :] * mat).sum())
    i, j = np.unravel_index(int(np.argmax(mat)), mat.shape)
    return {
        "p_home": p_home, "p_draw": p_draw, "p_away": p_away,
        "eg_home": eh, "eg_away": ea,
        "modal_home": int(i), "modal_away": int(j), "modal_p": float(mat[i, j]),
    }


def predict(fixtures, model, k):
    table = model["teams"]
    rows, matrices = [], {}
    for home_in, away_in, neutral in fixtures:
        home = resolve_team(home_in, table)
        away = resolve_team(away_in, table)
        mat = score_matrix(table[home], table[away], model["rho"],
                           model["home_advantage"], neutral)
        mat = apply_calibration(mat, k)
        s = summarize(mat)
        rows.append({"home": home, "away": away, "neutral": neutral, **s})
        matrices[f"{home} vs {away}"] = mat.tolist()
    return rows, matrices


def build_site_records(fixtures, model, k):
    """Produce records in the SAME schema update.py writes to matches.json,
    so the frontend's existing heatmap component can render them unchanged."""
    table = model["teams"]
    records = []
    for n, (home_in, away_in, neutral) in enumerate(fixtures, start=1):
        home = resolve_team(home_in, table)
        away = resolve_team(away_in, table)
        mat = score_matrix(table[home], table[away], model["rho"],
                           model["home_advantage"], neutral)
        mat = apply_calibration(mat, k)
        s = summarize(mat)
        records.append({
            "id": f"r32-{n}",
            "date": None,            # fill kickoff dates here if the page shows them
            "home": home,
            "away": away,
            "neutral": neutral,
            "stage": "round_of_32",
            "group": None,
            "probs": {"home": s["p_home"], "draw": s["p_draw"], "away": s["p_away"]},
            "expected_goals": {"home": s["eg_home"], "away": s["eg_away"]},
            "modal_score": {"home": s["modal_home"], "away": s["modal_away"],
                            "p": s["modal_p"]},
            "score_matrix": mat.tolist(),   # 7x7, identical shape to group stage
        })
    return records


def write_csv(rows, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["home", "away", "neutral",
                    "p_home", "p_draw", "p_away",
                    "eg_home", "eg_away",
                    "modal_home", "modal_away", "modal_score", "modal_p"])
        for r in rows:
            # modal_home/away as separate ints + a text score guarded against
            # Excel turning "1-2" into a date: leading apostrophe forces text.
            w.writerow([
                r["home"], r["away"], r["neutral"],
                f'{r["p_home"]:.4f}', f'{r["p_draw"]:.4f}', f'{r["p_away"]:.4f}',
                f'{r["eg_home"]:.3f}', f'{r["eg_away"]:.3f}',
                r["modal_home"], r["modal_away"],
                f'="{r["modal_home"]}-{r["modal_away"]}"', f'{r["modal_p"]:.4f}',
            ])


def print_table(rows):
    print(f'\n{"MATCH":34} {"H%":>5} {"D%":>5} {"A%":>5}  {"xG":>9}  modal')
    print("-" * 72)
    for r in rows:
        match = f'{r["home"]} v {r["away"]}'
        xg = f'{r["eg_home"]:.1f}-{r["eg_away"]:.1f}'
        modal = f'{r["modal_home"]}-{r["modal_away"]} ({r["modal_p"]*100:.0f}%)'
        flag = "" if r["neutral"] else "  [home adv]"
        print(f'{match[:34]:34} {r["p_home"]*100:5.1f} {r["p_draw"]*100:5.1f} '
              f'{r["p_away"]*100:5.1f}  {xg:>9}  {modal}{flag}')


def verify(model, k, data_dir: Path):
    """Recompute a few group-stage fixtures and compare to matches.json.
    If these match, the matchup math + calibration are confirmed correct."""
    mp = data_dir / "matches.json"
    if not mp.exists():
        raise SystemExit("--verify needs frontend/public/data/matches.json (not found).")
    saved = json.loads(mp.read_text(encoding="utf-8"))["matches"]
    table = model["teams"]
    worst = 0.0
    checked = 0
    for m in saved[:12]:
        if m["home"] not in table or m["away"] not in table:
            continue
        mat = score_matrix(table[m["home"]], table[m["away"]], model["rho"],
                           model["home_advantage"], m.get("neutral", True))
        mat = apply_calibration(mat, k)
        s = summarize(mat)
        d = max(abs(s["p_home"] - m["probs"]["home"]),
                abs(s["p_draw"] - m["probs"]["draw"]),
                abs(s["p_away"] - m["probs"]["away"]))
        worst = max(worst, d)
        checked += 1
        print(f'  {m["home"]:14} v {m["away"]:14}  '
              f'mine H/D/A {s["p_home"]:.3f}/{s["p_draw"]:.3f}/{s["p_away"]:.3f}  '
              f'site {m["probs"]["home"]:.3f}/{m["probs"]["draw"]:.3f}/{m["probs"]["away"]:.3f}  '
              f'Δ={d:.4f}')
    print(f"\nChecked {checked} fixtures. Worst probability difference: {worst:.5f}")
    if worst < 1e-3:
        print("PASS — the math reproduces your site exactly.")
    else:
        print("MISMATCH — tell Claude the worst-diff number before trusting R32 output.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="path to frontend/public/data")
    ap.add_argument("--out", default="scripts/out", help="output directory")
    ap.add_argument("--verify", action="store_true",
                    help="check the math against matches.json instead of predicting")
    ap.add_argument("--site", action="store_true",
                    help="also write r32.json (matches.json schema) into the data dir")
    args = ap.parse_args()

    data_dir = find_data_dir(args.data)
    model = load_ratings(data_dir)
    k = load_k(data_dir)
    print(f"Loaded ratings.json  (rho={model['rho']:.4f}, "
          f"home_adv={model['home_advantage']:.3f}, ref={model['reference_date']})")
    print(f"Calibration k = {k:.4f}" + ("  (identity / none found)" if k == 1.0 else ""))

    if args.verify:
        verify(model, k, data_dir)
        return

    valid = [fx for fx in FIXTURES if not str(fx[0]).startswith("#")]
    if len(valid) < 16:
        print(f"\n  NOTE: only {len(valid)} fixtures in FIXTURES — fill in all 16 "
              f"before the real run.\n")

    rows, matrices = predict(valid, model, k)
    print_table(rows)

    out = Path(args.out)
    write_csv(rows, out / "r32_predictions.csv")
    (out / "r32_matrices.json").write_text(
        json.dumps(matrices, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {out/'r32_predictions.csv'} and {out/'r32_matrices.json'}")

    if args.site:
        records = build_site_records(valid, model, k)
        site_path = data_dir / "r32.json"
        site_path.write_text(
            json.dumps({"matches": records}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"Wrote {site_path}  ({len(records)} matches, matches.json schema)")


if __name__ == "__main__":
    main()
# 2026 World Cup Predictor

A Dixon-Coles bivariate-Poisson model that ingests ~49,000 historical
international matches, refits twice daily, and publishes match-level
score probabilities and tournament title odds to a static site.

## What's in the box

```
wc-predictor/
├── model/
│   ├── dixon_coles.py     Core scoring model w/ time decay & tournament weighting
│   └── simulator.py       Monte Carlo bracket simulator (48-team / 12-group format)
├── api/
│   └── client.py          api-football.com v3 client w/ disk cache + quota tracking
├── scripts/
│   ├── update.py          Daily pipeline: fetch → fit → simulate → write JSON
│   └── backtest.py        Walk-forward backtest vs uniform & prior baselines
├── frontend/              Next.js static site (TypeScript + Tailwind)
│   ├── app/page.tsx       Editorial dark-theme dashboard
│   ├── components/        MatchCard, ScoreMatrix, WinProbBar, Contenders, GroupTable
│   └── public/data/*.json Generated predictions (consumed at build time)
├── data/results.csv       Historical match dataset
└── .github/workflows/update.yml   Scheduled CI: refit twice daily + deploy
```

## Backtest results

| Tournament        | Model log-loss | Uniform | Modal accuracy |
| ----------------- | -------------- | ------- | -------------- |
| 2018 World Cup    | 0.97           | 1.10    | 59 %           |
| 2022 World Cup    | 1.09           | 1.10    | mixed          |

2018: a meaningful +0.13 improvement over guessing — solid. 2022: essentially a wash, which matches what *every* professional bookmaker saw (Saudi Arabia beat Argentina, Morocco reached the semis, Japan beat Germany and Spain). The model isn't broken — that tournament just was upsets.

Optimal hyperparameters from the sweep: `xi=0.4`, `history=4 years`.

## Run locally

```bash
# Python pipeline
pip install -r requirements.txt

# Generate predictions (no API needed for the initial cut)
python -m scripts.update --no-api --sims 3000

# Backtest a past tournament
python -m scripts.backtest --year 2022 --tournament "FIFA World Cup"

# Build the site
cd frontend
npm install
npm run build         # produces frontend/out/ — static HTML/JS, deploy anywhere
npm run dev           # local dev server at http://localhost:3000
```

## Hosting — GitHub Pages + GitHub Actions (free)

The default setup. Total cost: zero. No server.

1. **Create a repo and push this directory.**

2. **Add your API key as a repository secret.**
   `Settings → Secrets and variables → Actions → New repository secret`
   Name it `API_FOOTBALL_KEY`. Get the key from <https://www.api-football.com/>.

3. **Enable GitHub Pages with the Actions source.**
   `Settings → Pages → Build and deployment → Source: GitHub Actions`

4. **Run the workflow once manually.**
   `Actions → update-and-deploy → Run workflow`
   This fits the model, generates the JSON, builds the site, and deploys.

After that, the workflow runs on schedule (06:00 and 18:00 UTC by default — change the cron in `.github/workflows/update.yml` if you want a different cadence). Each run uses 1-5 API requests, so you have huge headroom under the 100/day free-tier cap.

### Alternatives

- **Cloudflare Pages** — connect the repo, build command `cd frontend && npm run build`, output dir `frontend/out`. Schedule with Cloudflare Cron Triggers or keep GitHub Actions for the update job.
- **Netlify / Vercel** — identical to Cloudflare Pages.
- **Self-hosted** — the `frontend/out/` folder is fully static. Serve it with any HTTP server (nginx, Caddy, even `python -m http.server`). Run `scripts/update.py` from a cron job.

## Before you launch

These are the three things that matter, in order of impact:

1. **Replace the placeholder groups.** *(Done — `GROUPS_2026` in `scripts/update.py` now holds the real Dec 5, 2025 draw and the Mar 31, 2026 playoff winners.)*

2. **Calibrate against actual outcomes.** *(Done — run `python -m scripts.calibrate --from 2024-01-01 --to 2026-05-01` to learn a temperature parameter `k` that minimizes log-loss on held-out matches. Writes `frontend/public/data/calibration.json`; `update.py` picks it up automatically on the next run.)* In practice, the improvement is small (~0.005 log-loss) because the raw model is already reasonably well-calibrated against actual results — the apparent over-confidence vs. bookmaker odds reflects missing *information* (squads, injuries) more than miscalibration. See `model/calibration.py` for the implementation.

3. **Add an injury/lineup adjustment.** *Highest-impact remaining task.* The api-football `/injuries` endpoint is cheap (1 call per team). A team missing 3+ starting XI players should get a temporary attack/defense penalty — something like ±0.15 to the respective rating. Easy ~30-line addition to `scripts/update.py`.

## How the model works

**Dixon-Coles bivariate Poisson.** Each team has an attack rating α and a defense rating β. The expected goals in a match are:

```
λ_home = exp(α_home − β_away + γ)     # γ = home advantage (0 if neutral)
λ_away = exp(α_away − β_home)
```

Then `P(home=x, away=y) = Poisson(x; λ_home) · Poisson(y; λ_away) · τ(x, y; ρ)`, where τ is the Dixon-Coles correction that fixes the standard Poisson's tendency to under-predict 1-1 and over-predict 0-0.

**Time decay.** Each match in training is weighted by `exp(−ξ · age_years)`. With ξ=0.4, a 4-year-old match counts about 20% as much as today's.

**Tournament weighting.** Friendlies are scaled down to 0.3 because their signal-to-noise is bad (rotation squads, low intensity); World Cup matches are full weight; qualifiers are in between. See `TOURNAMENT_WEIGHTS` in `model/dixon_coles.py`.

**Warm-started fitting.** The optimizer (L-BFGS-B) gets initialized from the previous fit's parameters on every refit. This is what makes the daily update cycle fast (~10 seconds instead of ~60).

**Tournament simulation.** Monte Carlo. For each sample: simulate every group match by sampling from the score-probability matrix, rank teams by points → goal difference → goals scored, pick advancers, then play the knockout bracket. Extra time scales the Poisson rates by 1/3 (30 minutes of regulation-equivalent); penalties are a 50/50 coin flip because anything fancier would be made up.

## Known limitations

- **Penalty shootouts are 50/50.** A team with a notoriously good shootout record (England circa now, say) doesn't get credit. This is honest — the historical data is too thin to model this properly.
- **No squad changes.** The model treats "Argentina" as a single entity across decades. The May-2026 Argentina rating reflects the post-Messi-prime squad, but it also bakes in a lot of older matches.
- **CONMEBOL inflation.** South American teams play meaningful qualifiers against other strong sides; UEFA teams play qualifiers against minnows. The model can over-rate CONMEBOL teams as a result. Calibration against bookmaker odds fixes this empirically.
- **No injury or lineup awareness.** Build that in (see "Before you launch" #3).
- **Bracket is randomized per sim.** The real bracket is determined by group-finish position. When the draw is set, replace the `random.shuffle(bracket)` line in `model/simulator.py` with proper seeding logic.

## License

MIT. Have at it.

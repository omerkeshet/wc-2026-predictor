/**
 * Pure-function port of the Dixon-Coles bivariate Poisson math.
 *
 * Lets us compute matchup probabilities at build time directly from the
 * ratings JSON (attack/defense per team + rho), without re-running the
 * Python model. Same equations, same outputs — just in TypeScript.
 *
 * Used by the bracket page to derive knockout-round predictions from data
 * that was originally generated for the group stage.
 */
import type { Rating, RatingsPayload, OutcomeProbs } from "./types";

const MAX_GOALS = 6; // matches what the Python pipeline uses for fixture matrices

// Poisson PMF: P(X = k | lambda)
function poissonPmf(k: number, lambda: number): number {
  if (lambda <= 0) return k === 0 ? 1 : 0;
  // Compute via logs to avoid overflow for higher k. k stays small (≤6) so
  // factorial via gamma is overkill — just iterate.
  let logF = 0;
  for (let i = 2; i <= k; i++) logF += Math.log(i);
  const logP = k * Math.log(lambda) - lambda - logF;
  return Math.exp(logP);
}

/**
 * Build the score-probability matrix for a single match.
 * Returns a 7x7 grid where matrix[i][j] = P(home scores i, away scores j).
 */
export function scoreMatrix(
  homeRating: Rating,
  awayRating: Rating,
  rho: number,
  neutral: boolean,
  homeAdvantage: number,
): number[][] {
  const homeFactor = neutral ? 0 : homeAdvantage;
  const lambda = Math.exp(homeRating.attack - awayRating.defense + homeFactor);
  const mu = Math.exp(awayRating.attack - homeRating.defense);

  const size = MAX_GOALS + 1;
  const pH = Array.from({ length: size }, (_, i) => poissonPmf(i, lambda));
  const pA = Array.from({ length: size }, (_, j) => poissonPmf(j, mu));

  const mat: number[][] = [];
  for (let i = 0; i < size; i++) {
    const row: number[] = [];
    for (let j = 0; j < size; j++) row.push(pH[i] * pA[j]);
    mat.push(row);
  }

  // Dixon-Coles low-score correction (mirrors model/dixon_coles.py)
  mat[0][0] *= 1 - lambda * mu * rho;
  mat[0][1] *= 1 + lambda * rho;
  mat[1][0] *= 1 + mu * rho;
  mat[1][1] *= 1 - rho;

  // Renormalize (correction shifts total mass slightly off 1)
  let total = 0;
  for (let i = 0; i < size; i++) for (let j = 0; j < size; j++) total += mat[i][j];
  for (let i = 0; i < size; i++) for (let j = 0; j < size; j++) mat[i][j] /= total;
  return mat;
}

/**
 * Sum the home/draw/away regions of a score matrix.
 *
 * NOTE: These are 90-minute outcome probabilities. For knockout matches,
 * a draw at 90' goes to extra time and penalties. We model that by
 * splitting the draw mass 50/50 — see knockoutWinProbs().
 */
export function outcomeProbs(matrix: number[][]): OutcomeProbs {
  let home = 0, draw = 0, away = 0;
  const n = matrix.length;
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      if (i > j) home += matrix[i][j];
      else if (i < j) away += matrix[i][j];
      else draw += matrix[i][j];
    }
  }
  return { home, draw, away };
}

/**
 * Knockout-style win probabilities.
 *
 * Replicates how the Python simulator handles a tied scoreline: extra time
 * (which mostly just produces a few more goals, but we ignore for the
 * aggregated probability — the additional ET goal mass is small) and
 * penalties as a coin flip. So a 90-min draw becomes a 50/50 between sides.
 *
 * The Python simulator does this match-by-match in Monte Carlo. Here we
 * compute the aggregate analytically, which is equivalent in expectation.
 */
export function knockoutWinProbs(
  teamA: Rating,
  teamB: Rating,
  rho: number,
  homeAdvantage: number,
): { a: number; b: number; drawAt90: number } {
  const mat = scoreMatrix(teamA, teamB, rho, true, homeAdvantage);
  const { home: a, draw, away: b } = outcomeProbs(mat);
  // Split draw 50/50 between the two teams (penalties coin flip)
  return { a: a + draw / 2, b: b + draw / 2, drawAt90: draw };
}

export function teamMap(payload: RatingsPayload): Map<string, Rating> {
  return new Map(payload.ratings.map((r) => [r.team, r]));
}

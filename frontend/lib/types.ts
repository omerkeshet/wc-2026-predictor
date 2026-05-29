export type OutcomeProbs = { home: number; draw: number; away: number };

export type Match = {
  id?: string | number | null;
  date: string;
  home: string;
  away: string;
  neutral: boolean;
  stage: string;
  group?: string;
  probs: OutcomeProbs;
  expected_goals: { home: number; away: number };
  modal_score: { home: number; away: number; p: number };
  score_matrix: number[][];
};

export type MatchesPayload = { matches: Match[] };

export type Rating = { team: string; attack: number; defense: number; overall: number };

export type RatingsPayload = {
  home_advantage: number;
  rho: number;
  reference_date: string;
  ratings: Rating[];
};

export type Contender = {
  team: string;
  advance_r32: number;
  qf: number;
  sf: number;
  final: number;
  win: number;
};

export type Group = { name: string; teams: string[] };

export type TournamentPayload = {
  groups: Group[];
  contenders: Contender[];
};

export type Meta = {
  generated_at: string;
  reference_date: string;
  model: string;
  xi: number;
  history_years: number;
  n_simulations: number;
  n_matches_trained_on: number;
  converged: boolean;
};

/**
 * Build the "most likely" knockout bracket from the existing predictions.
 *
 * Approach:
 *   1. For each group, rank teams by their advance_r32 probability (which
 *      reflects model strength + group composition). Top 2 are the modal
 *      group winners/runners-up.
 *   2. Pick the 8 best third-placed teams overall (also by advance_r32 —
 *      already accounts for the third-place-spot subset).
 *   3. Seed them into the Round of 32 using the official 2026 bracket
 *      structure: A1-B2, C1-D2, etc.
 *   4. Walk each round: between the two teams in a slot, the higher-rated
 *      one (by attack+defense) advances. Compute the win probability for
 *      that matchup using knockoutWinProbs().
 *
 * "Most likely" here means modal at each independent decision — not the
 * single most probable joint outcome (which would require enumerating all
 * paths). For visualization purposes this distinction rarely matters.
 */
import type { Contender, Rating, RatingsPayload, TournamentPayload } from "./types";
import { knockoutWinProbs, teamMap } from "./match-math";

export type BracketTeam = {
  name: string;
  rating: Rating | null; // null if model has no data — shouldn't happen for WC teams
  groupFinish: "1st" | "2nd" | "3rd";
  group: string;
};

export type BracketMatch = {
  round: "R32" | "R16" | "QF" | "SF" | "F";
  slot: number; // 0-indexed position within the round
  teamA: BracketTeam;
  teamB: BracketTeam;
  winner: BracketTeam;
  probA: number; // chance teamA wins
  probB: number; // chance teamB wins
  drawAt90: number;
};

export type Bracket = {
  rounds: {
    R32: BracketMatch[];
    R16: BracketMatch[];
    QF: BracketMatch[];
    SF: BracketMatch[];
    F: BracketMatch[];
  };
  champion: BracketTeam;
};

// Real 2026 R32 pairings, encoded as the (group, finish) of each side.
// Derived from the actual FIFA 2026 bracket as published in mid-2026.
//
// The pattern is more complex than I originally guessed: FIFA mixes
// (winner vs 3rd-from-specific-group), (winner vs runner-up), and
// (runner-up vs runner-up) matches across the bracket. We encode each
// slot as a literal (group, finish) pair — no "best 3rd" guessing.
type Slot = { group: string; finish: "1st" | "2nd" | "3rd" };

const R32_SLOTS: [Slot, Slot][] = [
  // Top half of bracket
  [{ group: "E", finish: "1st" }, { group: "D", finish: "3rd" }],   // Germany vs Paraguay
  [{ group: "I", finish: "1st" }, { group: "F", finish: "3rd" }],   // France vs Tunisia
  [{ group: "A", finish: "2nd" }, { group: "B", finish: "2nd" }],   // S. Korea vs Canada
  [{ group: "F", finish: "1st" }, { group: "C", finish: "2nd" }],   // Netherlands vs Morocco
  [{ group: "K", finish: "2nd" }, { group: "L", finish: "2nd" }],   // Portugal vs Croatia
  [{ group: "H", finish: "1st" }, { group: "J", finish: "2nd" }],   // Spain vs Austria
  [{ group: "D", finish: "1st" }, { group: "I", finish: "3rd" }],   // USA vs Norway
  [{ group: "G", finish: "1st" }, { group: "J", finish: "3rd" }],   // Belgium vs Algeria
  // Bottom half of bracket
  [{ group: "C", finish: "1st" }, { group: "F", finish: "2nd" }],   // Brazil vs Japan
  [{ group: "E", finish: "2nd" }, { group: "I", finish: "2nd" }],   // Ecuador vs Senegal
  [{ group: "A", finish: "1st" }, { group: "E", finish: "3rd" }],   // Mexico vs Côte d'Ivoire
  [{ group: "L", finish: "1st" }, { group: "K", finish: "3rd" }],   // England vs Uzbekistan
  [{ group: "J", finish: "1st" }, { group: "H", finish: "2nd" }],   // Argentina vs Uruguay
  [{ group: "D", finish: "2nd" }, { group: "G", finish: "2nd" }],   // Australia vs Iran
  [{ group: "B", finish: "1st" }, { group: "G", finish: "3rd" }],   // Switzerland vs Egypt
  [{ group: "K", finish: "1st" }, { group: "L", finish: "3rd" }],   // Colombia vs Panama
];

function pickGroupFinishers(
  groups: TournamentPayload["groups"],
  contenders: Contender[],
): { byGroup: Map<string, { first: BracketTeam; second: BracketTeam; third: BracketTeam }> } {
  const cMap = new Map(contenders.map((c) => [c.team, c]));
  const byGroup = new Map<string, { first: BracketTeam; second: BracketTeam; third: BracketTeam }>();

  for (const g of groups) {
    // Rank teams in this group by their probability of advancing.
    const ranked = g.teams
      .map((t) => ({ name: t, c: cMap.get(t), group: g.name }))
      .sort((a, b) => (b.c?.advance_r32 ?? 0) - (a.c?.advance_r32 ?? 0));

    const teams: BracketTeam[] = ranked.slice(0, 4).map((r, i) => ({
      name: r.name,
      rating: null, // filled in by caller
      groupFinish: i === 0 ? "1st" : i === 1 ? "2nd" : "3rd",
      group: g.name,
    }));
    if (teams.length < 4) continue;

    byGroup.set(g.name, { first: teams[0], second: teams[1], third: teams[2] });
  }
  return { byGroup };
}

export function buildBracket(
  tournament: TournamentPayload,
  ratings: RatingsPayload,
): Bracket {
  const teamRatings = teamMap(ratings);
  const { byGroup } = pickGroupFinishers(tournament.groups, tournament.contenders);

  // Attach ratings to bracket teams
  const attachRating = (t: BracketTeam): BracketTeam => ({
    ...t,
    rating: teamRatings.get(t.name) ?? null,
  });

  // Build R32 from the slots — each slot directly names which group's
  // 1st/2nd/3rd finisher fills it.
  const r32: BracketMatch[] = R32_SLOTS.map((pair, slot) => {
    const teams = pair.map((s): BracketTeam => {
      const finishers = byGroup.get(s.group);
      if (!finishers) {
        return { name: `${s.group}${s.finish}`, rating: null, groupFinish: s.finish, group: s.group };
      }
      const team =
        s.finish === "1st" ? finishers.first :
        s.finish === "2nd" ? finishers.second :
        finishers.third;
      return attachRating(team);
    });
    return buildMatch("R32", slot, teams[0], teams[1], ratings);
  });

  // Helper: given a list of winners, pair them up to form the next round
  const nextRound = (
    prev: BracketMatch[],
    round: BracketMatch["round"],
  ): BracketMatch[] => {
    const out: BracketMatch[] = [];
    for (let i = 0; i < prev.length; i += 2) {
      out.push(buildMatch(round, out.length, prev[i].winner, prev[i + 1].winner, ratings));
    }
    return out;
  };

  const r16 = nextRound(r32, "R16");
  const qf = nextRound(r16, "QF");
  const sf = nextRound(qf, "SF");
  const f = nextRound(sf, "F");

  // Third-place playoff: the two losing semifinalists meet.
  // For each SF match, the loser is whichever team isn't the winner.
  return {
    rounds: { R32: r32, R16: r16, QF: qf, SF: sf, F: f },
    champion: f[0].winner,
  };
}

function buildMatch(
  round: BracketMatch["round"],
  slot: number,
  teamA: BracketTeam,
  teamB: BracketTeam,
  ratings: RatingsPayload,
): BracketMatch {
  // If either team has no rating (shouldn't happen with the official 2026 teams),
  // fall back to a 50/50.
  let probA = 0.5, probB = 0.5, drawAt90 = 0;
  if (teamA.rating && teamB.rating) {
    const r = knockoutWinProbs(teamA.rating, teamB.rating, ratings.rho, ratings.home_advantage);
    probA = r.a;
    probB = r.b;
    drawAt90 = r.drawAt90;
  }
  const winner = probA >= probB ? teamA : teamB;
  return { round, slot, teamA, teamB, winner, probA, probB, drawAt90 };
}

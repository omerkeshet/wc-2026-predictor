import type { Bracket, BracketMatch } from "@/lib/bracket";

const ROUND_LABELS: Record<BracketMatch["round"], string> = {
  R32: "Round of 32",
  R16: "Round of 16",
  QF: "Quarter-finals",
  SF: "Semi-finals",
  F: "Final",
};

// Base height (in rem) of a single R32 match cell + its gap to the next.
// Every subsequent round's cells take 2× the height of the previous round
// so each match visually centers between the two it came from.
const R32_CELL_HEIGHT_REM = 5.5;

export function BracketTree({ bracket }: { bracket: Bracket }) {
  const rounds: BracketMatch["round"][] = ["R32", "R16", "QF", "SF", "F"];

  return (
    <div>
      {/* Column headers */}
      <div className="mb-4 overflow-x-auto">
        <div className="grid gap-3 min-w-[1100px]"
             style={{ gridTemplateColumns: `repeat(${rounds.length}, minmax(200px, 1fr))` }}>
          {rounds.map((r) => (
            <div key={r} className="font-mono text-[10px] uppercase tracking-wider text-muted">
              {ROUND_LABELS[r]}
              <span className="ml-2 text-bone/40">{bracket.rounds[r].length} matches</span>
            </div>
          ))}
        </div>
      </div>

      {/* Bracket — horizontal scroll on narrow screens.
          Strategy: every column shares the same total height (= 16 × R32 cell).
          R32 column packs 16 cells flush. Subsequent rounds use justify-around
          to spread their (fewer, taller) cells across the same total height,
          which positions each cell at the midpoint of the two matches that
          feed it. Pure CSS — no math per column. */}
      <div className="overflow-x-auto pb-4">
        <div className="grid gap-3 min-w-[1100px]"
             style={{
               gridTemplateColumns: `repeat(${rounds.length}, minmax(200px, 1fr))`,
               height: `${R32_CELL_HEIGHT_REM * 17}rem`,
             }}>
          {rounds.map((r, colIdx) => {
            const matches = bracket.rounds[r];
            return (
              <div key={r} className="flex flex-col justify-around">
                {matches.map((m, i) => (
                  <BracketCell key={`${r}-${i}`} match={m} isFinal={r === "F"} />
                ))}
              </div>
            );
          })}
        </div>
      </div>

      {/* Champion */}
      <div className="mt-12 border-t border-bone/10 pt-8 text-center">
        <div className="font-mono text-[10px] uppercase tracking-wider text-muted">
          Most likely champion
        </div>
        <div className="mt-2 font-display text-7xl font-bold tracking-tighter text-accent">
          {bracket.champion.name}
        </div>
      </div>
    </div>
  );
}

function BracketCell({ match, isFinal }: { match: BracketMatch; isFinal: boolean }) {
  const aWins = match.winner.name === match.teamA.name;
  return (
    <div className={`w-full border ${isFinal ? "border-accent/40 shadow-[0_0_24px_rgba(212,255,58,0.1)]" : "border-bone/15"} bg-ink/40 p-2`}>
      <BracketSide
        name={match.teamA.name}
        prob={match.probA}
        won={aWins}
        sub={`${match.teamA.group} ${match.teamA.groupFinish}`}
      />
      <div className="my-1 border-t border-bone/10" />
      <BracketSide
        name={match.teamB.name}
        prob={match.probB}
        won={!aWins}
        sub={`${match.teamB.group} ${match.teamB.groupFinish}`}
      />
    </div>
  );
}

function BracketSide({
  name, prob, won, sub,
}: {
  name: string; prob: number; won: boolean; sub: string;
}) {
  return (
    <div className={`flex items-center justify-between gap-2 ${won ? "" : "opacity-50"}`}>
      <div className="min-w-0">
        <div className={`font-display text-sm tracking-tight truncate ${won ? "text-paper" : "text-bone/70"}`}>
          {name}
        </div>
        <div className="font-mono text-[9px] uppercase tracking-wider text-muted">{sub}</div>
      </div>
      <div className={`font-mono text-xs ${won ? "text-accent" : "text-muted"}`}>
        {Math.round(prob * 100)}%
      </div>
    </div>
  );
}

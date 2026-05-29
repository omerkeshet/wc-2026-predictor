import type { Match } from "@/lib/types";
import { WinProbBar } from "./WinProbBar";
import { ScoreMatrix } from "./ScoreMatrix";

export function MatchCard({ m }: { m: Match }) {
  return (
    <article className="border border-bone/15 bg-ink/40 p-6 backdrop-blur-sm">
      <header className="mb-5 flex items-baseline justify-between border-b border-bone/10 pb-3">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-wider text-muted">
            {m.group ? `Group ${m.group}` : m.stage} · {m.date}
          </div>
          <h3 className="mt-1 font-display text-2xl leading-tight tracking-tighter">
            <span className="text-paper">{m.home}</span>
            <span className="mx-3 text-muted">v</span>
            <span className="text-paper">{m.away}</span>
          </h3>
        </div>
        <div className="text-right">
          <div className="font-mono text-[10px] uppercase tracking-wider text-muted">Most likely</div>
          <div className="font-display text-3xl font-bold tracking-tighter text-accent">
            {m.modal_score.home}–{m.modal_score.away}
          </div>
          <div className="font-mono text-[10px] text-muted">
            {(m.modal_score.p * 100).toFixed(1)}%
          </div>
        </div>
      </header>

      <div className="mb-6">
        <WinProbBar probs={m.probs} homeLabel={m.home} awayLabel={m.away} />
      </div>

      <div className="mb-6 grid grid-cols-3 gap-4 border-y border-bone/10 py-3">
        <Stat label="Exp. goals (home)" value={m.expected_goals.home.toFixed(2)} />
        <Stat label="Exp. goals (away)" value={m.expected_goals.away.toFixed(2)} />
        <Stat label="Expected total" value={(m.expected_goals.home + m.expected_goals.away).toFixed(2)} />
      </div>

      <ScoreMatrix
        matrix={m.score_matrix}
        homeLabel={m.home}
        awayLabel={m.away}
        modal={m.modal_score}
      />
    </article>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-wider text-muted">{label}</div>
      <div className="mt-1 font-display text-2xl tracking-tighter">{value}</div>
    </div>
  );
}

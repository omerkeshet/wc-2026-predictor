import type { Contender } from "@/lib/types";

export function Contenders({ contenders }: { contenders: Contender[] }) {
  const top = contenders.filter((c) => c.win > 0).slice(0, 20);
  const maxWin = top[0]?.win ?? 1;

  return (
    <div className="border border-bone/15 bg-ink/40">
      <div className="border-b border-bone/10 px-6 py-3">
        <h2 className="font-display text-3xl tracking-tighter">Title contenders</h2>
        <div className="font-mono text-[10px] uppercase tracking-wider text-muted">
          Probability of winning the tournament · Monte Carlo
        </div>
      </div>
      <table className="w-full">
        <thead className="border-b border-bone/10 text-left font-mono text-[10px] uppercase tracking-wider text-muted">
          <tr>
            <th className="w-10 px-6 py-2">#</th>
            <th className="py-2">Team</th>
            <th className="py-2 text-right">R32</th>
            <th className="py-2 text-right">QF</th>
            <th className="py-2 text-right">SF</th>
            <th className="py-2 text-right">Final</th>
            <th className="py-2 pr-6 text-right">Win</th>
          </tr>
        </thead>
        <tbody>
          {top.map((c, i) => (
            <tr key={c.team} className="border-b border-bone/5 hover:bg-bone/5">
              <td className="px-6 py-3 font-mono text-xs text-muted">{i + 1}</td>
              <td className="py-3 font-display text-lg tracking-tight">{c.team}</td>
              <td className="py-3 text-right font-mono text-xs text-muted">{pct(c.advance_r32)}</td>
              <td className="py-3 text-right font-mono text-xs text-muted">{pct(c.qf)}</td>
              <td className="py-3 text-right font-mono text-xs text-muted">{pct(c.sf)}</td>
              <td className="py-3 text-right font-mono text-xs text-muted">{pct(c.final)}</td>
              <td className="py-3 pr-6 text-right">
                <div className="flex items-center justify-end gap-3">
                  <div className="h-1 bg-bone/10" style={{ width: 80 }}>
                    <div
                      className="h-full bg-accent"
                      style={{ width: `${(c.win / maxWin) * 100}%` }}
                    />
                  </div>
                  <span className="font-display text-xl font-bold tracking-tighter text-accent w-12 text-right">
                    {pct(c.win)}
                  </span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function pct(p: number): string {
  if (p < 0.001) return "·";
  if (p < 0.01) return "<1%";
  return `${Math.round(p * 100)}%`;
}

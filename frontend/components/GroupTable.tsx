import type { Contender, Group } from "@/lib/types";

export function GroupTable({
  group,
  contenders,
}: {
  group: Group;
  contenders: Contender[];
}) {
  const byTeam = new Map(contenders.map((c) => [c.team, c]));
  const rows = group.teams.map((t) => ({
    team: t,
    c: byTeam.get(t),
  }));
  rows.sort((a, b) => (b.c?.advance_r32 ?? 0) - (a.c?.advance_r32 ?? 0));

  return (
    <div className="border border-bone/15 bg-ink/40">
      <div className="border-b border-bone/10 px-4 py-2">
        <div className="font-mono text-[10px] uppercase tracking-wider text-muted">Group</div>
        <h3 className="font-display text-2xl font-bold tracking-tighter">{group.name}</h3>
      </div>
      <table className="w-full">
        <thead className="border-b border-bone/10 font-mono text-[10px] uppercase tracking-wider text-muted">
          <tr>
            <th className="px-4 py-1 text-left">Team</th>
            <th className="py-1 text-right">R32</th>
            <th className="py-1 pr-4 text-right">Win</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ team, c }) => (
            <tr key={team} className="border-b border-bone/5 last:border-b-0">
              <td className="px-4 py-2 font-display text-base tracking-tight">{team}</td>
              <td className="py-2 text-right font-mono text-xs">
                {c ? `${Math.round(c.advance_r32 * 100)}%` : "—"}
              </td>
              <td className="py-2 pr-4 text-right font-mono text-xs text-accent">
                {c && c.win >= 0.005 ? `${Math.round(c.win * 100)}%` : "·"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

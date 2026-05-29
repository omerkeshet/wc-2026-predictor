import type { OutcomeProbs } from "@/lib/types";

export function WinProbBar({ probs, homeLabel, awayLabel }: {
  probs: OutcomeProbs;
  homeLabel: string;
  awayLabel: string;
}) {
  const ph = Math.round(probs.home * 100);
  const pd = Math.round(probs.draw * 100);
  const pa = 100 - ph - pd;
  return (
    <div className="w-full">
      <div className="flex h-7 w-full overflow-hidden border border-bone/20 font-mono text-xs">
        <div
          className="flex items-center justify-end pr-2 text-ink"
          style={{ width: `${probs.home * 100}%`, background: "#d4ff3a" }}
          title={`${homeLabel}: ${ph}%`}
        >
          {ph >= 8 ? `${ph}%` : ""}
        </div>
        <div
          className="flex items-center justify-center text-paper"
          style={{ width: `${probs.draw * 100}%`, background: "#3a3a36" }}
          title={`Draw: ${pd}%`}
        >
          {pd >= 8 ? `${pd}%` : ""}
        </div>
        <div
          className="flex items-center justify-start pl-2 text-paper"
          style={{ width: `${probs.away * 100}%`, background: "#ff5638" }}
          title={`${awayLabel}: ${pa}%`}
        >
          {pa >= 8 ? `${pa}%` : ""}
        </div>
      </div>
      <div className="mt-1 flex justify-between font-mono text-[10px] uppercase tracking-wider text-muted">
        <span>{homeLabel} win</span>
        <span>draw</span>
        <span>{awayLabel} win</span>
      </div>
    </div>
  );
}

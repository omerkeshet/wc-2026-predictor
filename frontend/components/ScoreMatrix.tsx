type Props = {
  matrix: number[][];
  homeLabel: string;
  awayLabel: string;
  modal?: { home: number; away: number };
};

// Map probability → green intensity. Caps at top so the modal cell really pops.
function cellColor(p: number, max: number): string {
  if (p <= 0) return "rgba(255,255,255,0.02)";
  const t = Math.min(1, p / Math.max(max, 0.001));
  // dark green floor → bright lime ceiling
  const alpha = 0.10 + t * 0.85;
  return `rgba(212, 255, 58, ${alpha.toFixed(3)})`;
}

export function ScoreMatrix({ matrix, homeLabel, awayLabel, modal }: Props) {
  const max = Math.max(...matrix.flat());
  const size = matrix.length;

  return (
    <div>
      <div className="mb-2 flex items-end justify-between">
        <div className="font-mono text-[10px] uppercase tracking-wider text-muted">
          Score probability heatmap
        </div>
        <div className="font-mono text-[10px] uppercase tracking-wider text-muted">
          P(score) — darker = less likely
        </div>
      </div>
      <div className="inline-grid gap-px"
           style={{ gridTemplateColumns: `auto repeat(${size}, 36px)` }}>
        {/* Top-left corner */}
        <div />
        {/* Column headers (away goals) */}
        {Array.from({ length: size }).map((_, j) => (
          <div key={`col-${j}`} className="text-center font-mono text-[10px] text-muted">
            {j}
          </div>
        ))}
        {matrix.map((row, i) => (
          <>
            <div key={`row-${i}`} className="pr-2 text-right font-mono text-[10px] text-muted self-center">
              {i}
            </div>
            {row.map((p, j) => {
              const isModal = modal && modal.home === i && modal.away === j;
              return (
                <div
                  key={`${i}-${j}`}
                  className="heatmap-cell relative flex h-9 items-center justify-center font-mono text-[10px]"
                  style={{
                    background: cellColor(p, max),
                    color: p / max > 0.4 ? "#0a0a0a" : "#888",
                    outline: isModal ? "2px solid #d4ff3a" : undefined,
                  }}
                  title={`${homeLabel} ${i} – ${j} ${awayLabel}: ${(p * 100).toFixed(1)}%`}
                >
                  {(p * 100).toFixed(0)}
                </div>
              );
            })}
          </>
        ))}
      </div>
      <div className="mt-2 flex justify-between font-mono text-[10px] uppercase tracking-wider text-muted">
        <span>← {homeLabel} goals (rows)</span>
        <span>{awayLabel} goals (cols) →</span>
      </div>
    </div>
  );
}

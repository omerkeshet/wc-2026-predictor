import Link from "next/link";
import { loadR32, loadMeta } from "@/lib/data";
import { MatchCard } from "@/components/MatchCard";

export default async function RoundOf32Page() {
  const [r32, meta] = await Promise.all([loadR32(), loadMeta()]);

  const refDate = new Date(meta.reference_date).toLocaleDateString("en-GB", {
    day: "numeric", month: "long", year: "numeric",
  });

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      {/* Header */}
      <header className="mb-10 border-b border-bone/10 pb-8">
        <Link
          href="/"
          className="font-mono text-[10px] uppercase tracking-wider text-accent hover:underline"
        >
          ← Back to overview
        </Link>
        <h1 className="mt-3 font-display text-6xl font-bold leading-[0.95] tracking-tighter md:text-7xl">
          Round of 32
        </h1>
        <p className="mt-4 max-w-2xl text-bone/70">
          Every knockout fixture with a full score-probability heatmap.
          {" "}
          <span className="font-mono text-xs text-muted">
            {r32.matches.length} matches · model ref {refDate}
          </span>
        </p>
      </header>

      {/* All 16 ties, in bracket order */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {r32.matches.map((m, i) => (
          <MatchCard key={`${m.home}-${m.away}-${i}`} m={m} />
        ))}
      </div>

      <footer className="mt-24 border-t border-bone/10 pt-8 font-mono text-xs text-muted">
        <p>
          Probabilities are 90-minute outcomes (before extra time), computed at a neutral venue from
          the same Dixon-Coles ratings as the group stage. Modal scoreline shown with its probability;
          the heatmap below it shows the full P(home, away) distribution.
        </p>
      </footer>
    </main>
  );
}

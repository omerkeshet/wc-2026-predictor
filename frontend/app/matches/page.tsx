import Link from "next/link";
import { loadMatches, loadMeta } from "@/lib/data";
import { MatchCard } from "@/components/MatchCard";
import type { Match } from "@/lib/types";

export default async function MatchesPage() {
  const [matches, meta] = await Promise.all([loadMatches(), loadMeta()]);

  // Group by group letter; keep groups sorted A-L.
  const byGroup = new Map<string, Match[]>();
  for (const m of matches.matches) {
    const key = m.group ?? "?";
    if (!byGroup.has(key)) byGroup.set(key, []);
    byGroup.get(key)!.push(m);
  }
  const groupLetters = Array.from(byGroup.keys()).sort();

  // Within each group, sort matches so the most extreme mismatches come first —
  // it makes scanning a bit more interesting than alphabetical.
  for (const letter of groupLetters) {
    byGroup.get(letter)!.sort((a, b) => {
      const ma = Math.max(a.probs.home, a.probs.draw, a.probs.away);
      const mb = Math.max(b.probs.home, b.probs.draw, b.probs.away);
      return mb - ma;
    });
  }

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
          All matches
        </h1>
        <p className="mt-4 max-w-2xl text-bone/70">
          Every group-stage fixture with a full score-probability heatmap.
          {" "}
          <span className="font-mono text-xs text-muted">
            {matches.matches.length} matches · refreshed {refDate}
          </span>
        </p>
      </header>

      {/* Sticky group nav */}
      <nav className="sticky top-0 z-20 -mx-6 mb-10 border-y border-bone/10 bg-ink/95 px-6 py-3 backdrop-blur-md">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-[10px] uppercase tracking-wider text-muted">
            Jump to group:
          </span>
          {groupLetters.map((letter) => (
            <a
              key={letter}
              href={`#group-${letter}`}
              className="font-display text-base font-bold tracking-tight text-bone/70 hover:text-accent transition-colors"
            >
              {letter}
            </a>
          ))}
        </div>
      </nav>

      {/* All groups */}
      {groupLetters.map((letter) => {
        const groupMatches = byGroup.get(letter)!;
        return (
          <section
            key={letter}
            id={`group-${letter}`}
            className="mb-16 scroll-mt-20"
          >
            <div className="mb-6 flex items-baseline justify-between border-b border-bone/10 pb-3">
              <h2 className="font-display text-5xl tracking-tighter">
                Group <span className="text-accent">{letter}</span>
              </h2>
              <div className="font-mono text-[10px] uppercase tracking-wider text-muted">
                {groupMatches.length} matches
              </div>
            </div>
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              {groupMatches.map((m, i) => (
                <MatchCard key={`${m.home}-${m.away}-${i}`} m={m} />
              ))}
            </div>
          </section>
        );
      })}

      <footer className="mt-24 border-t border-bone/10 pt-8 font-mono text-xs text-muted">
        <p>
          Probabilities are 90-minute outcomes for neutral-venue matches. Modal scoreline shown
          with its probability; the heatmap below it shows the full P(home, away) distribution.
        </p>
      </footer>
    </main>
  );
}

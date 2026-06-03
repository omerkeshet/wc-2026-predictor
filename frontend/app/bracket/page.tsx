import Link from "next/link";
import { loadRatings, loadTournament, loadMeta } from "@/lib/data";
import { buildBracket } from "@/lib/bracket";
import { BracketTree } from "@/components/BracketTree";

export default async function BracketPage() {
  const [tournament, ratings, meta] = await Promise.all([
    loadTournament(),
    loadRatings(),
    loadMeta(),
  ]);

  const bracket = buildBracket(tournament, ratings);

  const refDate = new Date(meta.reference_date).toLocaleDateString("en-GB", {
    day: "numeric", month: "long", year: "numeric",
  });

  return (
    <main className="mx-auto max-w-7xl px-6 py-12">
      <header className="mb-10 border-b border-bone/10 pb-8">
        <Link
          href="/"
          className="font-mono text-[10px] uppercase tracking-wider text-accent hover:underline"
        >
          ← Back to overview
        </Link>
        <h1 className="mt-3 font-display text-6xl font-bold leading-[0.95] tracking-tighter md:text-7xl">
          The whole tournament
        </h1>
        <p className="mt-4 max-w-2xl text-bone/70">
          The most likely path from R32 to the final, assuming each group goes to chalk
          (top two teams advance, with the best third-placed sides filling the remaining slots).
          {" "}
          <span className="font-mono text-xs text-muted">refreshed {refDate}</span>
        </p>
        <p className="mt-3 max-w-2xl text-sm text-bone/50">
          Each percentage shows the favorite's chance to win that specific tie. Draws after
          90 minutes are split 50/50 to reflect penalty shootout uncertainty.
        </p>
      </header>

      <BracketTree bracket={bracket} />

      <footer className="mt-16 border-t border-bone/10 pt-8 font-mono text-xs text-muted">
        <p>
          The bracket assumes the modal group outcome (each group's strongest two teams advance,
          with the best four third-placed teams qualifying). In reality, group-stage upsets cascade
          through the knockout draw — the headline title odds on the homepage account for that
          variability across thousands of Monte Carlo runs; this view does not.
        </p>
      </footer>
    </main>
  );
}

import { loadMatches, loadTournament, loadMeta, loadRatings } from "@/lib/data";
import Link from "next/link";
import { MatchCard } from "@/components/MatchCard";
import { Contenders } from "@/components/Contenders";
import { GroupTable } from "@/components/GroupTable";

export default async function HomePage() {
  const [matches, tournament, meta, ratings] = await Promise.all([
    loadMatches(),
    loadTournament(),
    loadMeta(),
    loadRatings(),
  ]);

  // Pick a handful of fixtures with the most extreme & most balanced predictions
  // to feature on the homepage.
  const featured = [...matches.matches]
    .sort((a, b) => Math.max(b.probs.home, b.probs.away) - Math.max(a.probs.home, a.probs.away))
    .slice(0, 3)
    .concat(
      [...matches.matches]
        .sort((a, b) => {
          const balanceA = 1 - Math.max(a.probs.home, a.probs.draw, a.probs.away);
          const balanceB = 1 - Math.max(b.probs.home, b.probs.draw, b.probs.away);
          return balanceB - balanceA;
        })
        .slice(0, 3),
    );

  const refDate = new Date(meta.reference_date).toLocaleDateString("en-GB", {
    day: "numeric", month: "long", year: "numeric",
  });

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      {/* Header */}
      <header className="mb-16 border-b border-bone/10 pb-12">
        <div className="font-mono text-[10px] uppercase tracking-wider text-accent">
          Updated · {refDate}
        </div>
        <h1 className="mt-2 font-display text-7xl font-bold leading-[0.92] tracking-tighter md:text-8xl">
          The 2026
          <br />
          World Cup,
          <br />
          <span className="text-accent">in probabilities.</span>
        </h1>
        <p className="mt-6 max-w-2xl font-display text-xl leading-snug tracking-tight text-bone/80">
          A Dixon-Coles bivariate-Poisson model fitted to{" "}
          <span className="font-mono text-sm text-accent">
            {meta.n_matches_trained_on.toLocaleString()}
          </span>{" "}
          international matches, simulated{" "}
          <span className="font-mono text-sm text-accent">{meta.n_simulations.toLocaleString()}</span>{" "}
          times.
        </p>
        <div className="mt-8 grid grid-cols-2 gap-4 border-t border-bone/10 pt-6 md:grid-cols-4">
          <Meta label="Model" value="Dixon-Coles" />
          <Meta label="Decay (ξ)" value={meta.xi.toString()} />
          <Meta label="History" value={`${meta.history_years} years`} />
          <Meta label="Home adv." value={ratings.home_advantage.toFixed(3)} />
        </div>
      </header>

      {/* Contenders */}
      <section className="mb-20">
        <Contenders contenders={tournament.contenders} />
      </section>

      {/* Groups */}
      <section className="mb-20">
        <div className="mb-6 border-b border-bone/10 pb-3">
          <div className="font-mono text-[10px] uppercase tracking-wider text-muted">Phase one</div>
          <h2 className="font-display text-5xl tracking-tighter">Group stage</h2>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {tournament.groups.map((g) => (
            <GroupTable key={g.name} group={g} contenders={tournament.contenders} />
          ))}
        </div>
      </section>

      {/* Featured matches */}
      <section className="mb-20">
        <div className="mb-6 border-b border-bone/10 pb-3">
          <div className="font-mono text-[10px] uppercase tracking-wider text-muted">Selected</div>
          <h2 className="font-display text-5xl tracking-tighter">Match predictions</h2>
          <p className="mt-2 max-w-2xl text-bone/70">
            Top three mismatches and top three coin-flips, by model probability.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {featured.map((m, i) => (
            <MatchCard key={`${m.home}-${m.away}-${i}`} m={m} />
          ))}
        </div>
        <div className="mt-8 text-center">
          <Link
            href="/matches"
            className="inline-block border border-accent/40 bg-accent/5 px-6 py-3 font-mono text-xs uppercase tracking-wider text-accent hover:bg-accent hover:text-ink transition-colors"
          >
            View all {matches.matches.length} matches →
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="mt-24 border-t border-bone/10 pt-8 font-mono text-xs text-muted">
        <p>
          Auto-generated {new Date(meta.generated_at).toLocaleString()}. Predictions are probabilistic
          estimates, not advice. Past performance is not indicative of future results — especially in
          international football. Bookmakers' implied probabilities are still the strongest baseline.
        </p>
      </footer>
    </main>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-wider text-muted">{label}</div>
      <div className="mt-1 font-display text-2xl font-bold tracking-tighter">{value}</div>
    </div>
  );
}

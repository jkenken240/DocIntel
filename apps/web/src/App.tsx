import { useQuery } from "@tanstack/react-query";

import { fetchReadiness } from "./lib/api/health";

export function App() {
  const readiness = useQuery({
    queryKey: ["platform-readiness"],
    queryFn: ({ signal }) => fetchReadiness(signal),
    retry: false,
    refetchInterval: 10_000,
  });

  const status = readiness.data?.status ?? "not_ready";

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-16 text-slate-100">
      <section
        className="mx-auto max-w-3xl rounded-2xl border border-slate-800 bg-slate-900 p-8"
        aria-labelledby="foundation-title"
      >
        <p className="text-sm font-semibold tracking-[0.18em] text-cyan-400 uppercase">
          Phase 2
        </p>
        <h1 id="foundation-title" className="mt-3 text-4xl font-semibold">
          DocIntel platform foundation
        </h1>
        <p className="mt-4 max-w-2xl text-slate-300">
          The repository, database, migrations, API, and web toolchain are
          connected. Document intelligence features begin in later approved
          phases.
        </p>

        <div
          className="mt-8 rounded-xl border border-slate-700 bg-slate-950 p-5"
          aria-live="polite"
        >
          <div className="flex items-center justify-between gap-4">
            <h2 className="font-medium">Platform readiness</h2>
            <span
              className={
                status === "ready"
                  ? "rounded-full bg-emerald-400/15 px-3 py-1 text-sm text-emerald-300"
                  : "rounded-full bg-amber-400/15 px-3 py-1 text-sm text-amber-200"
              }
            >
              {readiness.isPending
                ? "Checking"
                : status === "ready"
                  ? "Ready"
                  : "Not ready"}
            </span>
          </div>

          {readiness.isError ? (
            <p className="mt-4 text-sm text-rose-300">
              The API could not be reached. Start the Docker Compose services
              and retry.
            </p>
          ) : null}

          {readiness.data ? (
            <dl className="mt-4 grid gap-3 sm:grid-cols-2">
              {Object.entries(readiness.data.checks).map(([name, check]) => (
                <div key={name} className="rounded-lg bg-slate-900 px-4 py-3">
                  <dt className="font-medium capitalize">{name}</dt>
                  <dd className="mt-1 text-sm text-slate-400">{check.detail}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </div>
      </section>
    </main>
  );
}

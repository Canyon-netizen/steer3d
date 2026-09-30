"use client";

/**
 * Archived intervention experiments.
 *
 * The steering controls show what an injection is doing *right now*.
 * This panel shows what the injections have actually done — the
 * archived sweeps from `backend/examples/output/intervention/*.json`,
 * each of which is a set of counterfactual runs against a shadow
 * stream.
 *
 * It is here because the single most useful thing about a steering
 * vector is not its label, it is the shape of its dose-response: at
 * what strength does it start working, where does it stop working,
 * and does the effect have the sign its name claims. Two of the
 * archived runs are controls (strength 0), and they read exactly
 * 0.0000 — that is the evidence the measurement is real, so it is
 * shown rather than hidden.
 */

import { useEffect, useState } from "react";

type StepSummary = {
  n_steps: number;
  n_bad_steps?: number;
  steer_norm: number;
  token_agreement: number;
  first_diverged_step: number | null;
  mean_logit_kl: number;
  mean_entropy_primary: number;
  mean_entropy_shadow: number;
  max_divergence: number;
  mean_divergence: number;
  layer_curve?: {
    layer: number[];
    mean_cosine: number[];
    mean_rel_shift: number[];
  };
};

type SweepRow = {
  prompt_label?: string;
  direction: string;
  strength: number;
  layer: number;
  injected_norm?: number;
  n_steps: number;
  summary: StepSummary;
};

type SweepFile = SweepRow[];

type ScanRow = {
  layer: number;
  layer_rms: number;
  token_agreement: number | null;
  delta_entropy: number | null;
  max_divergence: number;
  mean_logit_kl: number | null;
};

type ScanFile = {
  direction: string;
  norm: number;
  prompt: string;
  rows: ScanRow[];
};

const FILES: { url: string; label: string; kind: "sweep" | "scan" }[] = [
  {
    url: "/intervention/replication_24problems_L20.json",
    label: "24-problem replication · confidence pair · L20",
    kind: "sweep",
  },
  {
    url: "/intervention/directions_L20_aime2023.json",
    label: "All directions · L20 · AIME 2023 I#1",
    kind: "sweep",
  },
  {
    url: "/intervention/layer_scan_confidence_up.json",
    label: "Injection-layer scan · confidence_up",
    kind: "scan",
  },
  {
    url: "/intervention/confidence_up_L20_sweep.json",
    label: "confidence_up strength sweep · L20 · 1 prompt",
    kind: "sweep",
  },
];

function num(v: number | null | undefined, digits = 4): string {
  if (v == null || !isFinite(v)) return "—";
  return v.toFixed(digits);
}

export default function ArchivedExperiments() {
  const [idx, setIdx] = useState(0);
  const [data, setData] = useState<SweepFile | ScanFile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const file = FILES[idx];

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    fetch(file.url)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        return r.json();
      })
      .then((j) => {
        if (!cancelled) setData(j);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e.message ?? e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [file.url]);

  return (
    <div className="flex flex-col gap-2 p-4 rounded-lg bg-panel border border-border">
      <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
        Archived experiments
      </h2>

      <select
        value={idx}
        onChange={(e) => setIdx(parseInt(e.target.value, 10))}
        className="px-2 py-1 rounded bg-bg border border-border text-xs text-gray-200"
      >
        {FILES.map((f, i) => (
          <option key={f.url} value={i}>
            {f.label}
          </option>
        ))}
      </select>

      {loading && <p className="text-[11px] text-gray-500">loading…</p>}
      {error && (
        <p className="text-[10px] text-gray-500 leading-relaxed">
          <code className="text-gray-400">run_intervention.py</code> /
          <code className="text-gray-400"> layer_scan.py</code> writes here;
          nothing archived yet.
        </p>
      )}

      {data && file.kind === "sweep" && <SweepTable rows={data as SweepRow[]} />}
      {data && file.kind === "scan" && <ScanTable data={data as ScanFile} />}
    </div>
  );
}

// ---------------------------------------------------------------------------

function SweepTable({ rows }: { rows: SweepRow[] }) {
  // Group by direction so each reads as its own dose-response.
  const groups: { direction: string; rows: SweepRow[] }[] = [];
  for (const r of rows) {
    const g = groups.find((x) => x.direction === r.direction);
    if (g) g.rows.push(r);
    else groups.push({ direction: r.direction, rows: [r] });
  }

  // How many distinct prompts does this file cover? A mean over 24
  // problems is evidence; a mean over 1 is an anecdote, and the bar
  // looks the same either way unless we say which it is.
  const nProblems = new Set(rows.map((r) => r.prompt_label)).size;

  return (
    <div className="flex flex-col gap-2.5 max-h-80 overflow-y-auto">
      <div
        className={`text-[10px] px-2 py-1 rounded border ${
          nProblems >= 10
            ? "border-emerald-600/40 bg-emerald-500/10 text-emerald-300"
            : "border-amber-600/40 bg-amber-500/10 text-amber-300"
        }`}
      >
        {nProblems === 1
          ? "n = 1 prompt — illustrative only"
          : `n = ${nProblems} prompts`}
      </div>

      {groups.map((g) => {
        // Scale the entropy bar to the largest |Δentropy| in this group.
        const deltas = g.rows.map(
          (r) => r.summary.mean_entropy_primary - r.summary.mean_entropy_shadow
        );
        const maxDe = Math.max(...deltas.map(Math.abs), 1e-6);
        // Per-problem spread, when the file has more than one prompt.
        const spread = (() => {
          if (nProblems < 2) return null;
          const nonControl = deltas.filter((_, i) => g.rows[i].strength > 0);
          if (nonControl.length < 2) return null;
          const m = nonControl.reduce((a, b) => a + b, 0) / nonControl.length;
          const sd = Math.sqrt(
            nonControl.reduce((a, b) => a + (b - m) ** 2, 0) / (nonControl.length - 1)
          );
          return { sd, m };
        })();
        const sdExceedsMean =
          spread != null && Math.abs(spread.m) > 0 && spread.sd > Math.abs(spread.m);

        return (
          <div key={g.direction}>
            <div className="text-[10px] font-medium text-gray-300 mb-1">
              {g.direction}
            </div>
            <div className="space-y-0.5">
              {g.rows.map((r) => {
                const de = r.summary.mean_entropy_primary - r.summary.mean_entropy_shadow;
                const isControl = r.strength === 0;
                const w = (Math.abs(de) / maxDe) * 50;
                return (
                  <div
                    key={`${r.direction}-${r.strength}`}
                    className="flex items-center gap-1.5 text-[10px] font-mono"
                  >
                    <span className="w-8 text-gray-500 shrink-0">
                      {r.strength.toFixed(2)}
                    </span>
                    <span className="w-11 text-gray-500 shrink-0" title="token agreement">
                      {(r.summary.token_agreement * 100).toFixed(0)}%
                    </span>
                    <span className="w-11 text-right shrink-0">
                      {isControl ? (
                        <span className="text-emerald-500">ctrl</span>
                      ) : (
                        <span
                          style={{
                            color: de < 0 ? "#60a5fa" : "#fb923c",
                          }}
                        >
                          {de >= 0 ? "+" : ""}
                          {de.toFixed(4)}
                        </span>
                      )}
                    </span>
                    {/* signed bar: left = entropy down, right = up */}
                    <span className="flex-1 flex items-center h-2 min-w-8">
                      <span className="flex-1 flex justify-end">
                        {de < 0 && (
                          <span
                            className="h-full rounded-l-sm"
                            style={{
                              width: `${w}%`,
                              backgroundColor: "#60a5fa",
                              opacity: 0.65,
                            }}
                          />
                        )}
                      </span>
                      <span className="w-px bg-gray-700" />
                      <span className="flex-1">
                        {de > 0 && (
                          <span
                            className="h-full rounded-r-sm block"
                            style={{
                              width: `${w}%`,
                              backgroundColor: "#fb923c",
                              opacity: 0.65,
                            }}
                          />
                        )}
                      </span>
                    </span>
                    <span
                      className="w-12 text-right text-gray-500 shrink-0"
                      title="max per-layer divergence"
                    >
                      {r.summary.max_divergence.toFixed(3)}
                    </span>
                  </div>
                );
              })}
            </div>
            {spread && (
              <div className="text-[9px] text-gray-600 mt-0.5 pl-[4.5rem]">
                across problems: {spread.m >= 0 ? "+" : ""}
                {spread.m.toFixed(4)} ± {spread.sd.toFixed(4)} sd
                {sdExceedsMean && (
                  <span className="text-amber-600/80">
                    {" "}
                    — spread exceeds the effect
                  </span>
                )}
              </div>
            )}
          </div>
        );
      })}

      <p className="text-[10px] text-gray-500 leading-relaxed border-t border-border pt-1.5">
        Columns: strength · token agreement · Δentropy · max per-layer
        divergence. Rows at strength 0.00 are controls — they inject a zero
        vector and must come back at exactly zero divergence, which is what
        makes the other rows attributable to the intervention.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------

function ScanTable({ data }: { data: ScanFile }) {
  const rows = data.rows;
  const maxDiv = Math.max(...rows.map((r) => r.max_divergence), 1e-6);
  return (
    <div className="flex flex-col gap-2 max-h-80 overflow-y-auto">
      <div className="text-[10px] text-gray-500">
        ‖v‖ held constant at {data.norm.toFixed(0)} across all layers, so
        the only variable is where it lands.
      </div>
      <div className="space-y-0.5">
        {rows.map((r) => {
          const rel = data.norm / (r.layer_rms || 1);
          return (
            <div key={r.layer} className="flex items-center gap-1.5 text-[10px] font-mono">
              <span className="w-8 text-gray-400 shrink-0">L{r.layer}</span>
              <span
                className="w-12 text-gray-500 shrink-0"
                title="‖v‖ as a fraction of ‖h‖ at this layer"
              >
                {(rel * 100).toFixed(0)}%
              </span>
              <span className="w-11 text-gray-500 shrink-0">
                {r.token_agreement != null
                  ? `${(r.token_agreement * 100).toFixed(0)}%`
                  : "—"}
              </span>
              <span className="flex-1 h-2 bg-gray-800/50 rounded overflow-hidden min-w-8">
                <span
                  className="block h-full rounded"
                  style={{
                    width: `${(r.max_divergence / maxDiv) * 100}%`,
                    backgroundColor: "#c084fc",
                    opacity: 0.7,
                  }}
                />
              </span>
              <span className="w-10 text-right text-gray-400 shrink-0">
                {r.max_divergence.toFixed(3)}
              </span>
            </div>
          );
        })}
      </div>
      <p className="text-[10px] text-gray-500 leading-relaxed border-t border-border pt-1.5">
        Columns: layer · ‖v‖/‖h‖ · token agreement · max divergence.
        The relative column matters: the same vector is a much larger
        perturbation at a layer where the residual stream is small.
      </p>
    </div>
  );
}

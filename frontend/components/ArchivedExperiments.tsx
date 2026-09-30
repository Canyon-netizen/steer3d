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

type ExtractionFile = {
  n_problems: number;
  inject_at: number;
  strength: number;
  control: number;
  metric: string;
  friedman_p: number;
  ratio_top_bottom: number;
  per_layer: Record<string, { mean: number; sd: number; token_agreement: number }>;
  saturation: { pair: [number, number]; delta: number; p: number } | null;
};

type NullFloorFile = {
  layers: number[];
  directions: Record<
    string,
    {
      mean_offdiagonal_cosine: number;
      null_mean_offdiagonal_cosine: number | null;
      excess_over_null: number | null;
      cohens_d: Record<string, number | null>;
    }
  >;
};

const FILES: {
  url: string;
  label: string;
  kind: "sweep" | "scan" | "extraction" | "nullfloor";
}[] = [
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
  {
    url: "/intervention/extraction_layer_effect.json",
    label: "Extraction layer vs effect · 24 problems · injected at L20",
    kind: "extraction",
  },
  {
    url: "/intervention/extraction_layer_with_null.json",
    label: "Cross-layer cosine, with null floors",
    kind: "nullfloor",
  },
];

function num(v: number | null | undefined, digits = 4): string {
  if (v == null || !isFinite(v)) return "—";
  return v.toFixed(digits);
}

export default function ArchivedExperiments() {
  const [idx, setIdx] = useState(0);
  // The payload shape depends on `file.kind`, so there is no single type
  // to hold it; each branch below narrows to the one it renders.
  const [data, setData] = useState<unknown>(null);
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

      {data != null && file.kind === "sweep" ? (
        <SweepTable rows={data as SweepRow[]} />
      ) : null}
      {data != null && file.kind === "scan" ? (
        <ScanTable data={data as ScanFile} />
      ) : null}
      {data != null && file.kind === "extraction" ? (
        <ExtractionTable data={data as ExtractionFile} />
      ) : null}
      {data != null && file.kind === "nullfloor" ? (
        <NullFloorTable data={data as NullFloorFile} />
      ) : null}
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

// ---------------------------------------------------------------------------

/**
 * Extraction layer vs behavioural effect.
 *
 * The other tables hold the injection layer fixed and vary everything
 * else. This one does the opposite: the injection stays at L20 and only
 * the layer the vector was READ OUT at changes, so the difference is
 * attributable to the extraction rather than to where the vector lands.
 */
function ExtractionTable({ data }: { data: ExtractionFile }) {
  const layers = Object.keys(data.per_layer)
    .map(Number)
    .sort((a, b) => a - b);
  const means = layers.map((L) => data.per_layer[String(L)].mean);
  const max = Math.max(...means, 1e-9);
  const sat = data.saturation;

  return (
    <div className="flex flex-col gap-2.5 max-h-80 overflow-y-auto">
      <div className="text-[10px] px-2 py-1 rounded border border-emerald-600/40 bg-emerald-500/10 text-emerald-300">
        n = {data.n_problems} problems · injected at L{data.inject_at} ·
        strength {data.strength} · controls read exactly 0.0000
      </div>

      <div className="space-y-0.5">
        {layers.map((L, i) => {
          const r = data.per_layer[String(L)];
          const isInject = L === data.inject_at;
          return (
            <div
              key={L}
              className="flex items-center gap-1.5 text-[10px] font-mono"
            >
              <span
                className={`w-8 shrink-0 ${isInject ? "text-amber-300" : "text-gray-400"}`}
                title={isInject ? "read out where it is applied" : undefined}
              >
                L{L}
              </span>
              <span className="w-11 text-gray-500 shrink-0" title="token agreement">
                {(r.token_agreement * 100).toFixed(1)}%
              </span>
              <span className="w-11 text-gray-500 shrink-0" title="± sd across problems">
                ±{r.sd.toFixed(3)}
              </span>
              <span className="flex-1 h-2 bg-gray-800/50 rounded overflow-hidden min-w-8">
                <span
                  className="block h-full rounded"
                  style={{
                    width: `${(r.mean / max) * 100}%`,
                    backgroundColor: isInject ? "#fbbf24" : "#c084fc",
                    opacity: 0.7,
                  }}
                />
              </span>
              <span className="w-12 text-right text-gray-300 shrink-0">
                {r.mean.toFixed(4)}
              </span>
            </div>
          );
        })}
      </div>

      <p className="text-[10px] text-gray-500 leading-relaxed border-t border-border pt-1.5">
        Columns: extraction layer · token agreement · ± sd · Δ{data.metric}{" "}
        · value. Friedman across the {layers.length} layers: p ={" "}
        {data.friedman_p.toExponential(1)}. The effect is{" "}
        <span className="text-gray-300">{data.ratio_top_bottom.toFixed(2)}×</span>{" "}
        larger read out at L{layers[layers.length - 1]} than at L{layers[0]} with
        the injection layer unchanged
        {sat && sat.p > 0.05 ? (
          <>
            , and it stops growing at the injection layer (L{sat.pair[1]} vs
            L{sat.pair[0]}, p = {sat.p.toFixed(2)}) — reading the direction
            out past where it is applied buys nothing
          </>
        ) : null}
        . Token agreement barely varies across the same range — though it
        sits about 6% below the inert control at every one of them, so the
        intervention is never free; only the distributional divergence grows
        with extraction depth.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------

/**
 * Cross-layer cosine, with the null floor it has to be read against.
 *
 * Two vectors extracted from the same model share most of their direction
 * through the residual stream's own geometry, so a high cosine is the
 * expected result and is not by itself evidence that the extraction found
 * the same concept at two layers. The floor column is a random control
 * with matched sample sizes; only the excess over it means anything.
 */
function NullFloorTable({ data }: { data: NullFloorFile }) {
  const names = Object.keys(data.directions);
  const layers = data.layers;
  return (
    <div className="flex flex-col gap-2.5 max-h-80 overflow-y-auto">
      <div className="text-[10px] text-gray-500">
        Mean cosine between the same direction extracted at different layers,
        against a random control with the same sample sizes.
      </div>
      {names.map((name) => {
        const d = data.directions[name];
        const excess = d.excess_over_null;
        const ds = layers
          .map((L) => d.cohens_d[String(L)])
          .filter((x): x is number => x != null);
        return (
          <div key={name}>
            <div className="text-[10px] font-medium text-gray-300 mb-1">
              {name}
            </div>
            <div className="flex items-center gap-1.5 text-[10px] font-mono">
              <span className="w-24 text-gray-500 shrink-0">real</span>
              <span className="w-11 text-gray-300 shrink-0">
                {d.mean_offdiagonal_cosine >= 0 ? "+" : ""}
                {d.mean_offdiagonal_cosine.toFixed(3)}
              </span>
              <span className="w-16 text-gray-500 shrink-0" title="null floor">
                {d.null_mean_offdiagonal_cosine == null
                  ? "—"
                  : `floor ${d.null_mean_offdiagonal_cosine >= 0 ? "+" : ""}` +
                    d.null_mean_offdiagonal_cosine.toFixed(3)}
              </span>
              <span
                className={`w-16 shrink-0 ${
                  excess == null
                    ? "text-gray-500"
                    : excess > 0.15
                    ? "text-emerald-400"
                    : excess > 0.05
                    ? "text-amber-400"
                    : "text-red-400"
                }`}
              >
                {excess == null ? "" : `+${excess.toFixed(3)} over`}
              </span>
              <span className="flex-1 text-right text-gray-500 truncate">
                {ds.length
                  ? `d ${Math.min(...ds).toFixed(2)}…${Math.max(...ds).toFixed(2)}`
                  : ""}
              </span>
            </div>
          </div>
        );
      })}
      <p className="text-[10px] text-gray-500 leading-relaxed border-t border-border pt-1.5">
        A bare cross-layer cosine is uninterpretable: depending on how the
        control is built, the floor for this statistic runs from ~0.00 to
        ~0.87. Read the excess over the floor, not the cosine. Cohen&apos;s d
        (right) separates a real contrast far better than the cosine does —
        it is a within-layer statistic and so is not inflated by the shared
        component the cosine picks up.
      </p>
    </div>
  );
}

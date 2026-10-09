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
  // ⚠⚠ 第三十一笔：这个 state 是**修一个整页白屏**用的。
  //   原来渲染条件是 `{data != null && file.kind === "extraction" ? ... }`，
  //   而 setData(null) 在 useEffect 里 —— 它**晚一轮渲染**。
  //   ⇒ 切档那一瞬间：`file.kind` 已经是 "extraction"，
  //     `data` 却还是**上一档**的数据（idx=0 是 SweepRow[]，一个数组），
  //     于是 <ExtractionTable data={数组}> 渲染时
  //     `Object.keys(data.per_layer)` 拿到 undefined ⇒ TypeError ⇒
  //     Next 的 error boundary 接管，**整页白屏**。
  //   实测：bodyLen 23093 → 103，页面变成
  //     「Application error: a client-side exception has occurred」。
  //   ⇒ 只要把下拉框切到「Extraction layer vs effect」或
  //     「Cross-layer cosine」就必崩 —— 而默认档是 0，所以**每次都崩**。
  //   ⇒ 修法：记下 data 来自哪个 url，只在 `loadedFor === file.url` 时渲染。
  //     这样 stale data 根本到不了新 kind 的组件。
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const file = FILES[idx];

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    setLoadedFor(null);
    fetch(file.url)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        return r.json();
      })
      .then((j) => {
        if (!cancelled) {
          setData(j);
          setLoadedFor(file.url);
        }
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
    // ⚠⚠ 第三十一笔：这一整块原来**一个 data-* 都没有** ⇒ 它既不进覆盖矩阵，
    //   也不进探针的未标记段落清单（那份清单当时还写死了 8 个面板名），
    //   于是「ArchivedExperiments 里那句手写的 6%」三重隐形。
    //   另注意这个面板靠 <select> 切 6 个文件，**默认 idx=0**，
    //   而承载那句话的 extraction 表在 idx=4 ⇒ 默认视图里根本看不到它。
    //   data-archived / data-archived-file 让判据能定位并切过去。
    <div className="flex flex-col gap-2 p-4 rounded-lg bg-panel border border-border"
         data-archived="ready">
      <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
        Archived experiments
      </h2>
      <a href="/bpath-explorer" className="mt-2 block text-xs text-sky-300">
        B 路逐位置干预：剂量响应、token 反查与 3D 状态位移 →
      </a>

      <select
        data-archived-file={String(idx)}
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

      {loadedFor === file.url && data != null && file.kind === "sweep" ? (
        <SweepTable rows={data as SweepRow[]} />
      ) : null}
      {loadedFor === file.url && data != null && file.kind === "scan" ? (
        <ScanTable data={data as ScanFile} />
      ) : null}
      {loadedFor === file.url && data != null && file.kind === "extraction" ? (
        <ExtractionTable data={data as ExtractionFile} />
      ) : null}
      {loadedFor === file.url && data != null && file.kind === "nullfloor" ? (
        <NullFloorTable data={data as NullFloorFile} />
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------

function SweepTable({ rows }: { rows: SweepRow[] }) {
  // Collapse to one row per (direction, strength).
  //
  // The 24-problem file stores 96 rows: 24 problems x 2 directions x 2
  // strengths. Rendering them raw produced 24 rows that all looked identical
  // under the same (direction, strength) pair, which is also why the React
  // key `${direction}-${strength}` collided 24 times. The mean is the honest
  // summary of a 24-problem run, and the per-problem spread below it is what
  // says whether that mean is worth anything.
  type Cell = {
    direction: string;
    strength: number;
    rows: SweepRow[];
    meanDe: number;
    meanAgreement: number;
    // Worst case across problems, not the mean: this column answers "how far
    // did the paths separate at their worst", and averaging maxima would
    // report the gentlest problem instead of the dangerous one.
    maxDiv: number;
  };

  const byKey: { key: string; cell: Cell }[] = [];
  const seen = new Map<string, { direction: string; strength: number; rows: SweepRow[] }>();
  for (const r of rows) {
    const key = `${r.direction} | ${r.strength}`;
    let e = seen.get(key);
    if (!e) {
      e = { direction: r.direction, strength: r.strength, rows: [] };
      seen.set(key, e);
      byKey.push({ key, cell: e as Cell });
    }
    e.rows.push(r);
  }
  for (const { cell } of byKey) {
    const des = cell.rows.map(
      (r) => r.summary.mean_entropy_primary - r.summary.mean_entropy_shadow
    );
    cell.meanDe = des.reduce((a, b) => a + b, 0) / des.length;
    const agr = cell.rows.map((r) => r.summary.token_agreement);
    cell.meanAgreement = agr.reduce((a, b) => a + b, 0) / agr.length;
    cell.maxDiv = Math.max(...cell.rows.map((r) => r.summary.max_divergence));
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

      {byKey.map(({ key, cell: g }) => {
        // Scale the entropy bar to the largest |mean Δentropy| in the file.
        const maxDe = Math.max(...byKey.map((c) => Math.abs(c.cell.meanDe)), 1e-6);
        // Per-problem spread, when the file has more than one prompt.
        const spread = (() => {
          if (nProblems < 2) return null;
          const des = g.rows.map(
            (r) => r.summary.mean_entropy_primary - r.summary.mean_entropy_shadow
          );
          if (des.length < 2) return null;
          const m = des.reduce((a, b) => a + b, 0) / des.length;
          const sd = Math.sqrt(
            des.reduce((a, b) => a + (b - m) ** 2, 0) / (des.length - 1)
          );
          return { sd, m };
        })();
        const sdExceedsMean =
          spread != null && Math.abs(spread.m) > 0 && spread.sd > Math.abs(spread.m);

        return (
          <div key={key}>
            <div className="text-[10px] font-medium text-gray-300 mb-1">
              {g.direction}
            </div>
            <div className="space-y-0.5">
              {byKey
                .filter((c) => c.cell.direction === g.direction)
                .map(({ key: rk, cell: r }) => {
                  const de = r.meanDe;
                  const isControl = r.strength === 0;
                  const w = (Math.abs(de) / maxDe) * 50;
                  return (
                    <div
                      key={rk}
                      className="flex items-center gap-1.5 text-[10px] font-mono"
                    >
                      <span className="w-8 text-gray-500 shrink-0">
                        {r.strength.toFixed(2)}
                      </span>
                      <span className="w-11 text-gray-500 shrink-0" title={`token agreement, mean of ${r.rows.length} problems`}>
                        {(r.meanAgreement * 100).toFixed(0)}%
                      </span>
                      <span className="w-11 text-right shrink-0">
                        {isControl ? (
                          <span className="text-emerald-500">ctrl</span>
                        ) : (
                          <span
                            style={{
                              color: de < 0 ? "#60a5fa" : "#fb923c",
                            }}
                            title={`mean of ${r.rows.length} problems`}
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
                      title={`max per-layer divergence, worst of ${r.rows.length} problems`}
                    >
                      {r.maxDiv.toFixed(3)}
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
        divergence. Each row is the mean over all problems in the file, with
        the per-problem standard deviation printed underneath. Rows at
        strength 0.00 are controls — they inject a zero vector and must come
        back at exactly zero divergence, which is what makes the other rows
        attributable to the intervention.
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
  // ⚠⚠ 第三十一笔：原来末段手写「about 6% below the inert control」。
  //   产物里 token_agreement 逐层现算（见下）⇒ 距 1.0 的缺口是
  //   **5.40–6.01 个百分点**（均值 5.64），不是每层都 6%：
  //   L8 只有 5.40。所以「at every one of them … 6%」不成立。
  //   基准取 1.0 是**定义**推的（零强度注入 ⇒ 逐 token 不变），
  //   产物里**没有**单独实测的 inert control token_agreement 字段 ——
  //   顶层那个 control = 0.0 是**效应量指标** mean_logit_kl 的对照，
  //   与 token agreement 是两个量。下面那句话里必须说清这件事。
  const taVals = layers.map((L) => data.per_layer[String(L)].token_agreement);
  const gapLo = (1 - Math.max(...taVals)) * 100;
  const gapHi = (1 - Math.min(...taVals)) * 100;

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
        {/* ⚠⚠ 第三十一笔：原来这里是手写的
            「sits about 6% below the inert control at every one of them」，
            三处问题：
             ① 6% 是字面量，而且「每一层都约 6%」不成立
                （实测缺口 5.40–6.01 个百分点，L8 只有 5.40）。
             ② **产物里没有 inert control 的 token_agreement 字段**。
                基准 1.0 是**定义**推出来的：零强度注入 ⇒ 输出逐 token 不变。
                这一句必须把这件事说出来，否则读者会以为有实测对照。
             ③ 「the inert control」与本卡顶栏「controls read exactly 0.0000」
                **撞名但不是同一个东西**：顶栏那个 0.0000 是 mean_logit_kl 的
                对照，这里说的是 token agreement 的 1.0 基准。
                混读会得出「对照是 0，所以差 6 个百分点」这种不存在的对比。
                ⇒ 下面刻意不叫「control」，改说「zero-strength baseline」，
                  并显式指出产物里没有单独实测它。
            data-ta-gap 属性只作交叉核对，主体断言在可见文案上。 */}
        . Token agreement barely varies across the same range (
        {(Math.min(...taVals) * 100).toFixed(2)}–
        {(Math.max(...taVals) * 100).toFixed(2)}
        %), i.e. it stays{" "}
        <span className="font-mono text-gray-300"
              data-ta-gap-lo={gapLo.toFixed(2)} data-ta-gap-hi={gapHi.toFixed(2)}>
          {gapLo.toFixed(2)}–{gapHi.toFixed(2)} percentage points
        </span>{" "}
        short of the zero-strength baseline of 1.0 — a baseline fixed{" "}
        <b>by definition</b> (a zero-strength injection leaves every token
        unchanged), not a separately measured control: the artifact only
        records the effect-size control, which reads exactly 0.0000 above.
        The intervention is therefore never free; only the distributional
        divergence grows with extraction depth.
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

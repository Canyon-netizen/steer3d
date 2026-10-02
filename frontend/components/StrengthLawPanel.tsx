"use client";

/**
 * Strength is the cost; direction is the destination. — What the steering
 * vectors can and cannot be told apart on.
 *
 * Everything else on this page about the six shipped directions is either
 * geometric (are they non-random? yes — the panel above) or behavioural
 * (do they change answers? net zero — the panel above that). This panel
 * states the one general law the data actually supports, because it is the
 * part that transfers to any steering vector anyone extracts:
 *
 *     ‖h + s·rms(L)·u‖  departs from its own first-order prediction by
 *
 *         ≈ ½ · (s · rms(L) / ‖h‖)²
 *
 * Note what is **not** in that expression: `u`. The geometric price of an
 * injection is set by how far you push relative to how big the state
 * already is. The direction does not appear.
 *
 * So the law makes a falsifiable prediction, and it was tested: sixteen
 * seeded random directions of the same length, injected at the same
 * strengths, should land on the same curve as the four semantically-named
 * ones. They do — within 0.037 percentage points at strength ≤ 0.2, while
 * the spread *across* the named directions is 0.104 pp.
 *
 * That is the uncomfortable part, and the reason this panel exists:
 *
 *     A random vector costs exactly as much geometry as the one we call
 *     "confidence".
 *
 * Which means the cost carries no information about whether the direction
 * means anything. Cost can be predicted before you run anything; meaning
 * cannot, and has to be earned separately.
 *
 * The law is not claimed to hold everywhere. Above strength 0.2 the
 * quadratic approximation itself runs out of depth — the numbers are
 * printed here too, with the regime they are valid in marked, rather than
 * quietly restricted to the flattering range.
 */

import { useEffect, useMemo, useState } from "react";

type Row = {
  layer: number;
  strength: number;
  a_mean: number;
  pred_pct: number;
  real_dev_mean: number;
  real_dev_spread: number;
  random_dev_mean: number;
  random_dev_std: number;
  random_dev_min: number;
  random_dev_max: number;
  real: Record<string, { dev_pct: number; pred_pct: number; cos_mean: number }>;
};

type Law = {
  law: string;
  design: {
    layers: number[];
    strengths: number[];
    n_points: number;
    n_random: number;
    seed: number;
    real_directions: string[];
  };
  toy_selfcheck: string;
  rows: Row[];
  conclusions: {
    safe_regime: {
      strength_max: number;
      max_direction_spread_pp: number;
      max_real_vs_random_gap_pp: number;
      direction_independent: boolean;
      random_indistinguishable: boolean;
    };
    beyond_safe_regime: {
      strengths: number[];
      max_direction_spread_pp: number;
      max_real_vs_random_gap_pp: number;
    };
  };
};

const SHOW_LAYER = 20;     // where the 32k batch injects
const W = 340;
const H = 120;
const PAD_L = 30;
const PAD_B = 22;
const PAD_T = 8;
const PAD_R = 8;

export default function StrengthLawPanel() {
  const [law, setLaw] = useState<Law | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch("/latent/data/linearity_law.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j: Law) => alive && setLaw(j))
      .catch((e) => alive && setErr(String(e.message || e)));
    return () => { alive = false; };
  }, []);

  const view = useMemo(() => {
    if (!law?.rows) return null;
    const rows = law.rows.filter((r) => r.layer === SHOW_LAYER)
                        .sort((a, b) => a.strength - b.strength);
    return rows.length ? { rows, safe: law.conclusions.safe_regime } : null;
  }, [law]);

  if (err) {
    return (
      <div className="rounded bg-bg/40 border border-border p-3" data-law="error">
        <Head nRandom={null} />
        <p className="text-[10px] text-red-400 leading-relaxed mt-1">
          linearity artifact unavailable: {err}
        </p>
      </div>
    );
  }

  if (!law || !view) {
    return (
      <div className="rounded bg-bg/40 border border-border p-3" data-law="loading">
        <Head nRandom={null} />
        <p className="text-[10px] text-gray-500 leading-relaxed mt-1">Loading…</p>
      </div>
    );
  }

  const { rows, safe } = view;
  const maxY = Math.max(...rows.map((r) => r.pred_pct), ...rows.map((r) => r.real_dev_mean)) * 1.12;
  const maxA = Math.max(...rows.map((r) => r.a_mean));
  const sx = (a: number) => PAD_L + (a / maxA) * (W - PAD_L - PAD_R);
  const sy = (p: number) => PAD_T + (1 - p / maxY) * (H - PAD_T - PAD_B);

  // s=0.2 is where the quadratic approximation stops being usable; the
  // band past it is drawn hatched rather than dropped.
  const aAtSafe = rows.reduce((best, r) =>
    r.strength <= safe.strength_max && r.a_mean > best ? r.a_mean : best, 0);

  return (
    <div className="rounded bg-bg/40 border border-border p-3" data-law="ready">
      <Head nRandom={law.design.n_random} />

      <p className="text-[10px] text-gray-500 leading-relaxed mt-1">
        Push the residual stream at L{SHOW_LAYER} and measure how far its norm
        departs from what a first-order expansion predicts:
      </p>

      <div className="font-mono text-[10.5px] text-gray-300 bg-bg/60 rounded px-2 py-1.5 mt-1 mb-1.5">
        Δ ≈ ½ · ( s · rms / ‖h‖ )²
        <span className="text-gray-500"> — no <i>u</i> in it.</span>
      </div>

      <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="overflow-visible">
        {/* out-of-depth region: the quadratic term is no longer the whole story */}
        <rect
          x={sx(aAtSafe)} y={PAD_T}
          width={W - PAD_R - sx(aAtSafe)} height={H - PAD_T - PAD_B}
          fill="#f59e0b" opacity={0.07}
          data-outofdepth-from={aAtSafe}
        />
        <text x={W - PAD_R} y={PAD_T + 8} fontSize={7} fill="#b07d2a" textAnchor="end">
          approximation out of depth
        </text>

        {/* axes */}
        <line x1={PAD_L} x2={W - PAD_R} y1={H - PAD_B} y2={H - PAD_B}
              stroke="#3a4353" strokeWidth={1} />
        <line x1={PAD_L} x2={PAD_L} y1={PAD_T} y2={H - PAD_B}
              stroke="#3a4353" strokeWidth={1} />
        <text x={PAD_L - 3} y={PAD_T + 6} fontSize={7} fill="#6b7688" textAnchor="end">
          {maxY.toFixed(0)}%
        </text>
        <text x={PAD_L - 3} y={H - PAD_B} fontSize={7} fill="#6b7688" textAnchor="end">0%</text>
        <text x={PAD_L} y={H - PAD_B + 10} fontSize={7} fill="#6b7688">
          s·rms/‖h‖
        </text>

        {/* the analytic curve: ½a²
            The ×100 is load-bearing. ½a² is a *fraction*; the axis is in
            percent. Without it the whole curve is drawn at 0.1% on a
            16% axis and reads as a flat line pinned to the bottom —
            which is exactly what the browser measured before this fix. */}
        <path
          d={Array.from({ length: 41 }, (_, i) => {
            const a = (maxA * i) / 40;
            const p = 100 * 0.5 * a * a;
            return `${i === 0 ? "M" : "L"}${sx(a).toFixed(1)},${sy(p).toFixed(1)}`;
          }).join(" ")}
          fill="none" stroke="#8b95a8" strokeWidth={1} strokeDasharray="3 2"
          data-curve="analytic"
        />

        {/* measured: random directions, as a vertical span */}
        {rows.map((r) => (
          <line
            key={`r${r.strength}`}
            x1={sx(r.a_mean)} x2={sx(r.a_mean)}
            y1={sy(r.random_dev_max)} y2={sy(r.random_dev_min)}
            stroke="#f59e0b" strokeWidth={3} opacity={0.55}
            data-rnd-span={r.strength}
            data-rnd-lo={r.random_dev_min} data-rnd-hi={r.random_dev_max}
          />
        ))}

        {/* measured: the named directions */}
        {rows.map((r) => (
          <circle
            key={`m${r.strength}`}
            cx={sx(r.a_mean)} cy={sy(r.real_dev_mean)} r={2.6}
            fill="#60a5fa"
            data-named={r.strength} data-dev={r.real_dev_mean} data-pred={r.pred_pct}
          />
        ))}
      </svg>

      <p className="text-[10px] text-gray-500 leading-relaxed mt-0.5">
        <span className="text-gray-400 font-mono">— —</span> ½a² 解析值　
        <span className="text-[#60a5fa]">●</span> 四个命名方向的实测　
        <span className="text-[#f59e0b]">▮</span> {law.design.n_random} 个随机
        方向的实测区间
      </p>

      <p className="text-[10px] text-gray-500 leading-relaxed mt-1.5">
        At strength ≤ {safe.strength_max} the {law.design.n_random} seeded random
        directions sit within{" "}
        <span className="font-mono text-gray-400" data-gap={safe.max_real_vs_random_gap_pp}>
          {safe.max_real_vs_random_gap_pp.toFixed(3)} pp
        </span>{" "}
        of the named ones, and the named ones span{" "}
        <span className="font-mono text-gray-400" data-spread={safe.max_direction_spread_pp}>
          {safe.max_direction_spread_pp.toFixed(3)} pp
        </span>{" "}
        among themselves. Denominator: {law.design.n_points} recorded hidden
        states per point, {law.design.real_directions.length} named +{" "}
        {law.design.n_random} random directions, over{" "}
        {law.design.strengths.filter((s) => s <= safe.strength_max).length}{" "}
        strengths × {law.design.layers.length} layers.
      </p>

      <p className="text-[10px] text-gray-400 leading-relaxed mt-1">
        <b>So a random vector costs exactly as much geometry as the one called
        &ldquo;confidence&rdquo;.</b> The cost is set by how hard you push, and
        it carries no information about whether the direction means anything.
      </p>

      <p className="text-[10px] text-gray-600 leading-relaxed mt-1.5">
        Where it stops holding: above strength {safe.strength_max} the spread
        grows to{" "}
        <span className="font-mono">
          {law.conclusions.beyond_safe_regime.max_direction_spread_pp.toFixed(2)} pp
        </span>{" "}
        and the random-vs-named gap to{" "}
        <span className="font-mono">
          {law.conclusions.beyond_safe_regime.max_real_vs_random_gap_pp.toFixed(2)} pp
        </span>
        . Those points are not counterexamples — the quadratic term is simply
        no longer the whole story there. The existing 32k batch sits at
        strength 0.2, just inside the boundary.
      </p>

      <p className="text-[10px] text-gray-600 leading-relaxed mt-1">
        The measurement device was checked against a toy input with a closed-form
        answer ({law.toy_selfcheck}) before being pointed at the recordings.
      </p>
    </div>
  );
}

function Head({ nRandom }: { nRandom: number | null }) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="text-[10px] text-gray-500 uppercase tracking-wider">
        Strength law
      </span>
      <span className="text-[9px] text-gray-600 font-mono" data-law-random={nRandom ?? ""}>
        {nRandom == null ? "measured" : `${nRandom} random controls`}
      </span>
    </div>
  );
}

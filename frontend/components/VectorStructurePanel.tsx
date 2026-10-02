"use client";

/**
 * How structured are these vectors, really? — measured against 200
 * random directions of the same length.
 *
 * The rest of the steering story on this page is behavioural: the offline
 * batch shows where two arms first diverge. That says the vector does
 * something. It does not say the vector is not just a random direction
 * that happened to correlate with something, which is the objection that
 * every steering-vector result has to answer.
 *
 * So this panel reports a purely geometric measurement. For each
 * direction, the fraction of its length that falls inside the top-3
 * principal subspace of the recorded hidden states at that layer:
 *
 *     subspace_frac = ‖V₃ v‖ / ‖v‖
 *
 * A uniformly random 2048-d vector projects almost nothing into a 3-d
 * subspace. Measured over 200 seeded random directions at L20: mean
 * 0.036, sd 0.014, largest of the 200 draws 0.085. Every shipped
 * direction clears that by a wide margin — the largest real value at L20
 * is 0.571, 6.8x that ceiling. The same direction reaches its own peak of
 * 0.721 at L14, 9.3x the 200-draw ceiling *at that layer* (0.078).
 * Those are two different ratios at two different layers; do not merge
 * them into one "8x".
 *
 * What this does and does not establish:
 *
 *  - It does establish that the directions are not arbitrary. They point
 *    somewhere the model's own states actually travel.
 *  - It does not establish that "confidence" is what that somewhere means.
 *    That claim needs the behavioural evidence on the panel above, and
 *    even there the net effect on correctness is zero.
 *  - A 3-d subspace is a small slice of 2048. A direction can be
 *    non-random by this measure and still be mostly arbitrary; the number
 *    is a lower bound on structure, not a measure of it.
 *
 * Every direction peaks at L14, the layer the diff-of-means was extracted
 * at, and falls off on both sides. Only *two* of the six are sign flips —
 * `confidence_down` is `confidence_up` negated and `reasoning_shallow`
 * is `reasoning_deep` negated (both carry `derived_from` in the
 * registry, and their pairwise cosine is exactly -1.0). So the six
 * labels describe **four** distinct vectors, and the two flipped ones
 * agree to every printed digit at every layer, which is a
 * self-consistency check on the arithmetic. `caution` and `creativity`
 * are not a pair — their cosine is +0.34.
 */

import { useEffect, useMemo, useState } from "react";

type PerLayer = {
  random_mean: number;
  random_std: number;
  random_max: number;
  best_real: number;
  best_over_random_max: number;
  family_wise_rate_if_bar_is_200_max: number;
  real: Record<string, number>;
  empirical_p_gt_random: Record<string, number>;
};

type Scan = {
  n_random: number;
  seed: number;
  topk: number;
  layers: number[];
  top3_variance_frac: Record<string, number>;
  unpaired_cosine: Record<string, { cosine: number; is_flip: boolean }>;
  sign_flip_pairs: { pair: [string, string]; max_abs_diff: number; all_equal: boolean }[];
  per_layer: Record<string, PerLayer>;
};

const INJECT_LAYER = "20";     // where the 32k batch injects
const LAYERS = ["12", "14", "16", "20", "24"];

/**
 * Verified against the .npy files: pairwise cosine is exactly -1.0 and
 * ‖v_i + v_j‖ is exactly 0.0. Both members of a pair carry the same
 * projection length, because ‖V₃(−v)‖ = ‖V₃ v‖. The panel marks them
 * rather than hiding the duplicate bars, because a reader seeing two
 * equal bars is entitled to wonder whether the measurement is broken.
 */
const SIGN_FLIP: Record<string, string> = {
  confidence_down: "confidence_up",
  reasoning_shallow: "reasoning_deep",
};

const LABEL: Record<string, string> = {
  confidence_up: "Confidence ↑",
  confidence_down: "Confidence ↓",
  caution: "Cautious",
  creativity: "Creative",
  reasoning_deep: "Deep reasoning",
  reasoning_shallow: "Quick answer",
};

export default function VectorStructurePanel() {
  const [scan, setScan] = useState<Scan | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch("/latent/data/vector_random_control.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j: Scan) => alive && setScan(j))
      .catch((e) => alive && setErr(String(e.message || e)));
    return () => { alive = false; };
  }, []);

  const view = useMemo(() => {
    if (!scan?.per_layer) return null;
    const at = scan.per_layer[INJECT_LAYER];
    if (!at) return null;
    const names = Object.keys(at.real).sort((a, b) => at.real[b] - at.real[a]);
    return { at, names, peak: names.length ? names[0] : null };
  }, [scan]);

  if (err) {
    return (
      <div className="rounded bg-bg/40 border border-border p-3" data-structure="error">
        <Head nRandom={scan?.n_random ?? null} />
        <p className="text-[10px] text-red-400 leading-relaxed mt-1">
          random-control artifact unavailable: {err}
        </p>
      </div>
    );
  }

  if (!scan || !view) {
    return (
      <div className="rounded bg-bg/40 border border-border p-3" data-structure="loading">
        <Head nRandom={scan?.n_random ?? null} />
        <p className="text-[10px] text-gray-500 leading-relaxed mt-1">Loading…</p>
      </div>
    );
  }

  const { at, names } = view;
  const rnd = at.random_max;
  const v3 = scan.top3_variance_frac?.[INJECT_LAYER] ?? NaN;
  // Bar scale: the largest real value, with the random ceiling marked.
  const top = Math.max(...names.map((n) => at.real[n]), rnd);
  const W = 340;
  const rowH = 15;
  const BAR_X = 92;
  const BAR_W = W - 96;
  const rndX = BAR_X + (rnd / top) * BAR_W;

  return (
    <div className="rounded bg-bg/40 border border-border p-3" data-structure="ready">
      <Head nRandom={scan?.n_random ?? null} />

      <p className="text-[10px] text-gray-500 leading-relaxed mt-1 mb-1.5">
        How much of each vector points along the directions the model&apos;s own
        hidden states actually travel — the top-{scan.topk} principal subspace
        at L{INJECT_LAYER}, which holds only{" "}
        <span className="font-mono text-gray-400" data-top3var={v3}>
          {(v3 * 100).toFixed(1)}%
        </span>{" "}
        of the variance there. A random vector of the same length would land
        at{" "}
        <span className="font-mono text-gray-400">{at.random_mean.toFixed(3)}</span>.
        The largest of the {scan.n_random} random draws is{" "}
        <span className="font-mono text-gray-400">{rnd.toFixed(3)}</span>; the
        largest real direction here is{" "}
        <span className="font-mono text-gray-400" data-ratio={at.best_over_random_max}>
          {at.best_over_random_max.toFixed(1)}×
        </span>{" "}
        that.
      </p>

      <svg width="100%" viewBox={`0 0 ${W} ${names.length * rowH + 16}`} className="overflow-visible">
        {/* The ceiling of all 200 random draws, at its ACTUAL x on this scale.
            Drawing it full-width would be a lie in the reader's favour being
            wrong: it would put the random ceiling at the far right, so every
            real bar would look like it barely clears it. The six real bars
            reach 5x-7x further right than this line. */}
        <line
          x1={rndX} x2={rndX}
          y1={-4} y2={names.length * rowH}
          stroke="#f59e0b" strokeWidth={1} strokeDasharray="2 2"
          data-rnd-line={rndX} data-rnd={rnd} data-top={top}
        />
        <text x={rndX + 3} y={-2} fontSize={7} fill="#f59e0b">
          best of {scan.n_random} random = {rnd.toFixed(3)}
        </text>

        {names.map((n, i) => {
          const v = at.real[n];
          const w = ((v / top) * BAR_W).toFixed(1);
          const flip = SIGN_FLIP[n];
          return (
            <g key={n} transform={`translate(0, ${i * rowH + 8})`}>
              <text x={BAR_X - 4} y={8} fontSize={8} fill="#8891a4" textAnchor="end">
                {LABEL[n] || n}
              </text>
              <rect x={BAR_X} y={1} width={w} height={9}
                    fill={flip ? "#7c8aa0" : "#60a5fa"} rx={1}
                    data-dir={n} data-frac={v} data-drawn={w} data-top={top}
                    data-flip={flip || ""} />
              <text x={BAR_X + Number(w) + 4} y={8} fontSize={8} fill="#c9d4e4">
                {v.toFixed(3)}
              </text>
              {flip ? (
                <text x={BAR_X + Number(w) + 30} y={8} fontSize={7} fill="#6b7688">
                  = −{flip}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>

      <p className="text-[10px] text-gray-500 leading-relaxed mt-1">
        {scan.n_random} seeded random directions of equal length, same
        projection: mean {at.random_mean.toFixed(3)}, sd {at.random_std.toFixed(3)},
        largest {rnd.toFixed(3)}. Every shipped direction clears it; the
        empirical tail is under{" "}
        <span className="font-mono">
          {at.family_wise_rate_if_bar_is_200_max.toFixed(3)}
        </span>{" "}
        (1/{scan.n_random}).
      </p>

      {/* --- where the structure lives --- */}
      <div className="text-[10px] text-gray-500 uppercase tracking-wider mt-2 mb-1">
        Where the structure sits
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr auto", rowGap: 2 }}>
        {names.map((n) => {
          const vals = LAYERS.map((L) => scan.per_layer[L]?.real[n] ?? 0);
          const peakL = LAYERS[vals.indexOf(Math.max(...vals))];
          const isDef = peakL === "14";
          return (
            <div key={n} style={{ display: "contents" }}>
              <span className="text-[9.5px] text-gray-500 truncate">{LABEL[n] || n}</span>
              <span className="text-[9px] font-mono text-gray-500"
                    data-peak={peakL} data-peak-frac={vals[vals.indexOf(Math.max(...vals))]}>
                L{peakL} · {vals[vals.indexOf(Math.max(...vals))].toFixed(3)}
                {isDef ? " ← extracted here" : ""}
              </span>
            </div>
          );
        })}
      </div>

      <p className="text-[10px] text-gray-600 leading-relaxed mt-1.5">
        All six peak at L14, the layer the diff-of-means was taken from, and
        thin out on both sides. Two of the six are sign flips of another
        one —{" "}
        <span className="font-mono text-gray-500">confidence_↓ = −confidence_↑</span>{" "}
        and{" "}
        <span className="font-mono text-gray-500">
          reasoning_shallow = −reasoning_deep
        </span>{" "}
        (cosine exactly −1.0), which is why their bars are identical
        lengths. A projection length is blind to sign, so a flipped pair
        agreeing is a self-consistency check, not evidence of two
        findings. The six labels are four vectors.
      </p>

      <p className="text-[10px] text-gray-600 leading-relaxed mt-1">
        What this does <b>not</b> say: that the structure means
        &ldquo;confidence&rdquo;. It says the direction is not arbitrary. Naming
        it is a separate claim, resting on the behavioural panel above — where
        the net change in correct answers is zero.
      </p>
    </div>
  );
}

function Head({ nRandom }: { nRandom: number | null }) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="text-[10px] text-gray-500 uppercase tracking-wider">
        Are these directions arbitrary?
      </span>
      <span className="text-[9px] text-gray-600 font-mono" data-n-random={nRandom ?? ""}>
        {nRandom == null ? "random controls" : `${nRandom} random controls`}
      </span>
    </div>
  );
}

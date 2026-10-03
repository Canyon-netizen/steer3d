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
 *    That claim needs the behavioural evidence on the panel above, where
 *    answer_power.json's `net_change` is 0 over the complete pairs.
 *  - A 3-d subspace is a small slice of 2048. A direction can be
 *    non-random by this measure and still be mostly arbitrary; the number
 *    is a lower bound on structure, not a measure of it.
 *
 * Every direction peaks at L14, the layer the diff-of-means was extracted
 * at (both layer numbers now come from the artifacts — see below), and
 * falls off on both sides. Only *two* of the six are sign flips —
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

// 第二十六笔新增：注入层 / 提取层的**唯一源头**。
// vector_roles.json 的 layers 块原文：
//   "native_extraction": 14, "journal_injection": 20
// 并附一句作者自己的提醒：「两个层都算了：一个方向在定义它的层和被使用的层，
// 未必是同一件事。」——页面把它们分开印，正是这句话的意思。
type VectorRoles = {
  layers: {
    native_extraction: number;
    journal_injection: number;
    note?: string;
  };
};

// 第二十四笔那个「净变化是 0」的**第二份副本**原来就在本组件的散文里
// （"where the net change in correct answers is zero"）。answer_power.json
// 里有现成的 `net_change` 字段，所以这里接它，而不是再抄一个字面量 0。
type AnswerPowerLite = {
  net_change: number;
  n_problems_in_batch: number;
  n_complete_pairs: number;
};

// ⚠⚠ 第二十六笔：这里原来有两条模块级字面量 ——
//   const INJECT_LAYER = "20";               // where the 32k batch injects
//   const LAYERS = ["12","14","16","20","24"];
// 两条都**在产物里有源**，只是渲染层没接：
//   · scan.layers               ← vector_random_control.json 顶层（Scan 类型里
//                                  早就声明了 `layers: number[]`，代码却当它不存在）
//   · roles.layers.journal_injection / .native_extraction
//                                ← vector_roles.json 的 layers 块（14 / 20）
// 写死它们的代价不是「多抄一次」：
//   产物换一层，页面**照旧印旧层号且不红** —— 因为判据与产品共用同一份字面量，
//   两边一起错，C2/C3/C4 全绿（第十三笔修 AXES 时就是这个形状，LAYERS 被漏了）。
// 而 "← extracted here" 那个标记判的是 `peakL === "14"`：它把「峰值层」当成
// 「提取层」印在页面上，而这两个是**不同的层**，前者是量出来的、后者是配置里的。
// 改完这一处，INJECT_LAYER / EXTRACT_LAYER / LAYERS 三者都从产物派生。

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
  const [roles, setRoles] = useState<VectorRoles | null>(null);
  const [pw, setPw] = useState<AnswerPowerLite | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    // ⚠ 第二十六笔：三个产物用 Promise.all 一次取齐（与 InterventionOutcomePanel
    //   同一套写法）。**刻意不合成一个文件**：三份各有各的生成脚本，
    //   合并等于让它们互相覆写，谁后跑谁赢，顺序错了没人报错。
    const get = (u: string) =>
      fetch(u).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))));
    Promise.all([
      get("/latent/data/vector_random_control.json"),
      get("/latent/data/vector_roles.json"),
      get("/latent/data/answer_power.json"),
    ])
      .then(([s, r, p]: [Scan, VectorRoles, AnswerPowerLite]) => {
        if (!alive) return;
        setScan(s); setRoles(r); setPw(p);
      })
      .catch((e) => alive && setErr(String(e.message || e)));
    return () => { alive = false; };
  }, []);

  // ---- 三个层号全部派生化（第二十六笔）--------------------------------
  // ⚠ 三者都用 `""` 而不是硬编码兜底：`""` 会让下面的 `view` 算出 null，
  //   走「Loading…」分支 —— 即「源没到就说没到」，
  //   而不是拿一个猜的层号先把页面印出来（第二十四笔：写死一个真值 = 冻结成装饰）。
  const LAYERS = (scan?.layers ?? []).map(String);
  const INJECT_LAYER = roles == null ? "" : String(roles.layers.journal_injection);
  const EXTRACT_LAYER = roles == null ? "" : String(roles.layers.native_extraction);

  const view = useMemo(() => {
    if (!scan?.per_layer || !INJECT_LAYER) return null;
    const at = scan.per_layer[INJECT_LAYER];
    if (!at) return null;
    const names = Object.keys(at.real).sort((a, b) => at.real[b] - at.real[a]);
    return { at, names, peak: names.length ? names[0] : null };
  }, [scan, INJECT_LAYER]);

  if (err) {
    return (
      <div className="rounded bg-bg/40 border border-border p-3" data-structure="error">
        <Head nRandom={scan?.n_random ?? null} />
        <p className="text-[10px] text-red-400 leading-relaxed mt-1">
          artifact unavailable: {err}
        </p>
        <p className="text-[10px] text-gray-500 leading-relaxed mt-1">
          需要 vector_random_control / vector_roles / answer_power 三份产物。
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

  // ---- 峰值层现算（第二十六笔）------------------------------------
  // 原来内联在下面的 map 里算了两遍（`vals.indexOf(Math.max(...vals))` 出现两次），
  // 而「峰值层 = extracted here」那个可见标记判的是写死的 "14"。
  // 提成函数后：既去掉了重复计算，也让下面那段散文能**数出**有几个方向真的
  // 峰在提取层，而不是像原来那样直接断言「All six」。
  const peakLayerOf = (n: string) => {
    const vals = LAYERS.map((L) => scan.per_layer[L]?.real[n] ?? 0);
    if (!LAYERS.length || !vals.length) return { peakL: "", peakV: NaN };
    const i = vals.indexOf(Math.max(...vals));
    return { peakL: LAYERS[i], peakV: vals[i] };
  };
  // 「六个方向里有几个峰在提取层」——**现算**。原来散文里那句
  // "All six peak at L14" 是一个没人核过的断言：若产物换层，散文照旧印 "All six"，
  // 而每行的标记会悄悄全灭，没有一条判据会红。
  const nPeakAtExtract = names.filter((n) => peakLayerOf(n).peakL === EXTRACT_LAYER).length;
  const nFlips = names.filter((n) => SIGN_FLIP[n]).length;
  const nDistinct = names.length - nFlips;
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
          const { peakL, peakV } = peakLayerOf(n);
          const isDef = EXTRACT_LAYER !== "" && peakL === EXTRACT_LAYER;
          return (
            <div key={n} style={{ display: "contents" }}>
              <span className="text-[9.5px] text-gray-500 truncate">{LABEL[n] || n}</span>
              <span className="text-[9px] font-mono text-gray-500"
                    data-peak-dir={n}
                    data-peak={peakL} data-peak-frac={peakV}
                    data-extract-layer={EXTRACT_LAYER}>
                L{peakL} · {peakV.toFixed(3)}
                {isDef ? " ← extracted here" : ""}
              </span>
            </div>
          );
        })}
      </div>

      <p className="text-[10px] text-gray-600 leading-relaxed mt-1.5">
        {/* ⚠ 第二十六笔：原来这里是「All six peak at L14, the layer the
            diff-of-means was taken from」——「six」「L14」两个数都是手抄的，
            而正文没有任何东西核它们。现算：{nPeakAtExtract}/{names.length} 真的峰在
            提取层，提取层号本身取自 vector_roles.json。 */}
        <span data-peak-at-extract={nPeakAtExtract} data-n-dirs={names.length}
              data-extract-layer={EXTRACT_LAYER}
              /* ⚠⚠ 第二十六笔的变异台发现的：只判**答案**（峰值层）不够。
                 把层名单从 5 层截断成前 2 层，argmax **一个都不变**
                 （六个方向在 L12/L14 里最大都还是 L14）⇒ 页面输出逐字相同，
                 于是任何核 peak 的判据都绿。⇒ 必须把**扫了哪几层**本身暴露出来，
                 让「名单被截断」在输出没变时也立刻可见。 */
              data-layers-scanned={LAYERS.join(",")}>
          {nPeakAtExtract} of the {names.length} peak at L{EXTRACT_LAYER}
        </span>
        {/* 用破折号而不是逗号收尾：JSX 会在这段文本前补一个空格，
            写成「L14 , the layer…」在页面上就是一个逗号前的空格。 */}
        {" — the layer the diff-of-means was taken from — and they thin out on "}
        both sides. {nFlips} of the {names.length} are sign flips of another
        one —{" "}
        <span className="font-mono text-gray-500">confidence_↓ = −confidence_↑</span>{" "}
        and{" "}
        <span className="font-mono text-gray-500">
          reasoning_shallow = −reasoning_deep
        </span>{" "}
        (cosine exactly −1.0), which is why their bars are identical
        lengths. A projection length is blind to sign, so a flipped pair
        agreeing is a self-consistency check, not evidence of two
        findings. The {names.length} labels are {nDistinct} vectors.
      </p>

      <p className="text-[10px] text-gray-600 leading-relaxed mt-1">
        What this does <b>not</b> say: that the structure means
        &ldquo;confidence&rdquo;. It says the direction is not arbitrary. Naming
        it is a separate claim, resting on the behavioural panel above — where
        the net change in correct answers is{" "}
        {/* ⚠ 第二十六笔：第二十四笔把答案面板自己那份「净变化是 0」查出来是
            **写死的常数**（恰好为真）。这里是同一句话的**第二份副本**，
            同样是写死。同样改成现算：answer_power.json 的 `net_change`。
            读不到就明说读不到，而不是印一个 0（未测 ≠ 实测为 0）。 */}
        {pw == null ? (
          <span data-net-change="">unavailable</span>
        ) : (
          <span data-net-change={pw.net_change}>
            {pw.net_change > 0 ? `+${pw.net_change}` : pw.net_change}
          </span>
        )}
        {pw == null ? "" : ` over ${pw.n_complete_pairs} complete pairs`}.
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

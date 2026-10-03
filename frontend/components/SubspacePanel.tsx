"use client";

/**
 * SubspacePanel — 4 条命名轴之外，残差流里还剩多少解释得了行为的方向？
 *
 * 这块面板存在的理由：前面那块（AxisReadoutPanel）回答「这 4 条轴各自指向什么」，
 * 但它没回答「**除了它们还有多少**」。而后者才是「通用解释向量理论」能不能
 * 成立的关键 —— 如果 4 条就是全部，那理论是封闭的；如果不是，就得知道缺的是什么。
 *
 * 三样东西必须同时显示，缺一不可：
 *   1. **地板**（把目标在轨迹内打乱后同一个方向还能预测多少）
 *      —— 缺了它，0.86 看着漂亮，但那可能是这套判据的噪声水平。
 *   2. **非对角最大**（同一张表里最高的**别人**）
 *      —— 缺了它，一条方向可能根本不是它自己的读出（caution 就是这么塌的）。
 *   3. **位置轴对照不衰减**
 *      —— 缺了它，「六条都塌了」和「装置测不出持续方向」是同一个现象，
 *      分不开。step_frac 在 Δ=100 仍有 0.71，说明装置有这个能力。
 *
 * 还有一个**必须印在页面上**的边界：这里测的是**可读性**，不是**因果性**。
 *
 * 数据由 `.cache/xcheck/` 下的三个脚本产出，经
 * `.cache/xcheck/build_subspace_readout.py` 压成本文件。
 * **最优方向在分析侧选定**，这里只负责显示。
 */
import { useEffect, useState } from "react";

type Row = {
  key: string;
  label: string;
  meaning: string;
  diagnostic: {
    diagonal: number;
    floor: number;
    offdiag_worst: number;
    offdiag_worst_cell: string;
    offdiag_worst_label: string;
    margin_over_offdiag: number | null;
    cos_to_named_axes: Record<string, number>;
    max_cos_to_named: number;
  };
  delta: Record<string, number>;
  delta20_null_p99: number | null;
  delta20_over_null: number | null;
  decay_x20: number | null;
};

type Payload = {
  question: string;
  convention: {
    layer: number;
    k_pca: number;
    stride: number;
    search_space: string;
    floor: string;
    note: string;
  };
  headline: {
    readable_directions_lower_bound: number;
    named_axes: number;
    greedy_obs_only: number;
    separation_threshold: number;
    caution_absorbed: string;
  };
  surface_directions: Row[];
  named_axis_readouts: { key: string; axis: string; delta: Record<string, number>; decay_x20: number }[];
  control: {
    key: string;
    label: string;
    delta: Record<string, number>;
    decay_x20: number;
    note: string;
  };
  char_pairwise_abs_cos: Record<string, number>;
  char_pairwise_note: string;
  verdict: string;
  not_claimed: string;
};

const DELTAS = ["0", "20", "100"] as const;
const AXES = ["confidence", "caution", "creativity", "reasoning_deep"] as const;

export default function SubspacePanel() {
  const [d, setD] = useState<Payload | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch("/latent/data/readable_subspace.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setD)
      .catch((e) => setErr(String(e)));
  }, []);

  const box = "rounded bg-bg/40 border border-border p-3";
  if (err) {
    return (
      <div className={box} data-subspace="error">
        <h3 className="text-xs text-gray-400 mb-1">4 条轴之外还有多少方向？</h3>
        <p className="text-[10px] text-red-400">读不到 readable_subspace.json：{err}</p>
      </div>
    );
  }
  if (!d) {
    return (
      <div className={box} data-subspace="loading">
        <h3 className="text-xs text-gray-400 mb-1">4 条轴之外还有多少方向？</h3>
        <p className="text-[10px] text-gray-600">载入中…</p>
      </div>
    );
  }

  const h = d.headline;
  const dn = d.char_pairwise_abs_cos["digit_mass|newline_mass"];

  return (
    <div className={box} data-subspace="ready"
         data-lower-bound={h.readable_directions_lower_bound}
         data-named-axes={h.named_axes}
         data-n-rows={d.surface_directions.length}>
      <h3 className="text-xs text-gray-300 mb-1">
        4 条命名轴之外，残差流里还剩多少方向？
      </h3>

      <p className="text-[10px] text-gray-400 leading-relaxed mb-1.5"
         data-headline-verdict="true">
        L{d.convention.layer} 上互相近正交（|cos| &lt; {h.separation_threshold}）的可读方向
        <b className="text-amber-300"> 至少 {h.readable_directions_lower_bound} 条 </b>
        ，而命名轴只有 <b>{h.named_axes} 条</b>。
        下界来自 {h.greedy_obs_only} 个观测量各自的读出方向再加 {h.named_axes} 条命名轴。
      </p>

      <p className="text-[9.5px] text-gray-600 leading-relaxed mb-2">
        {h.caution_absorbed}
      </p>

      {/* 缺口不是一条轴，是四条 —— 这是这一节最反直觉的结论。
          那个余弦从产物读，不写死：上一轮判据刚抓过「写死的 1.18×」。 */}
      <div className="rounded bg-bg/30 border border-border/60 p-1.5 mb-2"
           data-not-one-axis="true">
        <p className="text-[9.5px] text-gray-400 leading-snug">
          <b>缺口不是一条「表面形式」轴，是 4 条互相近乎正交的轴。</b>
          「{d.surface_directions[0]?.label}」与「{d.surface_directions[2]?.label}」两条方向的余弦只有{" "}
          <span className="font-mono text-amber-300"
                data-cos-digit-newline={dn}>{dn.toFixed(4)}</span>{" "}
          —— 几乎正交。把它们平均成一个「格式方向」只会得到一个对谁都只对齐
          0.3–0.6 的废物。
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        {d.surface_directions.map((r) => (
          <div key={r.key} data-subspace-row={r.key}
               data-diagonal={r.diagnostic.diagonal}
               data-floor={r.diagnostic.floor}
               data-decay={r.decay_x20}
               className="rounded border border-border/60 p-1.5">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[10.5px] text-gray-300">
                <span className="font-mono">{r.key}</span> · {r.label}
              </span>
              <span className="text-[9px] font-mono text-gray-500"
                    data-decay-label="true">
                Δ=20 塌 <span data-decay-value={r.decay_x20}>{r.decay_x20}×</span>
              </span>
            </div>
            <p className="text-[9px] text-gray-600 mt-0.5">{r.meaning}</p>

            {/* 三个必须并排的数：自己 / 地板 / 别人。
                data-value 必须装**数值**（交叉核对用），data-kind 才是列名 ——
                第一版写成 data-value="diagonal"，页面上看完全正常，
                但属性里是键名，判据拿它跟产物比必然红，且毫无信息。 */}
            <div className="mt-1 grid grid-cols-3 gap-1">
              <div className="rounded bg-bg/30 px-1 py-0.5" data-guard={`${r.key}-diag`}>
                <div className="text-[8px] text-gray-600">自己</div>
                <div className="text-[11px] font-mono text-emerald-300"
                     data-kind="diagonal" data-value={r.diagnostic.diagonal}>
                  {r.diagnostic.diagonal.toFixed(4)}
                </div>
              </div>
              <div className="rounded bg-bg/30 px-1 py-0.5" data-guard={`${r.key}-floor`}>
                <div className="text-[8px] text-gray-600">地板（打乱后）</div>
                <div className="text-[11px] font-mono text-gray-400"
                     data-kind="floor" data-value={r.diagnostic.floor}>
                  {r.diagnostic.floor.toFixed(4)}
                </div>
              </div>
              <div className="rounded bg-orange-500/10 px-1 py-0.5"
                   data-guard={`${r.key}-offdiag`}>
                <div className="text-[8px] text-gray-600">同表最高别人</div>
                <div className="text-[11px] font-mono text-orange-300"
                     data-kind="offdiag" data-value={r.diagnostic.offdiag_worst}>
                  {r.diagnostic.offdiag_worst.toFixed(4)}
                </div>
                <div className="text-[7.5px] text-gray-600 truncate">
                  {r.diagnostic.offdiag_worst_label}
                </div>
              </div>
            </div>

            <p className="text-[8.5px] text-gray-500 mt-0.5 leading-snug">
              对 4 条命名轴的 cos 最高{" "}
              <span className="font-mono text-gray-300" data-kind="max-axis"
                    data-value={r.diagnostic.max_cos_to_named}>
                {r.diagnostic.max_cos_to_named.toFixed(3)}
              </span>{" "}
              （全低 ⇒ 专属于自己，不是任何命名轴的读出）
            </p>

            <div className="grid grid-cols-3 gap-1 mt-1">
              {DELTAS.map((dd) => (
                <div key={dd} className="rounded bg-bg/20 px-1 py-0.5"
                     data-delta-cell={`${r.key}-${dd}`}>
                  <div className="text-[8px] text-gray-600">Δ={dd}</div>
                  <div className="text-[10px] font-mono text-gray-300"
                       data-delta-value={r.delta[dd]}>{r.delta[dd].toFixed(4)}</div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* 位置轴对照：没有它，「六条都塌」和「装置测不出持续」分不开 */}
      <div className="rounded border border-emerald-800/60 bg-emerald-900/10 p-1.5 mt-1.5"
           data-control-row="true"
           data-control-delta100={d.control.delta["100"]}>
        <p className="text-[9.5px] text-emerald-300/90 leading-snug">
          <b>装置阳性对照：{d.control.label}</b>
          {" "}Δ=0 <span className="font-mono">{d.control.delta["0"].toFixed(4)}</span> →{" "}
          Δ=100 <span className="font-mono" data-control-delta="100"
                        data-control-value={d.control.delta["100"]}>
            {d.control.delta["100"].toFixed(4)}
          </span>{" "}
          （<span className="font-mono">{d.control.decay_x20}×</span>，几乎不塌）
        </p>
        <p className="text-[8.5px] text-gray-500 mt-0.5 leading-snug">{d.control.note}</p>
      </div>

      <p className="text-[9.5px] text-gray-400 leading-relaxed mt-2 pt-2 border-t border-border/60"
         data-verdict="true">
        {d.verdict}
      </p>

      <p className="text-[9.5px] text-amber-400/80 leading-relaxed mt-1"
         data-not-claimed="true">
        <b>这不是因果性：</b>{d.not_claimed}
      </p>

      <p className="text-[9px] text-gray-600 leading-relaxed mt-1 pt-1 border-t border-border/60">
        {d.convention.search_space}
        <br />
        {d.convention.floor}
      </p>
    </div>
  );
}

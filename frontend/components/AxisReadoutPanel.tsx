"use client";

/**
 * AxisReadoutPanel — 四条独立轴各自指向哪个逐 token 行为观测量。
 *
 * 这块面板存在的理由：**光是"跑出一个漂亮的余弦"没有意义**。这里每一格都并排
 * 显示两样东西 —— 真实候选的余弦，和**位置对照**（`step_frac = t/(T−1)`）的余弦。
 * 对照正是 `reasoning_deep` 的定义分组，所以它是这条轴自己的尺子。
 *
 * 三个必须显示、不能省的东西：
 *   1. 对照行。缺了它，"已测"就只是"在 40 个格子里挑了个最好的"。
 *   2. 「同一个候选在三层都成立」。`creativity` 每格换一个候选（rep_ngram4 /
 *      backtrack_topk / latex_mass 轮换），那是噪声的签名，不是读出方向。
 *   3. 搜索的代价：9 候选 × 4 轴，p 已经付过钱了。
 *
 * 数据由 `.cache/rolesverify/probe_axes.py` 产出，经
 * `.cache/rolesverify/build_axis_readouts.py` 压成本文件。
 * **最优候选在分析侧选定**，这里只负责显示 —— 挑和显示分开，
 * 才不会在渲染时"顺手"换一个更漂亮的候选。
 */
import { useEffect, useState } from "react";

type Cell = {
  candidate: string;
  cos: number;
  control_cos: number | null;
  beats_control: boolean;
  p: number | null;
};

type Specificity = {
  cell: string | null;
  axis_of_report_row: string;
  cos_per_axis: Record<string, number> | null;
  row_axis_cos: number;
  row_axis_is_strongest: boolean;
  strongest_axis: string;
  specific: boolean | null;
  verdict: "tautological" | "shared" | "no_readout" | "position_only";
  pair_cos_confidence_caution?: number;
  note: string;
};

type AxisRow = {
  label: string;
  grouping: string;
  status: "measured" | "tautological" | "shared_readout" | "position_axis" | "not_measured";
  at_delta0: {
    modal_candidate: string | null;
    per_layer: Record<string, Cell>;
    n_layers_beating_control: number;
    n_layers: number;
    median_cos: number;
    median_control_cos: number;
    min_ratio_over_control: number | null;
  };
  at_delta20_L14: Cell | null;
  n_cells_beating_control: number;
  n_cells_total: number;
  criterion: string;
  specificity?: Specificity;
};

type Payload = {
  convention: {
    target_transform: string;
    n_candidates_searched: number;
    n_candidate_cells: number;
    n_random_directions: number;
    p_note: string;
    control: string;
  };
  axes: Record<string, AxisRow>;
  headline: {
    measured: string[];
    tautological?: string[];
    shared_readout?: string[];
    position_axis: string[];
    not_measured: string[];
    vocabulary_caveat: string;
    retraction_note?: string;
  };
};

const AXES = ["confidence", "caution", "creativity", "reasoning"] as const;
const LAYERS = ["12", "14", "20"] as const;
const AXIS_KEYS = ["confidence", "caution", "creativity", "reasoning_deep"] as const;
const AXIS_LABEL: Record<string, string> = {
  confidence: "confidence",
  caution: "caution",
  creativity: "creativity",
  reasoning_deep: "reasoning_deep",
};
const STATUS_TEXT: Record<
  AxisRow["status"],
  { label: string; cls: string }
> = {
  measured: { label: "已测到读出方向", cls: "text-emerald-400 border-emerald-700" },
  tautological: { label: "已测，但目标是定义式", cls: "text-sky-400 border-sky-800" },
  shared_readout: { label: "非循环，但不专属", cls: "text-orange-400 border-orange-800" },
  not_measured: { label: "测不出", cls: "text-gray-500 border-border" },
  position_axis: { label: "判定为轨迹位置轴", cls: "text-amber-500 border-amber-800" },
};
const CAND_TEXT: Record<string, string> = {
  top1_prob_renorm: "top-1 概率（熵的重述）",
  backtrack_topk: "top-64 候选里出现修订类 token 的比例",
  rep_ngram4: "以本步结尾的 4-gram 是否已出现过",
  rep_frac_topk: "top-64 候选里已在生成前缀出现的比例",
  rep_top1: "top-1 token 是否已出现过",
  digit_mass: "top-64 质量中落在数字 token 上的占比",
  op_mass: "top-64 质量中落在运算符上的占比",
  latex_mass: "top-64 质量中落在排版结构上的占比",
  newline_mass: "top-64 质量中落在换行上的占比",
};

export default function AxisReadoutPanel() {
  const [d, setD] = useState<Payload | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch("/latent/data/axis_readouts.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setD)
      .catch((e) => setErr(String(e)));
  }, []);

  const box = "rounded bg-bg/40 border border-border p-3";
  if (err) {
    return (
      <div className={box} data-axis="error">
        <h3 className="text-xs text-gray-400 mb-1">轴 → 观测量</h3>
        <p className="text-[10px] text-red-400">读不到 axis_readouts.json：{err}</p>
      </div>
    );
  }
  if (!d) {
    return (
      <div className={box} data-axis="loading">
        <h3 className="text-xs text-gray-400 mb-1">轴 → 观测量</h3>
        <p className="text-[10px] text-gray-600">载入中…</p>
      </div>
    );
  }

  return (
    <div className={box} data-axis="ready"
         data-measured={d.headline.measured.join(",")}
         data-tautological={(d.headline.tautological ?? []).join(",")}
         data-shared-readout={(d.headline.shared_readout ?? []).join(",")}
         data-position-axis={d.headline.position_axis.join(",")}
         data-not-measured={d.headline.not_measured.join(",")}>
      <h3 className="text-xs text-gray-300 mb-1">
        四条独立轴各自指向什么？<span className="text-gray-600">（对照已并排显示）</span>
      </h3>

      <p className="text-[10px] text-gray-500 leading-relaxed mb-2">
        留一轨迹的线性探针 <span className="font-mono">w = argmin ‖h_t w − y_(t+Δ)‖²</span>
        ，然后量 <span className="font-mono">cos(w, u)</span>。
        {d.convention.target_transform}。
        p 已为 <span className="font-mono">
        {d.convention.n_candidates_searched} 候选 × {d.convention.n_candidate_cells} 格
        </span> 的搜索付过钱（{d.convention.n_random_directions} 个随机方向）。
      </p>

      <div className="flex flex-col gap-1.5">
        {AXES.map((ax) => {
          const a = d.axes[ax];
          if (!a) return null;
          const st = STATUS_TEXT[a.status];
          const d0 = a.at_delta0;
          const mean = CAND_TEXT[d0.modal_candidate ?? ""] ?? d0.modal_candidate;
          return (
            <div key={ax} data-axis-row={ax} data-status={a.status}
                 data-beating={d0.n_layers_beating_control}
                 data-layers={d0.n_layers}
                 className="rounded border border-border/60 p-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10.5px] text-gray-300">
                  <span className="font-mono">{ax}</span> · {a.label}
                </span>
                <span className={`text-[9px] px-1.5 py-0.5 rounded border ${st.cls}`}
                      data-status-label={st.label}>
                  {st.label}
                </span>
              </div>

              <p className="text-[9.5px] text-gray-500 mt-0.5">
                定义分组：{a.grouping}
              </p>

              <p className="text-[9.5px] text-gray-400 mt-1">
                Δ=0 读出方向：<span className="font-mono text-gray-300"
                data-candidate={d0.modal_candidate}>{d0.modal_candidate}</span>
                <span className="text-gray-600">（{mean}）</span>
              </p>

              {/* 真实 vs 对照，并排。缺了对照这一栏，这块面板就只是自我确认。 */}
              <div className="mt-1 grid grid-cols-3 gap-1">
                {LAYERS.map((L) => {
                  const c = d0.per_layer[L];
                  if (!c) return <div key={L} />;
                  return (
                    <div key={L} data-cell={`${ax}-${L}`} data-beats={String(c.beats_control)}
                         className="rounded bg-bg/30 px-1 py-0.5">
                      <div className="text-[8.5px] text-gray-600">L{L}</div>
                      <div className="text-[10px] font-mono text-gray-300"
                           data-cos={c.cos}>
                        {c.cos.toFixed(3)}
                      </div>
                      <div className="text-[8.5px] font-mono text-gray-600"
                           data-control-cos={c.control_cos ?? ""}>
                        对照 {(c.control_cos ?? 0).toFixed(3)}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* 归属检验：同一个 w* 对四条轴各算一次。缺了它，"测到"分不清是谁的。 */}
              {a.specificity?.cos_per_axis ? (
                <div className="mt-1 rounded bg-bg/30 px-1 py-1"
                     data-specificity={ax}
                     data-specific={String(a.specificity.specific)}
                     data-strongest={a.specificity.strongest_axis}>
                  <div className="text-[8.5px] text-gray-600">
                    同一格 <span className="font-mono text-gray-500">{a.specificity.cell}</span>{" "}
                    的 w* 对四条轴：
                  </div>
                  <div className="grid grid-cols-4 gap-1 mt-0.5">
                    {AXIS_KEYS.map((k) => {
                      const v = a.specificity!.cos_per_axis![k];
                      const isRow = k === a.specificity!.axis_of_report_row;
                      const isMax = k === a.specificity!.strongest_axis;
                      return (
                        <div key={k}
                             data-spec-cell={`${ax}-${k}`}
                             data-spec-cos={v}
                             data-spec-role={isMax ? "strongest" : isRow ? "row_axis" : "other"}
                             className={`rounded px-1 py-0.5 ${
                               isMax ? "bg-orange-500/15" : "bg-transparent"
                             }`}>
                          <div className="text-[8px] text-gray-600 truncate">{AXIS_LABEL[k]}</div>
                          <div className={`text-[10px] font-mono ${
                            isMax ? "text-orange-300" : "text-gray-400"}`}>
                            {v.toFixed(3)}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  <p className="text-[8.5px] text-gray-500 mt-0.5 leading-snug">{a.specificity.note}</p>
                </div>
              ) : a.specificity ? (
                <p className="text-[8.5px] text-gray-600 mt-1 leading-snug"
                   data-specificity={ax} data-specific="unknown">
                  {a.specificity.note}
                </p>
              ) : null}

              <p className="text-[9px] mt-1 leading-snug"
                 data-verdict={a.status}>
                {a.status === "tautological" ? (
                  <>
                    三层同一个候选，{d0.n_layers_beating_control}/{d0.n_layers} 层超过位置对照，
                    最小倍数 <span className="font-mono">{d0.min_ratio_over_control}×</span>，
                    且 20 步后（L14）塌到{" "}
                    <span className="font-mono">
                      {a.at_delta20_L14 ? a.at_delta20_L14.cos.toFixed(3) : "—"}
                    </span>{" "}
                    ⇒ <b>token 局部</b>。归属检验它<b>是专属的</b>
                    （{(a.specificity?.cos_per_axis?.confidence ?? 0).toFixed(3)}{" "}
                    vs 次高{" "}
                    <span className="font-mono">
                      {(a.specificity?.cos_per_axis?.caution ?? 0).toFixed(3)}
                    </span>
                    ），但<b>目标是构造恒等式</b> ⇒ 只能算装置阳性对照。
                  </>
                ) : a.status === "shared_readout" ? (
                  <>
                    三层同一个候选，{d0.n_layers_beating_control}/{d0.n_layers} 层超过位置对照，
                    最小倍数 <span className="font-mono">{d0.min_ratio_over_control}×</span>。
                    归属检验<b>没过</b>：同格上 <span className="font-mono">confidence</span>{" "}
                    对齐 <span className="font-mono">
                      {(a.specificity?.cos_per_axis?.confidence ?? 0).toFixed(3)}
                    </span>{" "}
                    高于 <span className="font-mono">caution</span> 的{" "}
                    <span className="font-mono">{(a.specificity?.row_axis_cos ?? 0).toFixed(3)}</span>
                    ，而两轴本身 <span className="font-mono">
                      cos = {(a.specificity?.pair_cos_confidence_caution ?? 0).toFixed(3)}
                    </span>{" "}
                    ⇒ 这是<b>两条轴共用</b>的可读方向，<b>分不开归属</b>。
                  </>
                ) : a.status === "measured" ? (
                  <>
                    三层同一个候选，{d0.n_layers_beating_control}/{d0.n_layers} 层超过位置对照，
                    最小倍数 <span className="font-mono">{d0.min_ratio_over_control}×</span>。
                    20 步后（L14）降到{" "}
                    <span className="font-mono">
                      {a.at_delta20_L14 ? a.at_delta20_L14.cos.toFixed(3) : "—"}
                    </span>{" "}
                    ⇒ <b>token 局部</b>。
                    {!a.label.includes("置信") && (
                      <>
                        {" "}余弦不是 1.0（{(d0.median_cos ** 2 * 100).toFixed(1)}% 的方向成分），
                        说的是「实现里<b>有</b>这一项」，不是「<b>就是</b>这一项」。
                      </>
                    )}
                  </>
                ) : a.status === "position_axis" ? (
                  <>
                    Δ=0 上 {d0.n_layers_beating_control}/{d0.n_layers} 层超过对照。
                    中位 <span className="font-mono">{d0.median_cos.toFixed(3)}</span>{" "}
                    vs 对照 <span className="font-mono">
                    {d0.median_control_cos.toFixed(3)}</span>{" "}
                    （{d0.min_ratio_over_control}×，即最差的一层还不到对照的一半），
                    且 {a.n_cells_beating_control}/{a.n_cells_total} 格里没有一格超过。
                    ⇒ <b>它就是一条轨迹位置轴</b> —— 不是测不出，
                    是除了位置之外没有别的可测行为。
                  </>
                ) : (
                  <>
                    Δ=0 只有 {d0.n_layers_beating_control}/{d0.n_layers} 层超过对照
                    （最小倍数 <span className="font-mono">{d0.min_ratio_over_control}×</span>，
                    即最差的一层还低于对照）。每格换一个候选也是噪声的签名。
                    全部 {a.n_cells_total} 格里只有 {a.n_cells_beating_control} 格偶然超过。
                    ⇒ <b>测不出</b>。
                  </>
                )}
              </p>
            </div>
          );
        })}
      </div>

      {d.headline.retraction_note && (
        <p className="text-[10px] text-orange-300/80 leading-relaxed mt-2 pt-2 border-t border-border/60"
           data-retraction="true">
          <b>⚠ 已撤回的结论：</b>{d.headline.retraction_note}
        </p>
      )}
      <p className="text-[10px] text-gray-600 leading-relaxed mt-2 pt-2 border-t border-border/60">
        <b className="text-gray-500">对照是什么，为什么必须显示它：</b>{" "}
        {d.convention.control}
        <br />
        <span className="text-gray-500">判定口径：</span>
        {d.axes.confidence?.criterion}
      </p>
      <p className="text-[10px] text-gray-600 leading-relaxed mt-1">
        <b className="text-gray-500">词表提醒：</b>
        {d.headline.vocabulary_caveat} 上面的四行是四条独立轴，不是四个标签。
      </p>
    </div>
  );
}

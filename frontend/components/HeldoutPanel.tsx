"use client";

/**
 * HeldoutPanel — 这套判据在**没参与过调参**的观测量上还灵吗？
 *
 * 前两块面板回答的都是「这批观测量里有什么」：
 *   AxisReadoutPanel —— 4 条命名轴各自指向什么；
 *   SubspacePanel    —— 4 条轴之外还剩多少方向。
 * 两者用的观测量**全是我自己构造的**，而且调过参（λ、K、层、命名轴都在它们身上选过）。
 * ⇒ 它们证明不了「这是一套方法」，只证明了「在这批量上找得到东西」。
 *
 * 这一块是**第二个问题**，所以数据必须换一批：
 *   三个量与原 `digit_mass` 共用底层分类，但函数形式完全不同
 *     （二值 / 个数占比 / 只看前 8 vs 重归一化质量）；
 *   另三个从**已发出的 token 文本**造，从未进过任何流程。
 *
 * 两问必须分开显示，合成一句就成了「找到新方向」：
 *   ① 迁移：已有的 w*(digit_mass) 换到别的函数形式还成立吗？
 *      —— 这是**非循环**问题。地板必须逐行独立估计：
 *      分母一旦共用一个常量就会算错（§4.9.1 原本写成 128/113/110×，正确是
 *      128.6/112.3/244.4×）。所以「倍数」由 build 脚本算，页面只显示。
 *   ② 归属：换出来的量是**新方向**吗？
 *      —— 余量（自己对角 ÷ 同表最高别人）不到 1 就是同一条方向的重新构造。
 *      这正是 caution 当年塌掉的方式，所以它必须并排显示，不能只显示自己那一列。
 *
 * 第三块是一个**自我纠正**：我原本把 emitted_has_digit 当「新家族」，
 * 仪器判它是重复 —— 查下来它与 digit_top1 就是同一个观测量
 * （同一步 0.9839，错开一步 0.0925）。这个错误要显示出来，不是藏起来。
 *
 * 数据由 `.cache/xcheck/` 下四个脚本产出，经 `build_heldout_readout.py` 压成本文件。
 * **判定在分析侧完成**，这里只负责显示。
 */
import { useEffect, useState } from "react";

type Transfer = {
  target: string;
  form: string;
  rho: number;
  floor: number;
  ratio: number;
};

type Row = {
  key: string;
  label: string;
  form: string;
  origin: string;
  verdict: "same_direction" | "new_clean" | "new_weak";
  rho_self: number;
  floor: number;
  worst_other: string;
  worst_other_value: number;
  margin: number;
  max_cos_named_axes: number;
  rho_delta20: number | null;
  decay_x20: number | null;
};

type SelfDup = {
  verdict: string;
  n_traj: number;
  n_step: number;
  pooled: { same_step: number; lag1: number; drop: number };
  per_traj_mean: { same_step: number; lag1: number; drop: number; n_used: number };
  note: string;
};

type Payload = {
  schema: string;
  question: string;
  convention: {
    source_direction: string;
    floor: string;
    margin_rule: string;
    new_clean_threshold: number;
    note: string;
  };
  headline: {
    heldout_total: number;
    transfer_targets: number;
    ratio_min: number;
    ratio_max: number;
    same_direction: number;
    new_clean: number;
    new_weak: number;
    verdict_line: string;
  };
  transfer: Transfer[];
  rows: Row[];
  selfdup: SelfDup;
  verdict: string;
  not_claimed: string;
};

const VERDICT_TEXT: Record<Row["verdict"], string> = {
  same_direction: "同一个方向",
  new_clean: "新方向（干净）",
  new_weak: "新方向（弱）",
};

const VERDICT_CLS: Record<Row["verdict"], string> = {
  same_direction: "text-gray-400",
  new_clean: "text-emerald-300",
  new_weak: "text-amber-300",
};

export default function HeldoutPanel() {
  const [d, setD] = useState<Payload | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch("/latent/data/heldout_readability.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setD)
      .catch((e) => setErr(String(e)));
  }, []);

  const box = "rounded bg-bg/40 border border-border p-3";
  if (err) {
    return (
      <div className={box} data-heldout="error">
        <h3 className="text-xs text-gray-400 mb-1">没参与过调参的观测量上还灵吗？</h3>
        <p className="text-[10px] text-red-400">读不到 heldout_readability.json：{err}</p>
      </div>
    );
  }
  if (!d) {
    return (
      <div className={box} data-heldout="loading">
        <h3 className="text-xs text-gray-400 mb-1">没参与过调参的观测量上还灵吗？</h3>
        <p className="text-[10px] text-gray-600">载入中…</p>
      </div>
    );
  }

  const h = d.headline;
  const sd = d.selfdup;

  return (
    <div className={box} data-heldout="ready"
         data-heldout-total={h.heldout_total}
         data-transfer-targets={h.transfer_targets}
         data-same-direction={h.same_direction}
         data-new-clean={h.new_clean}
         data-new-weak={h.new_weak}
         data-ratio-min={h.ratio_min}
         data-ratio-max={h.ratio_max}
         data-n-rows={d.rows.length}>
      <h3 className="text-xs text-gray-300 mb-1">没参与过调参的观测量上还灵吗？</h3>

      <p className="text-[10px] text-gray-400 leading-relaxed mb-1.5"
         data-heldout-headline="true">
        {h.verdict_line}
      </p>

      {/* ① 迁移：已有的方向换函数形式还成立吗 */}
      <div className="rounded bg-bg/30 border border-border/60 p-1.5 mb-1.5"
           data-block="transfer">
        <p className="text-[9.5px] text-gray-400 leading-snug mb-1">
          <b>① 迁移：</b>w*(digit_mass) 换到结构完全不同的函数形式，还预测得动吗？
          <span className="text-gray-600">（二值 / 个数占比 / 只看前 8，
          对照原量是重归一化质量）</span>
        </p>
        <div className="flex flex-col gap-0.5">
          {d.transfer.map((t) => (
            <div key={t.target} data-transfer-row={t.target}
                 className="rounded bg-bg/20 px-1 py-0.5">
              <div className="flex items-baseline justify-between gap-1 text-[9px]">
                <span className="font-mono text-gray-300">{t.target}</span>
                <span className="font-mono text-emerald-300"
                      data-kind="rho" data-value={t.rho}>{t.rho.toFixed(4)}</span>
                <span className="text-gray-600">/</span>
                <span className="font-mono text-gray-500"
                      data-kind="floor" data-value={t.floor}>{t.floor.toFixed(4)}</span>
                <span className="font-mono text-amber-300"
                      data-kind="ratio" data-value={t.ratio}>
                  {t.ratio.toFixed(1)}×
                </span>
              </div>
              {/* 形式说明另起一行：第一版和数字挤在同一行，328px 的侧栏里
                  `digit_top8_presence` 那一行的 Δ=20 被裁掉了。
                  判据当时全绿 —— 数值在 DOM 里，但读者看不见。 */}
              <div className="text-[8.5px] text-gray-600 leading-snug">{t.form}</div>
            </div>
          ))}
        </div>
        <p className="text-[8.5px] text-gray-600 leading-snug mt-1">
          倍数 = |ρ| ÷ |该行自己的打乱地板|，<b>分母逐行独立估计</b>。
          {d.convention.note}
        </p>
      </div>

      {/* ② 归属：它们是新方向吗。必须并排「自己 / 最高别人」 */}
      <div className="rounded bg-bg/30 border border-border/60 p-1.5 mb-1.5"
           data-block="specificity">
        <p className="text-[9.5px] text-gray-400 leading-snug mb-1">
          <b>② 归属：</b>它们是新方向，还是同一条方向的重新构造？
          <span className="text-gray-600">（余量 = 自己对角 ÷ 同表最高别人，
          &lt; 1 就是同一个）</span>
        </p>
        <div className="flex flex-col gap-0.5">
          {d.rows.map((r) => (
            <div key={r.key} data-heldout-row={r.key}
                 data-heldout-verdict={r.verdict}
                 className="rounded bg-bg/20 px-1 py-0.5">
              <div className="flex items-baseline justify-between gap-1 text-[9px]">
                <span className="font-mono text-gray-300">{r.key}</span>
                <span className={VERDICT_CLS[r.verdict]} data-kind="verdict-text">
                  {VERDICT_TEXT[r.verdict]}
                </span>
                <span className="font-mono text-gray-400"
                      data-kind="margin" data-value={r.margin}>
                  余量 {r.margin.toFixed(2)}×
                </span>
              </div>
              <div className="flex items-baseline justify-between gap-1 text-[8.5px]">
                <span className="font-mono text-orange-300/80"
                      data-kind="worst-other" data-value={r.worst_other_value}>
                  最强对手 {r.worst_other}
                </span>
                {r.rho_delta20 === null ? (
                  /* 未测就写「未测」，绝不能渲染成 0.0000 —— 那会把
                     「没测」与「测出零」混成一个数。判据专门查这一格。 */
                  <span className="text-gray-600" data-kind="delta20-missing">
                    Δ=20 未测
                  </span>
                ) : (
                  <span className="font-mono text-gray-500"
                        data-kind="delta20" data-value={r.rho_delta20}>
                    Δ=20 {r.rho_delta20.toFixed(4)}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ③ 自我纠正：我自己把同一个量当成了新家族 */}
      <div className="rounded border border-amber-800/60 bg-amber-900/10 p-1.5 mb-1.5"
           data-block="selfdup"
           data-selfdup-verdict={sd.verdict}
           data-selfdup-same={sd.pooled.same_step}
           data-selfdup-lag1={sd.pooled.lag1}
           data-selfdup-per-traj={sd.per_traj_mean.same_step}
           data-selfdup-n-traj={sd.n_traj}>
        <p className="text-[9.5px] text-amber-300/90 leading-snug">
          <b>③ 仪器抓到我的一个设计失误：</b>
          「本步发出的 token 含数字」与「本步记录的 top-1 是数字」
          同一步相关 <span className="font-mono" data-selfdup-cell="same">
            {sd.pooled.same_step.toFixed(4)}
          </span>
          ，而与错开一步只有{" "}
          <span className="font-mono" data-selfdup-cell="lag1">
            {sd.pooled.lag1.toFixed(4)}
          </span>{" "}
          —— <b>就是同一个观测量</b>，我却当成「新家族」提交了。
        </p>
        <p className="text-[8.5px] text-gray-500 mt-0.5 leading-snug">
          对照口径：逐轨迹算再平均 同一步{" "}
          <span className="font-mono" data-selfdup-cell="per-traj">
            {sd.per_traj_mean.same_step.toFixed(4)}
          </span>
          （{sd.per_traj_mean.n_used}/{sd.n_traj} 条轨迹有效）
          —— 与整段拼接差 {Math.abs(sd.pooled.same_step - sd.per_traj_mean.same_step).toFixed(4)}
          ，所以它不是跨轨迹拼接造出来的伪影。
        </p>
      </div>

      <p className="text-[9.5px] text-gray-400 leading-relaxed pt-2 border-t border-border/60"
         data-heldout-verdict-text="true">
        {d.verdict}
      </p>

      <p className="text-[9.5px] text-amber-400/80 leading-relaxed mt-1"
         data-heldout-not-claimed="true">
        <b>这仍然不是因果性：</b>{d.not_claimed}
      </p>

      <p className="text-[9px] text-gray-600 leading-relaxed mt-1 pt-1 border-t border-border/60">
        方向来源：{d.convention.source_direction}
        <br />
        余量定义：{d.convention.margin_rule}；新方向（干净）门槛 余量 ≥{" "}
        {d.convention.new_clean_threshold}×
      </p>
    </div>
  );
}

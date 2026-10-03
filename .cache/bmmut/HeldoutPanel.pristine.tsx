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
  recipe: {
    target: string;
    how: string;
    selfcheck_cos: number;
    loo_rho: number;
    loo_floor: number;
    loo_folds: number;
    loo_range: [number, number];
    control_confidence_same_code: number;
    cos_recipe_vs_ridge: number;
    cos_recipe_vs_caution_axis: number;
    cos_recipe_vs_caution_readout: number;
    recipe_loo_on_entropy: number;
    recipe_loo_on_selfcheck: number;
    specificity_margin: number;
    relative_amplitude: number;
    variants: {
      name: string;
      short: string;
      rho_own: number | null;
      rho_own_sem: number | null;
      worst_name: string | null;
      worst_rho: number | null;
      runner_up_name: string | null;
      runner_up_rho: number | null;
      gap_over_sem: number | null;
      /** 两个竞争者差距不到 2 sem ⇒ max 选中谁不可判，margin 只能读成下界 */
      tie: boolean;
      margin: number | null;
      n_positive: number | null;
    }[];
    control_self_check: {
      name: string;
      short: string;
      worst_name: string | null;
      worst_rho: number | null;
      runner_up_name: string | null;
      runner_up_rho: number | null;
      gap_over_sem: number | null;
      tie: boolean;
      margin: number | null;
    }[];
    closure_v1_selfcheck_vs_caution_axis: number;
    best_margin: number;
    clean_threshold: number;
    margin_gain_attribution: {
      margin_from: number; margin_to: number;
      own_from: number; own_to: number; own_change_pct: number;
      worst_from: number; worst_to: number; worst_change_pct: number;
      worst_name_from: string; worst_name_to: string;
      share_from_competitor: number | null;
    };
    control_binding_swapped: boolean;
    verdict: string;
  };
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

// 变体名在页面上要写成人话，不能直接印 V2_banded
const VLABEL: Record<string, string> = {
  V1_naive: "V1 朴素差均值",
  V2_banded: "V2 熵带内差",
  V3_residualized: "V3 熵残差化",
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
  const rc = d.recipe;

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

      {/* ④ 「可读」≠「有配方」≠「可注入」。这一块存在是因为：
          上面把 emitted_is_upper 标成「新方向（干净）」，读者很容易理解成
          「那是一条可以拿去注入的轴」—— 而第三关没过。 */}
      <div className="rounded border border-red-900/60 bg-red-900/10 p-1.5 mb-1.5"
           data-block="recipe"
           data-recipe-loo={rc.loo_rho}
           data-recipe-floor={rc.loo_floor}
           data-recipe-margin={rc.specificity_margin}
           data-recipe-selfcheck-cos={rc.selfcheck_cos}>
        <p className="text-[9.5px] text-red-300/90 leading-snug">
          <b>④ 但「新方向」不等于「可以拿去注入的轴」。</b>
          把它做成与现有 4 条命名轴<b>同一套配方</b>
          （首字母大写组 vs 非大写组取差均值），配方自证
          cos = {rc.selfcheck_cos.toFixed(9)}。
        </p>
        <p className="text-[8.5px] text-gray-400 leading-snug mt-1">
          留一轨迹 rho <span className="font-mono text-gray-200"
            data-recipe-cell="loo">{rc.loo_rho.toFixed(4)}</span>
          （{rc.loo_folds} 折，打乱地板 {rc.loo_floor.toFixed(4)}，
          {Math.round(rc.loo_rho / rc.loo_floor)}×；同一份代码量 confidence 是{" "}
          <span className="font-mono" data-recipe-cell="control">
            {rc.control_confidence_same_code.toFixed(4)}
          </span>）
          ⇒ <b className="text-emerald-300">配方写得出来，而且跨轨迹站得住</b>。
        </p>
        <p className="text-[8.5px] text-gray-400 leading-snug mt-0.5">
          瓶颈在<b>专一性</b>：同一份配方预测 <code>entropy</code> 有{" "}
          <span className="font-mono text-amber-300" data-recipe-cell="entropy">
            {rc.recipe_loo_on_entropy.toFixed(4)}
          </span>
          ，与预测它自己目标（{rc.loo_rho.toFixed(4)}）只差{" "}
          <span className="font-mono text-red-300" data-recipe-cell="margin">
            {rc.specificity_margin.toFixed(2)}×
          </span>
          —— 而上面那条读出方向的余量是 2.05×。
        </p>
        <p className="text-[8.5px] text-gray-500 leading-snug mt-0.5">
          顺带查清一个容易误读的数：配方与 caution <b>注入轴</b>的 cos 是{" "}
          <span className="font-mono" data-recipe-cell="caution-axis">
            {rc.cos_recipe_vs_caution_axis.toFixed(4)}
          </span>
          （高），但与 caution 的<b>读出方向</b>只有{" "}
          <span className="font-mono" data-recipe-cell="caution-readout">
            {rc.cos_recipe_vs_caution_readout.toFixed(4)}
          </span>
          （低）⇒ <b>轴 ≠ 读出</b>，不能读成「is_upper 就是 caution」。
          幅度 ‖差均值‖/mean‖h‖ = {rc.relative_amplitude.toFixed(4)}，
          与现有 4 条轴同量级。
        </p>
        <p className="text-[9px] text-red-300/90 leading-snug mt-1 pt-1 border-t border-red-900/40"
           data-recipe-verdict="true">
          {rc.verdict}
        </p>
        {/* 换配方结构能不能救？—— 三个变体 + 对照组。
            不印这一块，读者会以为「1.15×」就是这条方向唯一可得的配方。
            ⚠ 每行必须带上**谁在约束**（worst）与这个归属分不分得开（tie）：
              余量 = 自身 / max(竞争者)，两个竞争者并列时 max 选中谁是任意的，
              只印余量会把「并列」印成「结论」。 */}
        <div className="mt-1 pt-1 border-t border-red-900/40"
             data-recipe-variants="true"
             data-best-margin={rc.best_margin}
             data-clean-threshold={rc.clean_threshold}
             data-binding-swapped={String(rc.control_binding_swapped)}>
          <p className="text-[8.5px] text-gray-500 leading-snug mb-0.5">
            换配方结构（去熵混杂）能救吗？余量 = 自身 ÷ 最紧的那个竞争者，
            所以<b>「谁在约束」和余量一样重要</b>：
          </p>
          <ul className="text-[8.5px] text-gray-500 leading-snug mb-0.5">
            {rc.variants.map((v) => (
              <li key={v.name} data-variant-row={v.name}
                  data-variant-margin={v.margin}
                  data-variant-tie={String(v.tie)}
                  data-variant-worst={v.worst_name}>
                <b className="text-gray-300">{VLABEL[v.name] ?? v.short}</b>{" "}
                <span className="font-mono">{v.margin?.toFixed(2) ?? "n/a"}×</span>
                <span className="text-gray-600"> ← </span>
                压住它的是 <code>{v.worst_name}</code>
                <span className="font-mono"> {v.worst_rho?.toFixed(3)}</span>
                {v.tie
                  ? <b className="text-amber-400">（与 {v.runner_up_name}{" "}
                      {v.runner_up_rho?.toFixed(3)} 并列，差 {v.gap_over_sem?.toFixed(2)} sem
                      ⇒ 这个 max 选中谁是任意的）</b>
                  : <span className="text-gray-600">（领先 {v.gap_over_sem?.toFixed(1)} sem，归属可信）</span>}
              </li>
            ))}
          </ul>
          <p className="text-[8.5px] text-gray-500 leading-snug mb-0.5">
            最好 <b className="font-mono">{rc.best_margin.toFixed(2)}×</b>
            （{VLABEL.V2_banded}），仍不到干净门槛 {rc.clean_threshold.toFixed(1)}×。
            但涨幅不是配方变干净了：自身只涨{" "}
            <span className="font-mono">{rc.margin_gain_attribution.own_change_pct.toFixed(1)}%</span>，
            竞争者掉了{" "}
            <span className="font-mono">{Math.abs(rc.margin_gain_attribution.worst_change_pct).toFixed(1)}%</span>
            ⇒ 余量上涨的{" "}
            <b>{rc.margin_gain_attribution.share_from_competitor?.toFixed(0) ?? "n/a"}%</b>{" "}
            来自竞争者被压下去，不是来自配方本身。
          </p>
          <p className="text-[8.5px] text-gray-500 leading-snug">
            对照组 <code>self_check</code>（与磁盘 <code>caution.npy</code> 同族，
            cos {rc.closure_v1_selfcheck_vs_caution_axis.toFixed(4)}，非逐位相同）
            三个余量同样全 &lt; 1，但<b>压住它的那个也换了人</b>：
            朴素时是 <code>entropy</code>（只领先 1.7 sem，<b className="text-amber-400">并不显著</b>），
            去混杂后确定地变成 <code>emitted_is_upper</code>（5.1 / 3.3 sem）。
            ⇒ <b className="text-red-300">不能说「caution 的配方方向本来就是熵的」</b>：
            去掉熵的混杂之后，它是被「已发出 token 首字母大写」压住的。
          </p>
        </div>
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

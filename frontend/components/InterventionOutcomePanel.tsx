"use client";

/**
 * What the intervention actually did — the offline, token-level answer.
 *
 * The 3-D pane's steering control injects a vector into the residual
 * stream and the trajectory bends. What it does *not* do is change the
 * tokens: the runner reads them out of the recording, and re-decoding
 * would need the remaining 14–27 transformer blocks run on this machine,
 * which it deliberately does not do (see replay_runner.py's header, and
 * .cache/steerprobe/probe_steer.py for the measurement behind it).
 *
 * So the honest answer to "what did the vector do?" is not on this page
 * at all — it is in the 32k batch, where a real decoder was re-run
 * token by token with and without the vector. This panel reads that:
 *
 *   cot_texts.json      92 runs = 46 problems × {up, down} × {0.0, 0.2}
 *                       each with first_diverged_step and token_agreement
 *   answer_readout.json 10 problems, final answer under both arms
 *   arm_asymmetry.json  ±v paired test: is the axis response asymmetric?
 *   answer_power.json   what "net change = 0" does and does not license
 *
 * Three things this panel refuses to do:
 *
 *  1. Present these as the result of the slider on the left. They are not.
 *     A reader who nudges the strength control and sees this panel change
 *     would be reading a causal claim that is not there. Hence the
 *     offline banner, always visible, not a footnote.
 *  2. Hide the denominators. 46 steered runs, 1 of 10 answers changed
 *     from right to wrong and 1 from wrong to right — net zero. The
 *     numbers are not flattering and that is the point; a panel that
 *     only showed the cases where steering "worked" would be a
 *     selection effect, not a measurement.
 *  3. Smooth over the control. Every steered run is paired with a
 *     zero-strength run of the same problem and direction. The controls
 *     have first_diverged_step = null and token_agreement = 1.0, which is
 *     what makes the comparison mean anything: the two arms differ only
 *     by the injected vector.
 *
 * A fourth refusal, about the neighboring evidence: vector_roles.json
 * carries a `necessity` block whose `in_sample_circular` section is
 * circular by construction -- the vector is *defined* as a difference of
 * group means over these very tokens, then correlated back against the
 * same labels. Its `passes_gate: true` is an identity, not a finding. The
 * only non-circular evidence in that file is `heldout_non_circular`, which
 * was not independently reproduced. So this panel deliberately does not
 * render any of it, and says why rather than quietly omitting it.
 *
 * A fifth refusal, about the panel's own headline number. "Net change in
 * correct answers: 0" reads like a null result. It is not one. The 10
 * problems behind it were selected *because the two arms disagreed* — the
 * denominator is the set that moved — and only 2 of them flipped
 * correctness at all, one up and one down. The sign test needs 6
 * same-direction flips out of 10 to clear p < 0.05, and the exact 95%
 * interval on the flip rate runs from 0.003 to 0.445. "Zero" here is the
 * typical result *under* the null, so the panel prints that arithmetic
 * instead of letting the number stand alone. Same shape as §8's L4: an
 * unmeasured cell printed as a measured zero.
 */

import { useEffect, useMemo, useState } from "react";

type CotRun = {
  id: string;
  direction: string;
  strength: number;
  layer: number;
  n_steps: number;
  first_diverged_step: number | null;
  token_agreement: number;
  mean_logit_kl: number;
  n_bad_steps: number;
  primary_head: string;
  shadow_head: string;
};

type CotTexts = {
  n_runs: number;
  planned_runs: number;
  batch_complete: boolean;
  control_is_identity: boolean;
  runs: CotRun[];
};

type AnswerItem = {
  label: string;
  direction: string;
  verdict: string;
  zero: { answer: string; steps: number; chars: number };
  steered: { answer: string; steps: number; chars: number };
  shared_prefix_chars: number;
  split_char: number;
};

type AnswerReadout = {
  direction: string;
  strength: number;
  planned_runs: number;
  n_runs_analysed: number;
  selection: { n_eligible: number; n_shipped: number; by_verdict: Record<string, number> };
  caveats: string[];
  items: AnswerItem[];
};

type ArmMetric = {
  metric: string;
  desc: string;
  up_mean: number;
  down_mean: number;
  paired_diff: number;
  paired_sem: number;
  t: number;
  ci95_lo: number;
  ci95_hi: number;
  /** CI 跨 0 ⇒ 这个量在两臂之间分不开，不许当成一个结论印 */
  distinguishable: boolean;
};

type AnswerPower = {
  what: string;
  n_problems_in_batch: number;
  n_shipped: number;
  selection_rule: string;
  direction: string;
  strength: number;
  baseline_correct: number;
  steered_correct: number;
  net_change: number;
  verdicts: Record<string, number>;
  flips: number;
  flips_up: number;
  flips_down: number;
  up_rate_ci95: [number, number];
  two_sided_sign_p_if_all_same_direction: number;
  flips_needed_for_p05: number;
  flip_rate_ceiling_over_batch: number;
  steps_ratio_min: number;
  steps_ratio_max: number;
  labels_not_both_in_domain: string[];
  verdict: string;
  not_claimed: string;
};

type ArmAsymmetry = {
  what: string;
  n_pairs: number;
  n_zero_strength_identity_pairs: number;
  up_down_are_exact_negatives: boolean;
  max_abs_up_plus_down: number;
  cos_up_down: number;
  layer: number;
  strength: number;
  metrics: ArmMetric[];
  verdict: string;
  not_claimed: string;
};

const MLABEL: Record<string, string> = {
  mean_logit_kl: "分布被推离的远度 KL",
  token_agreement: "两臂选同一个 token",
  first_diverged_step: "第一次分岔的步数",
};

const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

export default function InterventionOutcomePanel() {
  const [cot, setCot] = useState<CotTexts | null>(null);
  const [ans, setAns] = useState<AnswerReadout | null>(null);
  const [arm, setArm] = useState<ArmAsymmetry | null>(null);
  const [pw, setPw] = useState<AnswerPower | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // Mounted with a cancellation guard, same shape as InterpretationPanel's
  // layer-profile fetch: the panel can unmount mid-flight and then there is
  // nothing to set state on.
  useEffect(() => {
    let alive = true;
    Promise.all([
      fetch("/latent/data/cot_texts.json").then((r) =>
        r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))),
      fetch("/latent/data/answer_readout.json").then((r) =>
        r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))),
      // 配对检验。**刻意不并进 cot_texts.json**：那个文件由
      // backend/examples/build_cot_text_readout.py 生成，合并进去等于
      // 让两支脚本互相覆写，谁后跑谁赢，顺序错了没人报错。
      fetch("/latent/data/arm_asymmetry.json").then((r) =>
        r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))),
      // 「净变化 0」的功效分析。同上，单独一份产物：写它的是
      // .cache/xcheck/answer_power.py，读它的是这块面板，合并会让
      // 两边的生成顺序变成隐式依赖。
      fetch("/latent/data/answer_power.json").then((r) =>
        r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))),
    ])
      .then(([c, a, m, p]: [CotTexts, AnswerReadout, ArmAsymmetry, AnswerPower]) => {
        if (alive) { setCot(c); setAns(a); setArm(m); setPw(p); }
      })
      .catch((e) => { if (alive) setErr(String(e.message || e)); });
    return () => { alive = false; };
  }, []);

  const stats = useMemo(() => {
    if (!cot?.runs) return null;
    const steered = cot.runs.filter((r) => r.strength > 0);
    const control = cot.runs.filter((r) => r.strength === 0);
    if (!steered.length) return null;
    const fd = steered
      .map((r) => r.first_diverged_step)
      .filter((x): x is number => x != null)
      .sort((a, b) => a - b);
    const med = (xs: number[]) =>
      xs.length ? xs[Math.floor(xs.length / 2)] : null;
    const agree = steered.map((r) => r.token_agreement).sort((a, b) => a - b);
    const kl = steered.map((r) => r.mean_logit_kl).sort((a, b) => a - b);
    const cleanControl = control.filter(
      (r) => r.first_diverged_step == null && r.token_agreement === 1);
    return {
      nSteered: steered.length,
      nControl: control.length,
      nCleanControl: cleanControl.length,
      fdMin: fd[0] ?? null,
      fdMed: med(fd),
      fdMax: fd[fd.length - 1] ?? null,
      agreeMin: agree[0] ?? null,
      agreeMed: med(agree),
      klMed: med(kl),
      controlIsIdentity: cot.control_is_identity,
      batchComplete: cot.batch_complete,
      planned: cot.planned_runs,
    };
  }, [cot]);

  if (err) {
    return (
      <div className="rounded bg-bg/40 border border-border p-3" data-outcome="error">
        <Head />
        <p className="text-[10px] text-red-400 leading-relaxed mt-1">
          offline readout unavailable: {err}
        </p>
      </div>
    );
  }

  if (!cot || !ans || !stats) {
    return (
      <div className="rounded bg-bg/40 border border-border p-3" data-outcome="loading">
        <Head />
        <p className="text-[10px] text-gray-500 leading-relaxed mt-1">
          Loading the offline intervention readout…
        </p>
      </div>
    );
  }

  const verdict = ans.selection?.by_verdict ?? {};
  const changed = (verdict["right->wrong"] ?? 0) + (verdict["wrong->right"] ?? 0);

  return (
    <div className="rounded bg-bg/40 border border-border p-3" data-outcome="ready">
      <Head />

      {/* Always visible, not a footnote. See the file header: the slider on
          the left does not produce these numbers. */}
      <div
        className="mt-1.5 mb-2 px-2 py-1.5 rounded text-[10px] leading-relaxed"
        style={{ background: "#131a28", borderLeft: "2px solid #d9a441", color: "#d8c08a" }}
        data-offline-banner
      >
        <b>Offline 32k batch, not this page&apos;s slider.</b> Re-decoded
        token by token with a real decoder. The strength control on the
        left bends the 3-D trajectory but does <b>not</b> change the tokens
        you see replaying — that would need the remaining transformer
        blocks run here, and this page does not run the model.
      </div>

      {/* --- when the vector takes effect --- */}
      <div className="text-[10px] text-gray-500 uppercase tracking-wider mt-1 mb-1">
        When the vector takes hold
      </div>
      <div className="grid grid-cols-3 gap-1.5 mb-1">
        <Stat label="first changed step" v={stats.fdMed != null ? `~${stats.fdMed}` : "—"}
              sub={stats.fdMin != null ? `${stats.fdMin}–${stats.fdMax}` : ""} />
        <Stat label="token agreement" v={stats.agreeMed != null ? pct(stats.agreeMed) : "—"}
              sub={stats.agreeMin != null ? `min ${pct(stats.agreeMin)}` : ""} />
        <Stat label="mean logit KL" v={stats.klMed != null ? stats.klMed.toFixed(3) : "—"}
              sub="vs zero arm" />
      </div>
      <p className="text-[10px] text-gray-500 leading-relaxed mb-2">
        {stats.nSteered} steered runs ({stats.nControl} zero-strength
        controls). The two arms share a prompt and a decoding loop, so the
        only thing separating them is the injected vector — the controls
        confirm it: {stats.nCleanControl}/{stats.nControl} have first-changed-step
        null and 100% agreement, i.e. they never moved.
      </p>

      {/* --- 上面三个中位数把两臂合并了，差异被盖住；这里补配对检验 --- */}
      {arm && arm.up_down_are_exact_negatives && (
        <div className="mb-2 px-2 py-1.5 rounded"
             style={{ background: "#101722", borderLeft: "2px solid #5a6b86" }}
             data-arm-asymmetry
             data-n-pairs={arm.n_pairs}
             data-cos-up-down={arm.cos_up_down}
             data-max-abs-sum={arm.max_abs_up_plus_down}>
          <p className="text-[10px] text-gray-400 leading-relaxed">
            <b>上面三个数把 +v 和 −v 合并了。</b>磁盘上{" "}
            <code>confidence_up</code> 与 <code>confidence_down</code>{" "}
            <b>恰好互为负向量</b>（<code>max|up+down| = {arm.max_abs_up_plus_down}</code>，
            cos = {arm.cos_up_down.toFixed(4)}），所以同题同层同强度下
            只差一个符号 —— 这个配对隔离出的是
            <b>网络沿这条轴的响应不对称</b>，{arm.n_pairs} 道题逐题配对：
          </p>
          <ul className="mt-1 text-[10px] leading-relaxed">
            {arm.metrics.map((m) => (
              <li key={m.metric} data-arm-metric={m.metric}
                  data-arm-diff={m.paired_diff}
                  data-arm-t={m.t}
                  data-arm-distinguishable={String(m.distinguishable)}>
                <span className="text-gray-300">{MLABEL[m.metric] ?? m.metric}</span>
                <span className="text-gray-500">{" "}+v {m.up_mean.toFixed(4)} / −v{" "}
                  {m.down_mean.toFixed(4)}</span>
                <br />
                <span className="font-mono text-gray-400">
                  配对差 {m.paired_diff >= 0 ? "+" : ""}{m.paired_diff.toFixed(4)} ±{" "}
                  {m.paired_sem.toFixed(4)}
                </span>
                {m.distinguishable ? (
                  <>
                    <b className="text-emerald-300"> 两臂分得开</b>
                    <span className="text-gray-600">（t = {m.t.toFixed(1)}）</span>
                  </>
                ) : (
                  <>
                    <b className="text-amber-300"> 分不开</b>
                    <span className="text-gray-600">（t = {m.t.toFixed(1)}，
                      95% CI [{m.ci95_lo.toFixed(1)}, {m.ci95_hi.toFixed(1)}] 跨 0）</span>
                  </>
                )}
              </li>
            ))}
          </ul>
          <p className="text-[10px] text-amber-200/90 leading-relaxed mt-1"
             data-arm-limitation>
            <b>但这不构成方向专属性：</b>本批次
            <b>没有同范数随机方向对照臂</b>。同幅度的随机方向注入同样会产生
            非零 KL、同样会让一致率低于 1，也可能左右不对称。
            缺的那一格已经定位清楚 ——
            <b>同层 {arm.layer}、同强度 ±{arm.strength}、同这 {arm.n_pairs} 道题、
            随机单位方向</b>，跑出来直接和上面两个数比。
            在补上之前，只能说「这条轴的响应不对称且可测」，
            不能说「这个效果是 confidence 特有的」。
          </p>
        </div>
      )}

      {/* --- answers --- */}
      <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">
        What happened to the answer
      </div>
      <div className="flex gap-1 mb-1.5">
        {Object.entries(verdict).map(([k, n]) => (
          <span
            key={k}
            className="text-[9px] font-mono px-1.5 py-0.5 rounded border border-border"
            style={{
              color: k === "right->wrong" ? "#ff8fa3"
                    : k === "wrong->right" ? "#7dd3a8" : "#8891a4",
            }}
            data-verdict={k}
          >
            {k} ×{n}
          </span>
        ))}
      </div>
      <p className="text-[10px] text-gray-500 leading-relaxed mb-2">
        {ans.selection?.n_shipped} of {ans.planned_runs} runs analysed, and
        only those whose two arms produced <i>different</i> parseable
        answers are shown — {ans.selection?.n_eligible} of the batch met
        that bar. So these are the cases where steering moved the answer at
        all. Net change in correct answers: <b>{pw?.net_change ?? 0}</b>.{" "}
        {pw
          ? "这个 0 是欠功效，不是零效应 —— 下面这一块算给你看。"
          : ""}
      </p>

      {/* --- 「净变化 0」到底是零效应，还是这个设计看不到效应 --- */}
      {pw && (
        <div className="mb-2 px-2 py-1.5 rounded"
             style={{ background: "#141019", borderLeft: "2px solid #8b6fd4" }}
             data-answer-power
             data-net-change={pw.net_change}
             data-flips={pw.flips}
             data-flips-needed={pw.flips_needed_for_p05}
             data-n-shipped={pw.n_shipped}
             data-n-batch={pw.n_problems_in_batch}
             data-ci-lo={pw.up_rate_ci95[0]}
             data-ci-hi={pw.up_rate_ci95[1]}
             data-out-domain={pw.labels_not_both_in_domain.length}>
          <p className="text-[10px] text-gray-300 leading-relaxed">
            <b>「净变化 {pw.net_change}」是欠功效，不是零效应。</b>
            {" "}这 {pw.n_problems_in_batch} 道题里只有 <b>{pw.n_shipped}</b> 题进了
            上面那张表，而入选条件之一就是<b>两臂答案不同</b> ——
            算净变化的那个分母，是按「确实变了」挑出来的。
          </p>
          <ul className="mt-1 text-[10px] text-gray-400 leading-relaxed">
            <li data-power-item="flips">
              入选集里只有 <b className="font-mono text-gray-200">{pw.flips}</b>{" "}
              个正确性翻转（{pw.flips_up} 正 / {pw.flips_down} 反）。符号检验双侧
              精确 p = 2×0.5<sup>{pw.flips}</sup> ={" "}
              <span className="font-mono">{pw.two_sided_sign_p_if_all_same_direction}</span>，
              要 p &lt; 0.05 需要 <b className="font-mono text-gray-200">{pw.flips_needed_for_p05}</b>{" "}
              个同向翻转，而本设计上限只有{" "}
              <b className="font-mono text-gray-200">{pw.n_shipped}</b> 个。
              实测 1 正 1 反，是零假设下的<b>典型</b>结果，不是「接近显著」。
            </li>
            <li data-power-item="ci">
              单侧翻转率的 Clopper–Pearson 95% CI ={" "}
              <span className="font-mono text-gray-200">
                [{pw.up_rate_ci95[0].toFixed(3)}, {pw.up_rate_ci95[1].toFixed(3)}]
              </span>
              {" "}—— 上界宽到 <b>{pct(pw.up_rate_ci95[1])}</b>，
              这批数据完全容得下「其实影响很大」。
            </li>
            <li data-power-item="length">
              还有长度偏倚：入选要求两臂都跑完 {"</think>"}，而两臂步数比在{" "}
              <span className="font-mono text-gray-200">
                {pw.steps_ratio_min}×–{pw.steps_ratio_max}×
              </span>
              {" "}之间 ⇒ 入选集偏向两臂都跑到底的题，而那正是干预影响最大的题。
            </li>
            <li data-power-item="ceiling">
              上界：答案改变率 ≤ <span className="font-mono text-gray-200">
                {pw.n_shipped}/{pw.n_problems_in_batch}
              </span>{" "}
              = <b>{pct(pw.flip_rate_ceiling_over_batch)}</b>。剩下{" "}
              <span className="font-mono text-gray-200">
                {pw.n_problems_in_batch - pw.n_shipped}
              </span>{" "}
              题的去向（答案相同 / 未跑完 / 严格口径解析不出）产物里没有分开记，
              这里不替它编。
            </li>
            <li data-power-item="domain">
              还有 <b className="font-mono text-gray-200">
                {pw.labels_not_both_in_domain.length}
              </b>{" "}
              题的<b>两臂答案都落在 AIME 答案域之外</b>（
              {pw.labels_not_both_in_domain.join("、")}
              ）。它们被归进 <code>wrong-&gt;wrong</code>，
              对净变化<b>没有贡献</b>，所以上面所有结论都不受影响；
              但它们的「错」是<b>域外判定</b>，不是与一个合法答案比对出来的。
            </li>
          </ul>
          <p className="text-[10px] text-amber-200/90 leading-relaxed mt-1"
             data-power-not-claimed>
            <b>所以本批能说的只有</b>「在 {pw.n_shipped} 题的入选子集上，
            正 {pw.flips_up} 次 / 反 {pw.flips_down} 次」，
            <b>不能说</b>「干预对答案正确性无影响」。这 {pw.n_shipped} 题也
            <b>不是</b> {pw.n_problems_in_batch} 题的随机样本 ——{" "}
            它们按「答案不同」筛过。另外这一格只覆盖{" "}
            <b>{pw.direction}</b> 一条轴的 −{pw.strength} 单档，另外 3 条命名轴与
            正的 <code>confidence_up</code> 臂都不在这里；
            <b>L7（改变的是概念而非位置/格式）一次都没测</b> ——
            「答案对不对」连位置轴对照都没有。
          </p>
        </div>
      )}

      <div className="flex flex-col gap-1" data-answer-rows>
        {ans.items.slice(0, 4).map((it) => (
          <div key={it.label} className="rounded bg-bg/60 border border-border px-2 py-1">
            <div className="flex items-baseline justify-between text-[10px]">
              <span className="text-gray-400 font-mono truncate">{it.label}</span>
              <span style={{
                color: it.verdict === "right->wrong" ? "#ff8fa3"
                    : it.verdict === "wrong->right" ? "#7dd3a8" : "#8891a4",
              }}>
                {it.verdict}
              </span>
            </div>
            <div className="text-[10px] font-mono text-gray-300 mt-0.5">
              {it.zero.answer} <span className="text-gray-600">→</span>{" "}
              <span style={{
                color: it.zero.answer !== it.steered.answer ? "#ffd479" : "#6b7280",
              }}>
                {it.steered.answer}
              </span>
            </div>
            <div className="text-[9px] text-gray-600 font-mono">
              diverged after {it.shared_prefix_chars} chars
            </div>
          </div>
        ))}
      </div>

      <p className="text-[10px] text-gray-600 leading-relaxed mt-2">
        Coverage is narrow and worth stating plainly: these answer
        comparisons exist for <b>{ans.direction}</b> at strength{" "}
        {ans.strength} only, and {changed} of {ans.selection?.n_shipped} shown
        problems changed their answer at all. The token-level table above
        covers {stats.nSteered} runs across both directions.
        {stats.batchComplete
          ? ""
          : ` The 32k batch is incomplete (${cot.n_runs}/${stats.planned} runs).`}
      </p>

      {/* --- why the slider looks like it does nothing --- */}
      <div
        className="mt-2 px-2 py-1.5 rounded text-[10px] leading-relaxed"
        style={{ background: "#131a28", borderLeft: "2px solid #4a90d9", color: "#9db4cc" }}
        data-invisible-note
      >
        <b>Why the 3-D curve barely moves when you inject.</b> Measured on
        this recording: the injection shifts the projection by an L1
        distance of ~0.02, against a trajectory whose own coordinates span
        ~5.4 — about <b>0.3%</b>. An independent SVD says why: the vector
        moves the top-3 subspace by 29.8 while the model itself moves 30.4
        per step. One injection is worth about one step of the model&apos;s
        own motion. It is acting on the residual stream (‖v‖ and its
        projection are reported live) — it is just not visible in three
        dimensions.
      </div>

      {/* --- what is deliberately not shown --- */}
      <details className="mt-2" data-omitted>
        <summary className="text-[10px] text-gray-500 cursor-pointer">
          Not shown: the in-sample necessity numbers
        </summary>
        <p className="text-[10px] text-gray-600 leading-relaxed mt-1">
          A separate artifact claims each vector modulates its own concept,
          with several directions passing its gate. Those correlations are
          circular: the vector is defined as a difference of group means
          over these tokens, then correlated back against the same labels,
          so the pass/fail is an identity rather than a finding. One
          direction rests on 3 trajectories out of 48. The non-circular
          (held-out) half of that evidence is not reproduced here either.
          Numbers like these render as convincing bars and mean nothing,
          so the panel omits them and tells you instead.
        </p>
        <p className="text-[10px] text-gray-600 leading-relaxed mt-1.5">
          That artifact also records one check as
          &ldquo;not recomputed, no weights on this machine&rdquo;. The
          weights are in this repository under{" "}
          <span className="font-mono">datasets/models/Qwen3-1.7B/</span>, and
          the step was run independently afterwards: argmax reproduces the
          recorded token on 99.5% of sampled steps, max logit error 0.125
          against the stored top-64. It needs numpy and about half a minute,
          not a GPU. The gap was bookkeeping, not a missing prerequisite.
        </p>
      </details>
    </div>
  );
}

function Head() {
  return (
    <div className="flex items-baseline justify-between">
      <span className="text-[10px] text-gray-500 uppercase tracking-wider">
        What the vector did
      </span>
      <span className="text-[9px] text-gray-600 font-mono">offline · 32k</span>
    </div>
  );
}

function Stat({ label, v, sub }: { label: string; v: string; sub?: string }) {
  return (
    <div className="rounded bg-bg/60 border border-border px-1.5 py-1">
      <div className="text-[9px] text-gray-500 leading-tight">{label}</div>
      <div className="text-[12px] text-gray-200 font-mono leading-tight">{v}</div>
      {sub ? <div className="text-[9px] text-gray-600 font-mono">{sub}</div> : null}
    </div>
  );
}

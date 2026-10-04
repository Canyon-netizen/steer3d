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

type DirCompare = {
  what: string;
  layer: number;
  strength: number;
  n_problems: number;
  shared_control: { claim: string; n_identical_zero_arms: number; n_problems: number; holds: boolean };
  closed_counts: {
    zero_shared: number;
    // ⚠ down_minus_v / up_plus_v 是**与共享零臂配对后的交集**，
    //   不是各臂自己的闭合数。两个口径第十七笔起都必须在页面上分开印。
    down_minus_v: number; up_plus_v: number;
    down_arm_own: number; up_arm_own: number;
    zero_closed_down_blew: number; down_closed_zero_blew: number;
    caliber: string;
    n_problems: number;
  };
  blew_up: {
    table_on_shared_zero_control: {
      n_zero_closed: number; both_closed: number;
      up_only_blew_up: number; down_only_blew_up: number; both_blew_up: number;
    };
    n_up_vs_shared_control: number;
    n_down_vs_shared_control: number;
    mcnemar_exact_p: number;
    zero_arm_at_cap: number;
  };
  length: {
    ratio_median_down: number; ratio_median_up: number;
    n_up_ratio_gt_down: number; n_problems: number; sign_test_p: number;
  };
  kl_contrast: {
    mean_logit_kl_up: number; mean_logit_kl_down: number;
    larger_kl_direction: string; more_blew_up_direction: string; opposite: boolean;
  };
  per_direction: Record<string, {
    n_complete: number; n_incomplete: number; verdicts: Record<string, number>;
    baseline_correct: number; steered_correct: number; net_change: number;
    changed: number; changed_rate: number | null; arms_at_token_cap: number;
  }>;
  verdict: string;
  not_claimed: string;
};

// §4.17「跑飞」到底是怎么坏的。方向对照块只说 +v 撞 token 上限，
// 没说机制；这份产物给出机制（逐字重复退化），以及它在**长度受控**下
// 到底能分离出多少。写入它的是 .cache/xcheck/steer_repetition.py。
type Repetition = {
  what: string;
  k_grams: number;
  window_words: number;
  strong_repeat_threshold: number;
  why_window: string;
  nonoverlap_note: string;
  dedup_note: string;
  layer: number;
  strength: number;
  cut_sweep: Array<{
    words: number;
    zero: { n_strong: number; n_eligible: number };
    minus_v: { n_strong: number; n_eligible: number };
    plus_v: { n_strong: number; n_eligible: number };
    same_problem_set: boolean;
    verdict: string;
    fisher_p_plus_vs_zero?: number;
    fisher_p_plus_vs_minus?: number;
  }>;
  summary: Array<{
    arm: string; n: number;
    rep_k_median: number; rep_k_max: number; rep_k_mean: number;
    rep_frac_median: number; rep_frac_max: number;
    n_with_rep_ge5: number; n_with_rep_ge20: number;
    n_with_onset: number; onset_median: number | null;
  }>;
};

// §8.6 主张降级器。写它的是 .cache/xcheck/claim_audit.py：
// 给一句结论和它的证据字段，机械地报出「它实际站得住的第几级」。
// 它是本项目对「别人给我的结论」唯一能**反过来用**的工具 ——
// §6 答「我该做什么」，§8.1 答「本项目到哪了」，两者都不回答这个。
type ClaimAudit = {
  what: string;
  why: string;
  levels: Array<{
    level: number; label: string; needs: string[];
    entails: string; cheapest_next: string;
  }>;
  random_ceiling_note: string;
  direction_substitution_note: string;
  coverage_limitation: {
    intended_primary_input: string;
    status: string;
    why: string;
    decision: string;
    consequence: string;
  };
  samples: Array<{
    id: string; source: string; kind: string; quote: string;
    declared_level: number | null;
    audit: {
      max_level_supported: number;
      declared_level: number | null;
      overreach_vs_declared: boolean;
      survives_direction_substitution: boolean;
      random_same_norm_arms: number;
      random_control_ceiling_quantile: number;
      entails: string;
      violations: Array<{ assertion: string; why: string }>;
      cheapest_next_step: { to_level: number; gate: string; how: string } | null;
    };
  }>;
};

// §8.7 把尺子指向真实论文摘要。写它的是 .cache/xcheck/lit_audit.py。
// ⚠ 第二十八笔新增：只声明**这一块真正读到的**字段，不整份照抄。
//   理由与 O 层那条纪律一致：类型写全了而代码不用其中一半，
//   读代码的人会以为那些字段参与了什么判断。
type VectorRolesLite = {
  unmeasured?: {
    lm_head_anchor?: {
      claim?: string;
      status?: string;
      reason?: string;
      pre_existing_measurement?: string;
    };
  };
  necessity?: {
    in_sample_circular?: Record<
      string,
      Record<string, {
        n_traj_pooled?: number;
        n_traj_within_which_rho_is_defined?: number;
        rho_within_traj?: number;
      }>
    >;
  };
};

type LitAudit = {
  what: string;
  source: { api: string; query: string; n_papers: number; only_abstracts: boolean };
  headline: {
    n_papers: number;
    n_with_verbatim_claim: number;
    n_naming_any_control_in_abstract: number;
    n_with_same_norm_random_control_known: number;
    same_norm_unknown: number;
    statement: string;
    what_this_is_not: string;
  };
  hard_rule: string;
  why_not_levels: string;
  rendered_fields: string[];
  rows: Array<{
    arxiv_id: string; title: string; url: string;
    claim_verbatim: string | null;
    max_level_from_abstract: number | null;
    verdict: string;
    controls_named_in_abstract: string[];
    same_norm_random_control: string;
    must_read_in_methods: string[];
    note: string;
  }>;
};

type AnswerPower = {
  what: string;
  direction: string;
  strength: number;
  // 覆盖面声明里的「另外 N 条命名轴」。N 由 answer_power.py 从
  // axis_readouts.axes 现算进产物 —— 原来这里是 JSX 里手抄的 3，
  // 与 arm_asymmetry.json 的同一句话是同一个数，两处都会漂。
  n_other_named_axes: number;
  other_named_axes: string[];
  n_problems_in_batch: number;
  n_complete_pairs: number;
  n_incomplete_pairs: number;
  incomplete_breakdown: { one_arm_closed: number; neither_closed: number; unparseable: number };
  incomplete_arms_at_token_cap: number;
  incomplete_arms_total: number;
  token_cap: number;
  full_verdicts: Record<string, number>;
  baseline_correct: number;
  steered_correct: number;
  net_change: number;
  n_shipped: number;
  shipped_verdicts: Record<string, number>;
  net_change_invariance: {
    claim: string;
    net_over_shipped_10: number;
    net_over_complete_20: number;
    unchanged_pairs_contribution: number;
    holds: boolean;
  };
  answer_change_rate_complete: number;
  changed_n: number;
  changed_but_still_wrong: number;
  changed_but_still_wrong_magnitude: {
    n: number; median: number; min: number; max: number;
    n_below_100: number; out_of_domain_labels: string[];
  };
  flips: number;
  flips_up: number;
  flips_down: number;
  break_denominator: number;
  fix_denominator: number;
  break_rate_ci95: [number, number];
  fix_rate_ci95: [number, number];
  two_sided_sign_p_if_all_same_direction: number;
  flips_needed_for_p05: number;
  max_possible_flips: number;
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
  // 覆盖面声明用的派生值（层/强度/轴数全部由 arm_asymmetry.py 从输入现算）。
  // 这几个字段进产物是为了让「这句话覆盖多少」也能被数据核，而不是印在散文里。
  n_dirs: number;
  named_axes_total: number;
  n_other_named_axes: number;
  other_named_axes: string[];
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
  const [sd, setSd] = useState<DirCompare | null>(null);
  const [rep, setRep] = useState<Repetition | null>(null);
  const [ca, setCa] = useState<ClaimAudit | null>(null);
  const [lit, setLit] = useState<LitAudit | null>(null);
  // ⚠⚠ 第二十八笔新增：这一块讨论的「那个产物」就是 vector_roles.json，
  //   而它**本来没被取**。于是这段话里的三个数全是手抄的：
  //     · 「99.5% of sampled steps」—— 产物给的是 all_steps 1532/1536 = 0.9974，
  //       页面那个 99.5% 既不是 99.74%，口径也说错了（不是抽样，是全部 1536 步）
  //     · 「max logit error 0.125」—— 值对，可是手抄
  //     · 「One direction rests on 3 trajectories out of 48」—— 两个数都有源，
  //       在 necessity.in_sample_circular.{L14,L20}.creativity 里
  //   关键：vector_roles.json 的 unmeasured.lm_head_anchor.pre_existing_measurement
  //   **已经写着全部正确的数**，而且把两个口径分开了
  //   （all_steps 1532/1536 = 0.9974；top1-top2 margin >= 1.0 的可判定步
  //     1420/1420 = 1.0），末尾还自带一句「该数字由 build_logit_lens.py 产出，
  //   不是本脚本重算的，引用而非复现」—— 那正是这里需要的措辞。
  //   ⇒ 直接渲染那句话，不重新叙述它。
  // ⚠ 为什么取它而不是 logit_lens.json：那三个数的结构化字段只在
  //   logit_lens.json 里，而它有 **1.7 MB**（第二大产物）；
  //   本面板现在 8 份产物合计 256 KB，加它就是 6.7 倍 ——
  //   为一个句子里的两个数不划算。vector_roles.json 只有 52 KB。
  const [roles, setRoles] = useState<VectorRolesLite | null>(null);
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
      // 方向对照。单独一份产物：写它的是 .cache/xcheck/steer_directions.py，
      // 它与 answer_power.json 共享 cot_divergence_32k.json 但口径不同
      // （那支只算 −v，这一支算两个方向 + 闭合率），并进任一份都会
      // 让「谁生成哪个字段」变得看不出来。
      fetch("/latent/data/steer_directions.json").then((r) =>
        r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))),
      // 「跑飞」的机制。与上面四份共享 all_runs.json 的原文，但口径是
      // 另一套（逐字重复的 12-gram 计数 + 长度受控），并进去会让
      // 「谁生成哪个字段」看不出来 —— 这一支的窗口/阈值都不是别处能推出来的。
      fetch("/latent/data/steer_repetition.json").then((r) =>
        r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))),
      // 主张降级器。读的是它自己的产物（门控表 + 样本判定），
      // 不从阶梯产物**推导** —— 推导会让两者一改就一起错。
      fetch("/latent/data/claim_audit.json").then((r) =>
        r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))),
      // 尺子指向真实论文摘要。与上一份**独立**：它带 arXiv 原文与逐字引述，
      // 两者一起变坏时还能互相指出问题。
      fetch("/latent/data/lit_audit.json").then((r) =>
        r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))),
      // 第二十八笔：这段话讨论的那个产物本身。52 KB。
      fetch("/latent/data/vector_roles.json").then((r) =>
        r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))),
    ])
      .then(([c, a, m, p, d, rp, q, li, vr]: [CotTexts, AnswerReadout, ArmAsymmetry, AnswerPower, DirCompare, Repetition, ClaimAudit, LitAudit, VectorRolesLite]) => {
        if (alive) {
          setCot(c); setAns(a); setArm(m); setPw(p); setSd(d); setRep(rp);
          setCa(q); setLit(li); setRoles(vr);
        }
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

      {/* --- 「净变化 0」到底是什么：20 个完整配对的全表 + 不变性定理 --- */}
      {pw && (
        <div className="mb-2 px-2 py-1.5 rounded"
             style={{ background: "#141019", borderLeft: "2px solid #8b6fd4" }}
             data-answer-power
             data-net-change={pw.net_change}
             data-n-complete={pw.n_complete_pairs}
             data-n-incomplete={pw.n_incomplete_pairs}
             data-n-shipped={pw.n_shipped}
             data-changed={pw.changed_n}
             data-wrong2wrong={pw.changed_but_still_wrong}
             data-flips={pw.flips}
             data-flips-needed={pw.flips_needed_for_p05}
             data-max-flips={pw.max_possible_flips}
             data-base-right={pw.baseline_correct}
             data-steer-right={pw.steered_correct}>
          <p className="text-[10px] text-gray-300 leading-relaxed">
            <b>「净变化 {pw.net_change}」是欠功效，不是零效应。</b>
            {" "}上一句问的是「干预把答案搞坏了没有」。这一块是把它算干净：
            整批 {pw.n_problems_in_batch} 题里，
            <b>{pw.n_complete_pairs} 题</b>两臂都跑完、构成可比的配对，
            这 {pw.n_complete_pairs} 题的 verdict 全表是 ——
            right-&gt;right <b className="font-mono text-gray-200">
              {pw.full_verdicts["right->right"] ?? 0}</b>、
            right-&gt;wrong <b className="font-mono text-red-300">
              {pw.full_verdicts["right->wrong"] ?? 0}</b>、
            wrong-&gt;right <b className="font-mono text-emerald-300">
              {pw.full_verdicts["wrong->right"] ?? 0}</b>、
            wrong-&gt;wrong <b className="font-mono text-gray-200">
              {pw.full_verdicts["wrong->wrong"] ?? 0}</b>。
            基线答对 <b className="font-mono text-gray-200">{pw.baseline_correct}</b>
            /{pw.n_complete_pairs}，注入后答对{" "}
            <b className="font-mono text-gray-200">{pw.steered_correct}</b>
            /{pw.n_complete_pairs} ⇒ <b>净变化 {pw.net_change}</b>。
          </p>
          <ul className="mt-1 text-[10px] text-gray-400 leading-relaxed">
            <li data-power-item="invariance">
              <b>先回答最容易被怀疑的那一条：这个 0 会不会是筛出来的？</b>
              {" "}不会，而且这<b>不是数据碰巧</b>，是定理 ——
              上面那张表只入表了 {pw.n_shipped} 题（规则含「两臂答案不同」），
              被剔除的 {pw.n_complete_pairs - pw.n_shipped} 题<b>答案都相同</b>，
              答案相同 ⇒ 两臂对错必然一致 ⇒ verdict 恒为 X-&gt;X ⇒{" "}
              <b>对净变化的贡献恒为 0</b>。
              实测印证：入表 {pw.n_shipped} 题净{" "}
              <span className="font-mono text-gray-200">
                {pw.net_change_invariance.net_over_shipped_10}
              </span>{" "}
              = 完整 {pw.n_complete_pairs} 题净{" "}
              <span className="font-mono text-gray-200">
                {pw.net_change_invariance.net_over_complete_20}
              </span>。
            </li>
            <li data-power-item="semantic">
              <b>但「答案变了」不等于「概念变了」。</b>
              答案改变率是 <b className="font-mono text-gray-200">
                {pw.changed_n}/{pw.n_complete_pairs} ={" "}
                {pct(pw.answer_change_rate_complete)}</b>
              ，可这 {pw.changed_n} 次里有{" "}
              <b className="font-mono text-amber-300">
                {pw.changed_but_still_wrong}</b>{" "}
              次<b>前后都是错的</b>（wrong-&gt;wrong），数值中位只动了{" "}
              <span className="font-mono text-gray-200">
                {pw.changed_but_still_wrong_magnitude.median}
              </span>{" "}
              （最小 {pw.changed_but_still_wrong_magnitude.min}、
              最大 {pw.changed_but_still_wrong_magnitude.max}，
              {pw.changed_but_still_wrong_magnitude.n_below_100} 次不到 100）。
              所以「一半的题答案变了」<b>不能</b>读成「一半的题概念变了」。
            </li>
            <li data-power-item="domain">
              上面那 {pw.changed_but_still_wrong_magnitude.n} 次里还有{" "}
              <b>{pw.changed_but_still_wrong_magnitude.out_of_domain_labels.length}</b>{" "}
              次两臂答案都落在 AIME 答案域之外（
              {pw.changed_but_still_wrong_magnitude.out_of_domain_labels.join("、")}
              ），它们的「错」是<b>域外判定</b>，对净变化没有贡献。
            </li>
            <li data-power-item="unknown">
              <b>真正未知的只有 {pw.n_incomplete_pairs} 题</b>（
              {pw.incomplete_breakdown.one_arm_closed} 题只跑完一臂、
              {pw.incomplete_breakdown.neither_closed} 题都没跑完、
              严格口径解析不出的是 <b>{pw.incomplete_breakdown.unparseable}</b> 题）。
              而它们的 {pw.incomplete_arms_total} 条 arm 里有{" "}
              <b className="font-mono text-amber-300">
                {pw.incomplete_arms_at_token_cap}</b>{" "}
              条撞了 <b>{pw.token_cap}</b> token 上限
              ⇒ 未知的那几题恰恰是<b>跑飞了</b>的题，
              也就是干预影响最大的那批。这才是这批数据真正的选择效应。
            </li>
            <li data-power-item="power">
              <b>功效仍然不够。</b>正确性翻转{" "}
              <b className="font-mono text-gray-200">{pw.flips}</b> 次
              （{pw.flips_up} 正 / {pw.flips_down} 反），
              符号检验双侧精确 p ={" "}
              <span className="font-mono text-gray-200">
                {pw.two_sided_sign_p_if_all_same_direction}
              </span>
              ，要 p &lt; 0.05 需要 <b className="font-mono text-gray-200">
                {pw.flips_needed_for_p05}</b>{" "}
              个同向翻转 —— 而 {pw.n_complete_pairs} 个完整配对<b>够得着</b>{" "}
              {pw.flips_needed_for_p05} 个（最多 {pw.max_possible_flips} 个）。
              破坏率是 1/{pw.break_denominator}、修复率是 1/{pw.fix_denominator}，
              两个 95% 区间分别是{" "}
              <span className="font-mono text-gray-200">
                [{pw.break_rate_ci95[0].toFixed(3)}, {pw.break_rate_ci95[1].toFixed(3)}]
              </span>{" "}
              与{" "}
              <span className="font-mono text-gray-200">
                [{pw.fix_rate_ci95[0].toFixed(3)}, {pw.fix_rate_ci95[1].toFixed(3)}]
              </span>
              ，都宽到没法据此说任何一边。
            </li>
          </ul>
          <p className="text-[10px] text-amber-200/90 leading-relaxed mt-1"
             data-power-not-claimed>
            <b>所以本批能说的只有</b>「{pw.n_complete_pairs} 个可比配对上，
            破坏 1 次、修复 1 次，净变化 0；答案变了 {pw.changed_n} 次，
            其中 {pw.changed_but_still_wrong} 次前后都是错的」。
            <b>不能说</b>「干预对答案正确性无影响」，也<b>不能说</b>「准确率没有下降」——
            净变化 0 只是「1 修 1 破」相抵，两边区间都极宽。
            另外这 {pw.n_complete_pairs} 个配对也<b>不是</b>{" "}
            {pw.n_problems_in_batch} 题的随机样本：被剔掉的 {pw.n_incomplete_pairs} 题
            不是随机抽掉的，是<b>撞 token 上限才没跑完</b>的。
            这一格只覆盖 <b>{pw.direction}</b> 一条轴的 −{pw.strength} 单档，
            另外 {pw.n_other_named_axes} 条命名轴与正的{" "}
            <code>confidence_up</code> 臂都不在这里；
            <b>L7（改变的是概念而非位置/格式）一次都没测</b> ——
            「答案对不对」连位置轴对照都没有。
          </p>
        </div>
      )}

      {/* --- 同一根轴的另一个符号：+v 几乎让整个批次跑飞（§4.16）---
          上面整块只看了 −v 一侧。disk 上还有同 23 题的 +v 臂，
          而两个方向的零强度臂逐字相同（23/23）⇒ 共享同一份对照，
          配对里没有「两次运行」的噪声源，只差注入符号一个变量。 */}
      {sd && (
        <div className="mb-2 px-2 py-1.5 rounded"
             style={{ background: "#101a14", borderLeft: "2px solid #3f9e6a" }}
             data-direction-compare
             data-n={sd.n_problems}
             data-zero-identical={sd.shared_control.n_identical_zero_arms}
             data-zero-closed={sd.closed_counts.zero_shared}
             data-down-closed={sd.closed_counts.down_minus_v}
             data-up-closed={sd.closed_counts.up_plus_v}
             data-down-own={sd.closed_counts.down_arm_own}
             data-up-own={sd.closed_counts.up_arm_own}
             data-zero-closed-down-blew={sd.closed_counts.zero_closed_down_blew}
             data-down-closed-zero-blew={sd.closed_counts.down_closed_zero_blew}
             data-up-only={sd.blew_up.table_on_shared_zero_control.up_only_blew_up}
             data-down-only={sd.blew_up.table_on_shared_zero_control.down_only_blew_up}
             data-mcnemar-p={sd.blew_up.mcnemar_exact_p}
             data-up-rw={sd.per_direction.up.verdicts["right->wrong"] ?? 0}
             data-up-net={sd.per_direction.up.net_change}
             data-opposite={String(sd.kl_contrast.opposite)}
             data-len-p={sd.length.sign_test_p}>
          <p className="text-[10px] text-gray-300 leading-relaxed">
            <b>同一根轴，把符号换过来，行为完全相反。</b>
            {" "}上面整块只看了 <code>−v</code>。disk 上还有同 {sd.n_problems} 道题的{" "}
            <code>+v</code> 臂，而两个方向的<b>零强度臂逐字相同</b>（
            {sd.shared_control.n_identical_zero_arms}/{sd.n_problems}）⇒
            它们共享同一份对照，配对里没有「两次运行」的噪声源，
            只差注入向量这一个变量。
          </p>
          {/* ⚠ 第十七笔：这三格原来印的是 `closed_counts.down_minus_v` /
              `up_plus_v`，而那两个字段是**与零臂配对后的交集**，不是各臂
              自己的闭合数。并排读成三个同口径「闭合率」时，21 / 20 / 5
              会读成「−v 跑挂了 1 题」—— 而这一节要说的恰恰是「−v 不跑飞」。
              真实情况：−v 自己跑完 {down_arm_own}/23，与零臂同数；
              配对那格少 1 题是因为两侧各有 1 题没跑完（对称）。 */}
          <div className="grid grid-cols-3 gap-1.5 my-1">
            <Stat label="零臂（共享对照）" v={`${sd.closed_counts.zero_shared}/${sd.n_problems}`}
                  sub="自己跑完 </think>" />
            <Stat label="−v 臂自己跑完" v={`${sd.closed_counts.down_arm_own}/${sd.n_problems}`}
                  sub="与零臂同数" />
            <Stat label="+v 臂自己跑完" v={`${sd.closed_counts.up_arm_own}/${sd.n_problems}`}
                  sub="大面积跑飞" />
          </div>
          <p className="text-[9.5px] text-gray-500 leading-relaxed mb-1"
             data-dir-item="paired-caliber">
            <b>另一口径：与零臂配对比较</b>（零臂 ∧ 该臂都跑完的<b>交集</b>）
            —— −v <b className="font-mono text-gray-300">
              {sd.closed_counts.down_minus_v}/{sd.n_problems}</b>{" "}
            vs +v <b className="font-mono text-gray-300">
              {sd.closed_counts.up_plus_v}/{sd.n_problems}</b>。
            ⚠ −v 那格比零臂少 {sd.closed_counts.zero_closed_down_blew} 题，原因是
            <b>{sd.closed_counts.zero_closed_down_blew} 题零臂跑完而 −v 没跑完</b>、
            另有 <b>{sd.closed_counts.down_closed_zero_blew} 题反过来</b>
            —— <b>两侧对称，所以这 1 题不构成 −v 跑飞</b>。
          </p>
          <ul className="mt-0.5 text-[10px] text-gray-400 leading-relaxed">
            <li data-dir-item="mcnemar">
              在零臂闭合的 {sd.blew_up.table_on_shared_zero_control.n_zero_closed} 题里：
              <b className="font-mono text-amber-300">
                {sd.blew_up.table_on_shared_zero_control.up_only_blew_up}</b>{" "}
              题<b>只有 +v 跑不完</b>，
              <b className="font-mono text-gray-200">
                {sd.blew_up.table_on_shared_zero_control.down_only_blew_up}</b>{" "}
              题只有 −v 跑不完，McNemar 双侧精确 p ={" "}
              <span className="font-mono text-gray-200">
                {sd.blew_up.mcnemar_exact_p.toExponential(2)}
              </span>
              。加上两臂都没跑完的{" "}
              {sd.blew_up.table_on_shared_zero_control.both_blew_up} 题，
              +v 相对共享对照一共让{" "}
              <b className="font-mono text-gray-200">
                {sd.blew_up.n_up_vs_shared_control}</b>{" "}
              题从「跑得完」变成「跑不完」，−v 只有{" "}
              <b className="font-mono text-gray-200">
                {sd.blew_up.n_down_vs_shared_control}</b>{" "}
              题。
            </li>
            <li data-dir-item="kl">
              <b>而且这与注入幅度相反。</b>同一层同一强度下，
              <code>−v</code> 把分布推得<b>更远</b>（KL{" "}
              <span className="font-mono text-gray-200">
                {sd.kl_contrast.mean_logit_kl_down.toFixed(4)}
              </span>{" "}
              对 +v 的{" "}
              <span className="font-mono text-gray-200">
                {sd.kl_contrast.mean_logit_kl_up.toFixed(4)}
              </span>
              ），却<b>更少跑飞</b>。
              ⇒ 「把分布推得远」和「把生成推入不收敛」是两件事，
              本项目这条轴上两者的方向<b>相反</b>。
            </li>
            <li data-dir-item="length">
              生成长度配对中位数：+v{" "}
              <span className="font-mono text-gray-200">
                {sd.length.ratio_median_up.toFixed(2)}×
              </span>{" "}
              对 −v{" "}
              <span className="font-mono text-gray-200">
                {sd.length.ratio_median_down.toFixed(2)}×
              </span>
              ，同题比较 {sd.length.n_up_ratio_gt_down}/{sd.length.n_problems} 题
              +v 更长 —— 但符号检验 p ={" "}
              <span className="font-mono text-gray-200">
                {sd.length.sign_test_p.toFixed(3)}
              </span>{" "}
              <b className="text-amber-300">没到 0.05</b>。
              ⇒ <b>长度是弱证据</b>，能站住的是上面的闭合率。
            </li>
          </ul>
          <p className="text-[10px] text-amber-200/90 leading-relaxed mt-1"
             data-dir-trap>
            ⚠ <b>这里有个很容易踩的坑：只看闭合的那几题，+v 臂的 verdict 是{" "}
            right-&gt;wrong <b>{sd.per_direction.up.verdicts["right->wrong"] ?? 0}</b>、
            净变化 <b>{sd.per_direction.up.net_change}</b> —— 读起来像
            「+v 是最安全的方向」。</b>
            那是 <b>{sd.per_direction.up.n_incomplete}/{sd.n_problems}</b>{" "}
            未闭合制造出来的假象：<b>破坏没有消失</b>，
            它从「答错」变成了「答不出来」，而按 verdict 计数<b>看不见</b>。
            ⇒ 对 +v 唯一诚实的读法是：<b>
              它在 {sd.per_direction.up.n_incomplete}/{sd.n_problems} 的题上
              根本没有产出答案</b>。
            <br />
            <b>不能说的</b>：本项目只有 s = {sd.strength} <b>一个强度点</b>，
            所以「某个阈值之上 +v 会跑飞」是<b>假设</b>，既不能证实也不能证伪；
            也不能把这个符号不对称说成 confidence 这个<b>概念</b>的性质 ——
            <b>缺同范数随机方向臂</b>，排除不了「±v 各自靠近某个不稳定吸引域」
            这种更平凡的解释。
          </p>
        </div>
      )}

      {/* --- §4.17：+v「跑飞」的机制，以及它在长度受控下能分离出多少 --- */}
      {rep && (() => {
        const byArm = (n: string) => rep.summary.find((s) => s.arm === n)!;
        const z = byArm("zero"), mv = byArm("minus_v"), pv = byArm("plus_v");
        const clean = rep.cut_sweep.filter((c) => c.same_problem_set);
        const best = clean.reduce(
          (a, b) => ((a.fisher_p_plus_vs_zero ?? 1) <= (b.fisher_p_plus_vs_zero ?? 1) ? a : b));
        const dirty = rep.cut_sweep.filter((c) => !c.same_problem_set);
        return (
        <div className="rounded bg-bg/60 border border-border px-2 py-1.5"
             data-repetition
             data-rep-words={String(best.words)}
             data-rep-plus={String(best.plus_v.n_strong)}
             data-rep-zero={String(best.zero.n_strong)}
             data-rep-minus={String(best.minus_v.n_strong)}
             data-rep-p={String(best.fisher_p_plus_vs_zero)}
             data-rep-p-minus={String(best.fisher_p_plus_vs_minus)}
             data-rep-same-set={best.same_problem_set ? 1 : 0}
             data-rep-dirty-cuts={dirty.map((c) => c.words).join("/")}
             data-rep-max-plus={String(pv.rep_k_max)}
             data-rep-max-zero={String(z.rep_k_max)}
             data-rep-max-minus={String(mv.rep_k_max)}
             data-rep-k={String(rep.k_grams)}
             data-rep-thresh={String(rep.strong_repeat_threshold)}
             data-rep-n={String(rep.summary[0].n)}>
          <div className="text-[11px] text-gray-200 font-semibold">
            「跑飞」不是没答完，是逐字重复退化 —— 但能分离出的量有限
          </div>
          <p className="text-[10px] text-gray-400 leading-relaxed mt-1"
             data-rep-mechanism>
            上面只说了 +v 撞 token 上限，<b>没说怎么坏的</b>。
            翻原文可见机制：模型卡在同一句上<b>逐字重复</b>直到撞上限，
            不是啰嗦、不是犹豫、不是答不出来而已。
            度量用 <code>{rep.k_grams}</code>-gram 的<b>不重叠</b>重复次数
            （{rep.nonoverlap_note}），
            「强重复」= 某个 {rep.k_grams}-gram 不重叠出现{" "}
            <b className="font-mono text-gray-200">
              &ge; {rep.strong_repeat_threshold}</b> 次。
            窗口内最强的一处：+v 重复{" "}
            <b className="font-mono text-gray-200">{pv.rep_k_max}</b> 次，
            共享对照和 −v 都只有{" "}
            <b className="font-mono text-gray-200">
              {z.rep_k_max} / {mv.rep_k_max}</b> 次。
          </p>
          <ul className="mt-1.5 space-y-1 text-[10px] text-gray-300 leading-relaxed">
            <li data-rep-item="controlled">
              <b>必须做长度受控，否则是自证的。</b>{" "}
              {rep.why_window}
              在三臂入选<b>同一批题</b>的 {best.words} 词窗口里，
              强重复：+v{" "}
              <b className="font-mono text-gray-200">
                {best.plus_v.n_strong}/{best.plus_v.n_eligible}</b>、
              共享对照{" "}
              <b className="font-mono text-gray-200">
                {best.zero.n_strong}/{best.zero.n_eligible}</b>、
              −v{" "}
              <b className="font-mono text-gray-200">
                {best.minus_v.n_strong}/{best.minus_v.n_eligible}</b>，
              Fisher 精确检验 p ={" "}
              <span className="font-mono text-gray-200">
                {best.fisher_p_plus_vs_zero?.toFixed(3)}
              </span>{" "}
              {best.fisher_p_plus_vs_zero != null &&
               best.fisher_p_plus_vs_zero < 0.05 ? (
                <b className="text-emerald-300">已过 0.05</b>
              ) : (
                <b className="text-amber-300">
                  没到 0.05 —— 方向一致、量级 4 倍，但只是弱证据
                </b>
              )}
              。这条修的是同一片混淆（§8.3 ⑧），方向和量级都对，
              <b>但不该当成已证实的机制</b>。
            </li>
            <li data-rep-item="confounded">
              <b>看起来更好的那些数字不能引用。</b>把窗口放大到{" "}
              {dirty.map((c) => c.words).join(" / ")} 词时 p 会小到{" "}
              {dirty.map((c) => c.fisher_p_plus_vs_zero?.toFixed(3))
                 .filter((x) => x != null).join(" / ")}，
              看起来强得多 —— 但那一档<b>三臂入选的题集不同</b>：
              入选「全文够长」的题，本身就是长的、
              也就是更容易没跑完的题，而没跑完和 +v 相关。
              ⇒ 那是<b>按长度筛题</b>挑出来的，不是长度受控的结果。
            </li>
            <li data-rep-item="why">
              <b>所以机制结论分两层，不能混着说。</b>
              「+v 会把生成推入逐字重复循环」这条，机制上直接可见
              （重复 {pv.rep_k_max} 次 vs 对照 {z.rep_k_max} 次），
              <b>不依赖那个 p</b>；
              但「重复比对照显著更多」在严格长度受控下{" "}
              <b>只到弱证据</b>。
              强的那条证据仍然是闭合率（上面 p ={" "}
              <span className="font-mono text-gray-200">
                {sd?.blew_up.mcnemar_exact_p.toExponential(2) ?? "—"}
              </span>
              ），它按题计数，不受文本长度影响。
            </li>
          </ul>
          <p className="text-[10px] text-amber-200/90 leading-relaxed mt-1.5"
             data-rep-cannot>
            <b>不能说的</b>：不能说「重复退化是 confidence 这个概念触发的」——
            还是<b>缺同范数随机方向臂</b>；也不能说「重复就是跑飞的全部机制」——
            这里只量了逐字重复，撞上限还可能有别的成因。
            另外这份比较只看 {rep.strength === 0.2 ? "s = 0.2" : rep.strength} 的{" "}
            {rep.layer === 20 ? "L20" : `L${rep.layer}`}，
            <b>一个强度点、一层</b>。
            {rep.dedup_note}
          </p>
        </div>
        );
      })()}

      {/* --- §8.7 把尺子指向真实论文的摘要 --- */}
      {lit && (() => {
        const H = lit.headline;
        const withClaim = lit.rows.filter((r) => r.claim_verbatim);
        const named = lit.rows.filter((r) => r.controls_named_in_abstract.length > 0);
        return (
        <div className="rounded bg-bg/60 border border-border px-2 py-1.5"
             data-lit-audit
             data-lit-n={String(lit.source.n_papers)}
             data-lit-claim={String(H.n_with_verbatim_claim)}
             data-lit-ctrl={String(H.n_naming_any_control_in_abstract)}
             data-lit-samenorm={String(H.n_with_same_norm_random_control_known)}
             data-lit-samenorm-unknown={String(H.same_norm_unknown)}
             data-lit-rendered-fields={String(lit.rendered_fields.length)}>
          <div className="text-[11px] text-gray-200 font-semibold">
            把这把尺子指向真实论文的摘要：{H.n_papers} 篇，0 篇可判
          </div>
          <p className="text-[10px] text-gray-400 leading-relaxed mt-1"
             data-lit-rule>
            {/* ⚠ 标签只写「提示」，不重复产物字符串的第一句 ——
                我第一版标签和字符串都以「摘要里没有的东西，不许替论文填」开头，
                页面上连着印了两遍。判据全绿，**只有截图能看出来**。 */}
            <b>硬规矩：</b>
            {lit.hard_rule}
            抓取源 <code>{lit.source.api}</code>，查询{" "}
            <code className="font-mono">{lit.source.query}</code>，
            只入库摘要（每条引述都可对着原文核）。
          </p>
          <ul className="mt-1.5 space-y-1 text-[10px] text-gray-300 leading-relaxed">
            <li data-lit-item="headline">
              {H.statement}
              {H.n_with_same_norm_random_control_known === 0 && (
                <b className="text-amber-300">
                  {" "}注意这是「未知」不是「没有」。
                </b>
              )}
            </li>
            <li data-lit-item="notaccuse">
              {H.what_this_is_not}
            </li>
            <li data-lit-item="levels">
              <b>为什么不给「级别低」，只给「未定」。</b>
              {lit.why_not_levels}
            </li>
            <li data-lit-item="read">
              抽到逐字主张句 <b className="font-mono text-gray-200">
                {H.n_with_verbatim_claim}</b> / {H.n_papers} 篇；
              摘要里点名过任何对照的{" "}
              <b className="font-mono text-gray-200">
                {H.n_naming_any_control_in_abstract}</b> 篇
              （含 {named.slice(0, 2).map((r) => r.arxiv_id).join("、")
                 || "无"}）。要真判定，方法章节里必须逐条核这{" "}
              {lit.rows[0]?.must_read_in_methods.length ?? 0} 项。
            </li>
          </ul>
          <details className="mt-1" data-lit-detail>
            <summary className="text-[10px] text-gray-500 cursor-pointer">
              展开 {withClaim.length} 条逐字引述
            </summary>
            <ul className="mt-1 space-y-1.5">
              {withClaim.map((r) => (
                <li key={r.arxiv_id} className="text-[10px] text-gray-400 leading-relaxed"
                    data-lit-row={r.arxiv_id}>
                  <a className="text-gray-300 font-mono" href={r.url}
                     target="_blank" rel="noreferrer">{r.arxiv_id}</a>
                  {" "}<span className="text-gray-500">{r.title.slice(0, 60)}</span>
                  <div className="text-gray-300 mt-0.5">「{r.claim_verbatim}」</div>
                  <div className="text-gray-500 mt-0.5">
                    摘要点名对照 {r.controls_named_in_abstract.length} 处 ·
                    同范数随机方向 = {r.same_norm_random_control}
                  </div>
                </li>
              ))}
            </ul>
          </details>
        </div>
        );
      })()}

      {/* --- §8.6 主张降级器：把一句结论换算成它站得住的第几级 --- */}
      {ca && (() => {
        // ⚠ 按 id 取，**不要用下标**。我第一版写 ca.samples[0]/[2]/[3]，
        //   而 samples[2] 其实是 l6 那条（声明 6 / 实测 4），不是 l2 ——
        //   M0 立刻报出 DOM 是 6/4、产物是 3/2。下标错位在数据变动时静默。
        const byId = (id: string) => ca.samples.find((x) => x.id === id)!;
        const s0 = byId("l0-only"), s1 = byId("l2-no-specificity"),
              s2 = byId("l6-no-random-arm"),
              s3 = byId("project-confidence-claim");
        return (
        <div className="rounded bg-bg/60 border border-border px-2 py-1.5"
             data-claim-audit
             data-ca-n={String(ca.samples.length)}
             data-ca-l0-declared={String(s0.audit.declared_level)}
             data-ca-l0-supported={String(s0.audit.max_level_supported)}
             data-ca-l0-survives={String(s0.audit.survives_direction_substitution ? 1 : 0)}
             data-ca-l2-declared={String(s1.audit.declared_level)}
             data-ca-l2-supported={String(s1.audit.max_level_supported)}
             data-ca-l6-declared={String(s2.audit.declared_level)}
             data-ca-l6-supported={String(s2.audit.max_level_supported)}
             data-ca-self-declared={String(s3.audit.declared_level)}
             data-ca-self-supported={String(s3.audit.max_level_supported)}
             data-ca-nlevels={String(ca.levels.length)}>
          <div className="text-[11px] text-gray-200 font-semibold">
            这句话站得住第几级？—— 反过来用的那把尺子
          </div>
          <p className="text-[10px] text-gray-400 leading-relaxed mt-1"
             data-ca-why>
            {ca.why}
            它不猜语义，只按<b>可机械核查的证据门控</b>算，共{" "}
            <b className="font-mono text-gray-200">{ca.levels.length}</b> 级。
            下面四句是它跑出来的结果：
          </p>
          <ul className="mt-1.5 space-y-1 text-[10px] text-gray-300 leading-relaxed">
            <li data-ca-item="l0">
              「Steering along this direction shifts internal representations」
              声明 L{s0.audit.declared_level} ⇒ 只能站住{" "}
              <b className="font-mono text-gray-200">
                L{s0.audit.max_level_supported}</b>，而且
              <b className={s0.audit.survives_direction_substitution
                ? "text-amber-300" : "text-emerald-300"}>
                {s0.audit.survives_direction_substitution
                  ? "换个随机方向逐字成立" : "换个随机方向就不成立"}
              </b>。
              {s0.audit.entails}
            </li>
            <li data-ca-item="l2">
              「This direction linearly encodes the honesty state」
              声明 L{s1.audit.declared_level} ⇒{" "}
              <b className="font-mono text-gray-200">
                L{s1.audit.max_level_supported}</b>
              （差一级：没做专属性矩阵）。{s1.audit.entails}
            </li>
            <li data-ca-item="l6">
              「Injecting the vector improves accuracy」
              声明 L{s2.audit.declared_level} ⇒{" "}
              <b className="font-mono text-gray-200">
                L{s2.audit.max_level_supported}</b>，
              缺<b>同范数随机方向臂</b>，排除不了「随便什么方向都能做到」。
              {s2.audit.cheapest_next_step
                ? <>升到 L{s2.audit.cheapest_next_step.to_level} 只需：{
                    s2.audit.cheapest_next_step.how}</>
                : null}
            </li>
            <li data-ca-item="self">
              <b>本项目自己那句话</b>
              {/* ⚠⚠ 第二十八笔：原来这里是手写的一句转述
                  「（±v 闭合率 5/23 vs 20/23，破坏模式是逐字重复退化）」。
                  而 s3.quote（claim_audit.json 的原文）是：

                    在同一根轴上注入 +v 会让生成跑飞（闭合率 5/23 vs
                    **共享对照 21/23**），而 −v 几乎不变（20/23）；
                    破坏模式是逐字重复退化。

                  ⇒ 转述把「共享对照 21/23」和「−v 的 20/23」并成了
                    一个「20/23」，于是这句话与它**所引用的原文**自相矛盾；
                  而 steer_directions.json 的 closed_counts.caliber 字段明写：
                    down_minus_v / up_plus_v = 与共享零臂**配对**后两臂都跑完的题数
                    down_arm_own / up_arm_own = 该臂自己跑完的题数
                  ⇒ 20 与 21 是**两个口径**（配对交集 vs 零臂自身），
                    不写出来就成了同屏矛盾（第十七笔在主三格表上修过一次，
                    这里这个自评块是同一问题的第二处）。
                  修法不是把那三个数算对，是**别再转述** ——
                  原样渲染 quote，它自己就分得清两个口径。
                  同一个 <li> 里的兄弟条目（cheapest_next_step.how 等）
                  本来就是直接渲染产物字符串的，这里是唯一一处例外。 */}
              <span data-ca-self-quote={s3.quote}>{s3.quote}</span>
              {" "}声明 L{s3.audit.declared_level} ⇒ 按它自己的尺子只到{" "}
              <b className="font-mono text-gray-200">
                L{s3.audit.max_level_supported}</b>。
              差的正是那条随机臂。
            </li>
          </ul>
          <p className="text-[10px] text-gray-400 leading-relaxed mt-1.5"
             data-ca-ceiling>
            <b>随机臂不设魔法阈值，只报你能说到哪。</b>
            {ca.random_ceiling_note}
            {ca.direction_substitution_note}
          </p>
          <p className="text-[10px] text-amber-200/90 leading-relaxed mt-1"
             data-ca-coverage>
            <b>这条尺子有个覆盖限制，必须一起说。</b>
            {ca.coverage_limitation.decision}
            {ca.coverage_limitation.consequence}
          </p>
        </div>
        );
      })()}

      <div className="flex flex-col gap-1" data-answer-rows>        {ans.items.slice(0, 4).map((it) => (
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
          so the pass/fail is an identity rather than a finding.{" "}
          {/* ⚠⚠ 第二十八笔：原来这里是「One direction rests on 3 trajectories out
              of 48」—— 两个数都是手抄的。源在 vector_roles.json 的
              necessity.in_sample_circular.L14.<方向>：
              n_traj_within_which_rho_is_defined 与 n_traj_pooled。
              注意这两个**不是同一件事**：分母 48 是池化的全部轨迹，
              分子 3 是「轨迹内 rho 有定义」的条数（常数轨迹上 Spearman
              无定义，只从逐轨迹 rho 里剔除，pooled 仍用上它的每一步 ——
              产物自己在 per_traj_denominator_note 里写了这件事）。
              而 rho_within_traj 0.0489 说明这 3 条上的效应也确实很小。 */}
          {roles ? (() => {
            // ⚠ 只看第一个层（L14 / L20 的 n 相同，取哪个都一样），
            //   一次遍历找分子**最小**的那个方向。
            //   不点名某个方向 —— 手写名字在这里同样是「猜哪个是它」，
            //   而「最小」是能从产物算出来的。
            const byLayer = Object.values(
              roles.necessity?.in_sample_circular ?? {})[0] ?? {};
            let dir: string | null = null;
            let best: { n: number; pool: number; rho: number } | null = null;
            for (const [d, r] of Object.entries(byLayer)) {
              const n = r.n_traj_within_which_rho_is_defined;
              const pool = r.n_traj_pooled;
              if (n == null || pool == null) continue;
              if (best === null || n < best.n) {
                best = { n, pool, rho: r.rho_within_traj ?? NaN };
                dir = d;
              }
            }
            if (!best || dir === null) return null;
            return (
              <>
                The thinnest one,{" "}
                <span className="font-mono" data-thin-dir={dir}
                      data-thin-n={best.n} data-thin-pool={best.pool}
                      data-thin-rho={best.rho}>
                  {dir}
                </span>
                , rests on{" "}
                <span className="font-mono">{best.n}</span> trajectories out of{" "}
                <span className="font-mono">{best.pool}</span>{" "}
                {best.n === best.pool
                  ? "(all of them)."
                  : `(the other ${best.pool - best.n} have no within-trajectory rho defined — the statistic is undefined on a constant trace, and pooled still uses their steps).`}
              </>
            );
          })() : null}{" "}
          The non-circular
          (held-out) half of that evidence is not reproduced here either.
          Numbers like these render as convincing bars and mean nothing,
          so the panel omits them and tells you instead.
        </p>
        <p className="text-[10px] text-gray-600 leading-relaxed mt-1.5">
          That artifact also records one check as{" "}
          <span className="font-mono" data-anchor-status={roles?.unmeasured?.lm_head_anchor?.status ?? ""}>
            {roles?.unmeasured?.lm_head_anchor?.status ?? "unavailable"}
          </span>
          . The
          weights are in this repository under{" "}
          <span className="font-mono">datasets/models/Qwen3-1.7B/</span>, and
          the step was run independently afterwards:{" "}
          {/* ⚠⚠ 第二十八笔：原来这里是
              「argmax reproduces the recorded token on 99.5% of sampled steps,
                max logit error 0.125 against the stored top-64」——
              99.5% **既不是产物值也不对**：anchor.all_steps.rate = 0.9974，
              而口径是「全部 1536 步」，不是「sampled steps」。
              产物（vector_roles.json 的 unmeasured.lm_head_anchor.
              pre_existing_measurement）**已经把正确的话整句写好了**，
              两个口径分开、末尾还自带「引用而非复现」的说明
              ⇒ 这里直接渲染那句话，不重新叙述它。
              读不到就印 unavailable，而不是退回一个手抄的百分数。 */}
          {roles?.unmeasured?.lm_head_anchor?.pre_existing_measurement
            ? (
              <span data-anchor-note>
                {roles.unmeasured.lm_head_anchor.pre_existing_measurement}
              </span>
            )
            : <span data-anchor-note="">unavailable</span>}
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

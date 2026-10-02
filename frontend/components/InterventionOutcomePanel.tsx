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

const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

export default function InterventionOutcomePanel() {
  const [cot, setCot] = useState<CotTexts | null>(null);
  const [ans, setAns] = useState<AnswerReadout | null>(null);
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
    ])
      .then(([c, a]: [CotTexts, AnswerReadout]) => {
        if (alive) { setCot(c); setAns(a); }
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
        all. Net change in correct answers: <b>0</b>. Steering moved
        things; it did not make them better.
      </p>

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

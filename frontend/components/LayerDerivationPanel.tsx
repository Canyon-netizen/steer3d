"use client";

/**
 * Per-layer derivation chain — "how did the hidden states become this
 * token?"
 *
 * The 3-D pane shows where the residual stream travelled. It does not
 * show what the model was *deciding* at each depth. This panel answers
 * the other half: for one step, apply the last layer's readout (RMSNorm
 * + unembedding) to layer 0, 1, ... 27 in turn, and record which token
 * each layer would emit on its own.
 *
 * Data: `logit_lens.json`, the same artifact the 2-D page renders. Each
 * trajectory carries a `window` (the last 32 steps) and per-step
 * `per_layer.{argmax,p_argmax,p_final,margin,correct}`. `argmax[l]` is
 * the token id layer l would emit; `p_final[l]` is how much probability
 * that layer already gives the token the model actually chose.
 *
 * Two things this panel refuses to do:
 *
 *  1. Invent a chain for a step it has no data for. The artifact only
 *     covers the last 32 steps of each recording, while replay starts at
 *     step 0. So for most of the playback there is genuinely nothing to
 *     show, and the panel says which steps *do* have data instead of
 *     drawing an empty frame that reads like "no layers agreed".
 *
 *  2. Present the readout as if it were the model's forward pass. It is
 *     not: it is a probe that applies the final decoder to intermediate
 *     states. The shape is informative, the causality is not.
 *
 * The anchor matters here. `anchor_ok` is whether the last layer's
 * readout reproduced the token the model actually emitted. The artifact
 * was re-derived independently from the npz files: 1532/1536 steps
 * reproduce it, and all 4 misses are steps where the model's own top1 and
 * top2 were exactly tied in the stored float16 — nothing was dropped.
 * The reconstruction error is about 0.08 logits on median, 0.125 at
 * worst, which is why the undecidable steps are counted separately rather
 * than quietly averaged in.
 *
 * Note on layer 27: it is stored *post*-norm, so it is not normalised
 * again here. Re-normalising it drops the hit rate from 98.8% to 76.9% —
 * the artifact's choice is the correct one.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useApp } from "@/lib/store";

type LensStep = {
  t: number;
  final_id: number;
  tok: string;
  real_margin: number;
  decidable: boolean;
  first_layer_correct: number | null;
  n_layers_correct: number;
  monotone: boolean;
  per_layer: {
    argmax: number[];
    p_argmax: number[];
    p_final: number[];
    margin: number[];
    correct: boolean[];
  };
  anchor_ok: boolean;
  anchor_logit_err: number;
};

type LensTrajectory = {
  id: string;
  problem: string;
  mode: string;
  T: number;
  window: [number, number];
  steps: LensStep[];
};

type LensArtifact = {
  anchor?: {
    decidable_steps?: { pass?: number; total?: number };
    all_steps?: { pass?: number; total?: number };
    max_logit_error_vs_stored_topk?: number;
  };
  // 第二十七笔新增：层数**不写死**，从这两处取（见下面 N_LAYERS 的说明）。
  model?: { n_layers?: number };
  per_layer_mean_p_final?: { values?: number[] };
  trajectories?: LensTrajectory[];
};

const W = 328;
const H = 132;
const PAD = { top: 12, right: 10, bottom: 20, left: 10 };
// ⚠⚠ 第二十七笔：`const N_LAYERS = 28;` 已从模块级删掉。
//   它是**这个组件自己刚取回来的那份产物**里的一个字段
//   （logit_lens.json 的 model.n_layers = 28，另有一条独立证据
//   per_layer_mean_p_final.values 正好 28 项）——
//   也就是说，这个面板**手里拿着真值，却在旁边写了一个字面量**。
//   而它决定的东西很关键：横轴刻度 `L0 … L{N_LAYERS-1}`、每层柱宽
//   `plotW / N_LAYERS`、以及那句「layers 0–27 were read」的**可见文字**。
//   判据侧 verify_derivation.mjs 同时把 28 抄了四处（bars.length === 28 ×3
//   与一处守卫）⇒ 与第十三/二十六笔同形：两边一起错，判据自己不会红。
//   ⇒ 现在从产物派生；取不到就明说取不到（见下面那句 fallback）。

export default function LayerDerivationPanel() {
  const currentTrajectory = useApp((s) => s.currentTrajectory);
  const focusedStep = useApp((s) => s.focusedStep);
  const setFocusedStep = useApp((s) => s.setFocusedStep);
  const latest = useApp((s) => s.latest);

  const [lens, setLens] = useState<LensArtifact | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Loaded once. The artifact is ~1.5 MB of per-step per-layer data for
  // 48 recordings; re-fetching it on every trajectory change would be the
  // difference between an instant panel and a visible stall.
  useEffect(() => {
    let alive = true;
    fetch("/latent/data/logit_lens.json")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((j: LensArtifact) => {
        if (alive) setLens(j);
      })
      .catch((e) => {
        if (alive) setLoadError(String(e.message || e));
      });
    return () => {
      alive = false;
    };
  }, []);

  const traj = useMemo(() => {
    if (!lens?.trajectories || !currentTrajectory) return null;
    return lens.trajectories.find((t) => t.id === currentTrajectory) ?? null;
  }, [lens, currentTrajectory]);

  // Follow the newest frame unless the reader picked a step.
  const stepId = focusedStep ?? latest?.step_id ?? null;

  // A step number only indexes a step *within one record*. After switching
  // records, a remembered step usually points into the previous trace, so
  // the panel sat on "out-of-window" indefinitely: the slider's `value` prop
  // already clamps to win[0], so the reader saw the handle on a step the
  // panel refused to draw, and nothing recovered until they nudged the
  // slider by hand. That was F9 of verify_derivation — a real defect.
  //
  // Drop the pick only when it is **meaningless in the new record** — i.e.
  // outside its window. A step that happens to fall inside the new window is
  // a legitimate pick for it and has to survive. Clearing unconditionally
  // opens a race: a reader (or a test) can choose a step in the new record
  // in the same tick as the switch, and the cleanup would throw that away,
  // dropping the panel back to whatever frame arrived next. That is exactly
  // how F9 became flaky rather than fixed.
  //
  // Deliberately NOT done by falling back to win[0] when out of window: that
  // would draw a chain for a step the model has not reached yet, which is
  // the dishonesty F3/F3b exist to prevent. "Out of window, and nothing
  // drawn" stays the honest answer for early playback.
  const trajId = traj?.id ?? null;
  const prevTrajId = useRef<string | null>(null);
  useEffect(() => {
    if (prevTrajId.current !== null && prevTrajId.current !== trajId) {
      const w = traj?.window ?? null;
      const s = focusedStep;               // 同一次渲染里的值，切换那一刻的 pick
      if (s != null && (!w || s < w[0] || s >= w[1])) setFocusedStep(null);
    }
    prevTrajId.current = trajId;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trajId, traj, setFocusedStep]);

  const step = useMemo(() => {
    if (!traj || stepId == null) return null;
    return traj.steps.find((s) => s.t === stepId) ?? null;
  }, [traj, stepId]);

  const win = traj?.window ?? null;

  const header = (
    <div className="flex items-baseline justify-between">
      <span className="text-[10px] text-gray-500 uppercase tracking-wider">
        Per-layer derivation
      </span>
      {traj && win && (
        <span className="text-[9px] text-gray-600 font-mono">
          steps {win[0]}–{win[1] - 1}
        </span>
      )}
    </div>
  );

  // Step picker. Without it the panel is only usable if you sit and wait
  // for playback to reach the window -- measured at 8 steps/s, that is
  // ~2 minutes for a 1024-step trace, and the shortest recording has T=265
  // so the same wait is 30s there. The window is only 32 steps wide, so
  // every one of them is directly reachable and there is no reason to make
  // the reader sit through the trajectory to get there.
  const stepPicker = (() => {
    if (!traj || !win) return null;
    return (
      <div className="flex items-center gap-2 mt-1.5">
        <input
          type="range"
          min={win[0]}
          max={win[1] - 1}
          step={1}
          value={stepId != null && stepId >= win[0] && stepId < win[1] ? stepId : win[0]}
          onChange={(e) => setFocusedStep(parseInt(e.target.value, 10))}
          className="flex-1"
          data-deriv-step
        />
        <span className="text-[9px] text-gray-500 font-mono whitespace-nowrap">
          {stepId != null && stepId >= win[0] && stepId < win[1] ? stepId : win[0]}
          /{win[1] - 1}
        </span>
        {focusedStep != null && (
          <button
            onClick={() => setFocusedStep(null)}
            className="text-[9px] text-gray-500 hover:text-gray-300 border border-border rounded px-1"
            data-deriv-follow
            title="Follow the newest frame again"
          >
            live
          </button>
        )}
      </div>
    );
  })();

  if (loadError) {
    return (
      <div className="rounded bg-bg/40 border border-border p-3" data-derivation="error">
        {header}
        <p className="text-[10px] text-red-400 leading-relaxed mt-1">
          logit_lens.json unavailable: {loadError}
        </p>
      </div>
    );
  }

  if (!lens) {
    return (
      <div className="rounded bg-bg/40 border border-border p-3" data-derivation="loading">
        {header}
        <p className="text-[10px] text-gray-500 leading-relaxed mt-1">
          Loading the per-layer readout…
        </p>
      </div>
    );
  }

  if (!currentTrajectory) {
    return (
      <div className="rounded bg-bg/40 border border-border p-3" data-derivation="no-traj">
        {header}
        {stepPicker}
        <p className="text-[10px] text-gray-500 leading-relaxed mt-1">
          Pick a recording to see how each layer builds up to its tokens.
        </p>
      </div>
    );
  }

  // ⚠ 第二十七笔：层数由产物给出。两条独立证据取其一：
  //   model.n_layers 是模型自述的层数；per_layer_mean_p_final.values 是
  //   逐层均值的实际长度。两者不一致本身就是一件该看见的事，
  //   所以下面把它**暴露成可核的属性**，而不是内部悄悄取其一。
  // ⚠ 取不到时给 0 而不是 28：那会让 `plotW / N_LAYERS` = Infinity、
  //   刻度印 `L-1` —— 一个**看起来正常**的错误。
  //   早退分支已经保证 lens 非 null，所以这里不会是「还没取到」。
  const N_LAYERS = lens.model?.n_layers
    ?? lens.per_layer_mean_p_final?.values?.length
    ?? 0;

  if (!traj) {
    return (
      <div className="rounded bg-bg/40 border border-border p-3" data-derivation="no-lens">
        {header}
        {stepPicker}
        <p className="text-[10px] text-amber-400/90 leading-relaxed mt-1">
          This recording has no per-layer readout. The artifact covers{" "}
          {(lens.trajectories?.length ?? 0).toLocaleString()} recordings; this one
          ({" "}
          <span className="font-mono">{currentTrajectory}</span>) is not among
          them, so nothing is drawn.
        </p>
      </div>
    );
  }

  // In the window but this particular step has no per-layer data.
  if (win && stepId != null && stepId >= win[0] && stepId < win[1] && !step) {
    return (
      <div className="rounded bg-bg/40 border border-border p-3" data-derivation="no-step">
        {header}
        {stepPicker}
        <p className="text-[10px] text-amber-400/90 leading-relaxed mt-1">
          Step {stepId} is inside the readout window but carries no per-layer
          entry. Nothing is drawn rather than showing an empty chain.
        </p>
      </div>
    );
  }

  if (!step) {
    return (
      <div className="rounded bg-bg/40 border border-border p-3" data-derivation="out-of-window" data-traj={trajId ?? ""} data-step-id={stepId ?? ""} data-n-layers={N_LAYERS}>
        {header}
        {stepPicker}
        <p className="text-[10px] text-gray-500 leading-relaxed mt-1">
          {stepId == null ? (
            <>Waiting for the first frame…</>
          ) : (
            <>
              Step {stepId} is outside the readout window{" "}
              {win ? (
                <span className="font-mono">
                  ({win[0]}–{win[1] - 1})
                </span>
              ) : null}
              . Only the last {traj.steps.length} steps were probed — layers
              0–{N_LAYERS - 1} were read for those steps only. Playback
              starts at step 0, so this panel fills in as the trace reaches
              the window.
            </>
          )}
        </p>
      </div>
    );
  }

  const pl = step.per_layer;
  const first = step.first_layer_correct;
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const bw = plotW / N_LAYERS;
  const bx = (l: number) => PAD.left + l * bw;

  // Bar height = how much probability this layer already puts on the
  // token the model finally chose. A chain that stays at zero and then
  // jumps is the interesting shape: the decision is made late, and the
  // layers below it were busy saying something else.
  const bars = pl.p_final.map((p, l) => {
    const hgt = Math.max(1.5, Math.min(p, 1) * plotH);
    const ok = pl.correct[l];
    return { l, p, ok, hgt, x: bx(l), w: Math.max(bw - 1.2, 1) };
  });

  const flx = first != null && first >= 0 ? bx(first) + bw / 2 : null;

  return (
    <div className="rounded bg-bg/40 border border-border p-3" data-derivation="ready" data-traj={trajId ?? ""} data-step-id={stepId ?? ""} data-n-layers={N_LAYERS}>
      {header}
      {stepPicker}

      <div className="text-[10.5px] text-gray-300 leading-snug mt-1 mb-1">
        Step <span className="font-mono text-gray-400">{step.t}</span> — the
        model picked{" "}
        <span className="font-mono text-amber-300">{step.tok || `#${step.final_id}`}</span>{" "}
        {first != null && first >= 0 ? (
          <>
            , and layer{" "}
            <span className="text-emerald-300 font-semibold">{first}</span> is
            the first one that says it.
          </>
        ) : (
          <span className="text-red-300">— no layer out of 28 ever said it.</span>
        )}
      </div>

      <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="overflow-visible">
        {bars.map((b) => (
          <rect
            key={b.l}
            x={b.x.toFixed(2)}
            y={(PAD.top + plotH - b.hgt).toFixed(2)}
            width={b.w.toFixed(2)}
            height={b.hgt.toFixed(2)}
            fill={b.ok ? "#34d399" : "#334155"}
            opacity={b.ok ? 0.95 : 0.8}
            data-layer={b.l}
            data-ok={b.ok ? "1" : "0"}
            // Two independent readouts of the same bar, on purpose.
            // `data-pfinal` is the number the panel was handed;
            // `data-drawn` is derived from the height actually rendered.
            // A criterion that only reads the first cannot tell a correct
            // bar from a constant-height one -- and the height is what the
            // reader sees. Verified by mutation D1, which made every bar
            // half the plot and left a 14/14 green criterion untouched.
            data-pfinal={b.p}
            data-drawn={(b.hgt / plotH).toFixed(4)}
          />
        ))}

        {flx != null && (
          <line
            x1={flx}
            y1={PAD.top - 4}
            x2={flx}
            y2={PAD.top + plotH}
            stroke="#fbbf24"
            strokeWidth={1}
            strokeDasharray="2 2"
          />
        )}

        <text x={PAD.left} y={8} fontSize={7} fill="#6b7280">
          L0
        </text>
        <text x={W - PAD.right} y={8} fontSize={7} fill="#6b7280" textAnchor="end">
          L{N_LAYERS - 1}
        </text>
        <text x={PAD.left} y={H - 5} fontSize={7} fill="#6b7280">
          0
        </text>
        <text x={W - PAD.right} y={H - 5} fontSize={7} fill="#6b7280" textAnchor="end">
          p(final token)
        </text>
      </svg>

      <div className="flex items-center justify-between text-[9px] text-gray-600 font-mono mt-0.5">
        <span title="layers that already emit the chosen token">
          {step.n_layers_correct}/{N_LAYERS} layers agree
        </span>
        <span title="top1 − top2 at the final layer">
          margin {step.real_margin?.toFixed?.(2) ?? "—"}
        </span>
      </div>

      <p className="text-[10px] text-gray-500 leading-relaxed mt-1">
        Bar height is how much probability that layer already gives the
        token the model went on to emit. Green bars are layers whose own
        argmax is already that token; grey ones are still saying something
        else. Dashed line marks the first agreeing layer.
        {!step.anchor_ok && (
          <span className="text-red-300">
            {" "}
            This step&apos;s anchor did not hold (reconstruction error{" "}
            {step.anchor_logit_err?.toFixed?.(3)} logits), so treat the shape
            with care.
          </span>
        )}
      </p>
      <p className="text-[10px] text-gray-600 leading-relaxed mt-1">
        This is a probe, not a forward pass: the final layer&apos;s decoder is
        applied to intermediate states. It shows what each depth was already
        committed to, not what caused the token.
      </p>
    </div>
  );
}

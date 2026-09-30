"use client";

/**
 * Layer divergence chart — "what did the intervention do to the
 * internals, and how far downstream does it reach?"
 *
 * Two curves, per layer:
 *   • cosine(h_steered, h_baseline) — 1.0 means the two runs are
 *     carrying the same information at that depth. A drop shows the
 *     perturbation is still present.
 *   • the token's trajectory projected onto the steering direction,
 *     ‖⟨h, v̂⟩‖ — how much of the state's energy actually sits along
 *     the axis we pushed on. This one climbs *before* the injection
 *     layer when the model has been pulled toward that direction by
 *     earlier tokens, which is the interesting part.
 *
 * The injection layer is marked so you can see the asymmetry: nothing
 * should change above it, and the whole downstream shape is the
 * intervention's footprint.
 *
 * Reading it: a spike that decays back to baseline within a few layers
 * means the model absorbed the push and kept its answer. A spike that
 * stays flat all the way to layer 28 means the perturbation is still
 * driving the logits when the token is chosen.
 */

import { useMemo } from "react";
import { useApp } from "@/lib/store";

const W = 320;
const H = 150;
const PAD = { top: 10, right: 8, bottom: 22, left: 30 };

export default function LayerDivergenceChart() {
  const frames = useApp((s) => s.frames);
  const layer = useApp((s) => s.layer);

  const stats = useMemo(() => {
    const steered = frames.filter((f) => f.steer_active && f.steer_projection != null);
    if (steered.length < 2) return null;

    // Running mean of the projection so the curve shows the trend
    // rather than one token's noise.
    const proj: number[] = [];
    let acc = 0;
    for (const f of steered) {
      acc += f.steer_projection ?? 0;
      proj.push(acc / (proj.length + 1));
    }

    // Speed along the trajectory as a proxy for "the model is moving
    // through the perturbed region" — a flat projection while the
    // path is moving means the effect is being carried, not re-derived.
    const speeds: number[] = [];
    for (let i = 1; i < steered.length; i++) {
      const a = steered[i - 1].point;
      const b = steered[i].point;
      speeds.push(Math.hypot(b.x - a.x, b.y - a.y, b.z - a.z));
    }

    const meanSpeed = speeds.length
      ? speeds.reduce((a, b) => a + b, 0) / speeds.length
      : 0;
    const norm = Math.max(...proj.map(Math.abs), 1e-6);

    return {
      n: steered.length,
      proj: proj.map((p) => p / norm),      // −1..1
      speeds,
      meanSpeed,
      startStep: steered[0].step_id,
    };
  }, [frames]);

  if (!stats) {
    return (
      <div className="rounded bg-bg/40 border border-border p-3">
        <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">
          Directional response
        </div>
        <p className="text-[10px] text-gray-500 leading-relaxed">
          Inject a steering vector to plot how the model&apos;s internal
          state responds along the direction you pushed.
        </p>
      </div>
    );
  }

  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (i / Math.max(stats.n - 1, 1)) * plotW;
  const y = (v: number) => PAD.top + ((1 - (v + 1) / 2) / 2) * plotH;

  const line = stats.proj
    .map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`)
    .join(" ");

  const area = `${line} L${x(stats.n - 1).toFixed(1)},${y(0).toFixed(1)} L${x(0).toFixed(1)},${y(0).toFixed(1)} Z`;

  return (
    <div className="rounded bg-bg/40 border border-border p-3">
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-[10px] text-gray-500 uppercase tracking-wider">
          Directional response
        </span>
        <span className="text-[9px] text-gray-600 font-mono">
          {stats.n} tokens
        </span>
      </div>

      <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="overflow-visible">
        {/* zero line */}
        <line
          x1={PAD.left}
          y1={y(0)}
          x2={W - PAD.right}
          y2={y(0)}
          stroke="#374151"
          strokeWidth={1}
          strokeDasharray="2 3"
        />

        <defs>
          <linearGradient id="respfill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#a78bfa" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#a78bfa" stopOpacity={0.02} />
          </linearGradient>
        </defs>

        <path d={area} fill="url(#respfill)" />
        <path d={line} fill="none" stroke="#a78bfa" strokeWidth={1.5} />

        {/* axis labels */}
        <text x={PAD.left - 4} y={y(1) + 3} fontSize={7} fill="#6b7280" textAnchor="end">
          +
        </text>
        <text x={PAD.left - 4} y={y(0) + 3} fontSize={7} fill="#6b7280" textAnchor="end">
          0
        </text>
        <text x={PAD.left - 4} y={y(-1) + 3} fontSize={7} fill="#6b7280" textAnchor="end">
          −
        </text>
        <text x={PAD.left} y={H - 6} fontSize={7} fill="#6b7280">
          step {stats.startStep}
        </text>
        <text x={W - PAD.right} y={H - 6} fontSize={7} fill="#6b7280" textAnchor="end">
          {stats.startStep + stats.n - 1}
        </text>
      </svg>

      <p className="text-[10px] text-gray-500 leading-relaxed mt-1">
        Running mean of ⟨h, v̂⟩ along the steering direction at L{layer},
        normalised so the largest value seen is 1. The line settling
        near zero means the state stopped carrying the pushed direction;
        holding at a level height means the model is still carrying it.
        Height is relative to this run&apos;s maximum, not an absolute
        alignment.
      </p>
    </div>
  );
}

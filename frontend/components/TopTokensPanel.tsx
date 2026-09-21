"use client";

/**
 * Side panel showing the latest frame's scalar metrics + flags.
 * Lets the user see at a glance what the model is "thinking
 * about" — entropy (uncertainty), perplexity (top-1 confidence),
 * and whether this step is a self-check / revisit moment.
 *
 * v0.2 note: previous versions displayed `top_tokens` (next-token
 * distribution), which required shipping the full logits tensor
 * over WebSocket. We dropped that to keep the wire protocol
 * tiny; this panel now focuses on the metrics that *are* in
 * Frame. If you want top-K back, add a `top_tokens: List[{token,
 * prob}]` field in `protocol.Frame` and re-extend this panel.
 */

import { useApp } from "@/lib/store";

export default function TopTokensPanel() {
  const latest = useApp((s) => s.latest);

  if (!latest) {
    return (
      <div className="p-4 rounded-lg bg-panel border border-border text-sm text-gray-500">
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-2">
          Current Step
        </h2>
        waiting for stream...
      </div>
    );
  }

  const entropy = latest.entropy ?? null;
  const perplexity = latest.perplexity ?? null;

  return (
    <div className="flex flex-col gap-3 p-4 rounded-lg bg-panel border border-border">
      <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
        Current Step
      </h2>

      <div className="flex items-baseline gap-2">
        <span className="text-xs text-gray-500">token</span>
        <span className="font-mono text-lg text-yellow-300 truncate">
          {latest.token || "·"}
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
        <dt className="text-gray-500">entropy</dt>
        <dd className="font-mono text-gray-200 text-right">
          {entropy !== null ? entropy.toFixed(3) : "—"}
        </dd>

        <dt className="text-gray-500">perplexity</dt>
        <dd className="font-mono text-gray-200 text-right">
          {perplexity !== null ? perplexity.toFixed(2) : "—"}
        </dd>

        <dt className="text-gray-500">step_id</dt>
        <dd className="font-mono text-gray-200 text-right">{latest.step_id}</dd>

        <dt className="text-gray-500">token_id</dt>
        <dd className="font-mono text-gray-200 text-right">{latest.token_id}</dd>
      </dl>

      <div className="flex flex-wrap gap-1.5 pt-1 border-t border-border">
        {latest.is_self_check && (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-orange-500/15 text-orange-300 border border-orange-500/40">
            self-check
          </span>
        )}
        {latest.is_revisit && (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-500/15 text-purple-300 border border-purple-500/40">
            revisit
          </span>
        )}
        {!latest.is_self_check && !latest.is_revisit && (
          <span className="px-2 py-0.5 rounded-full text-[10px] text-gray-500">
            flowing
          </span>
        )}
      </div>

      <p className="text-[10px] text-gray-600 pt-2 leading-relaxed">
        Tip: 想看 top-K 下个候选 token?给{" "}
        <code className="text-orange-300">Frame</code> 加{" "}
        <code className="text-orange-300">top_tokens: List[TokenProb]</code> 字段（见
        <code className="text-orange-300">protocol.py</code>）。
      </p>
    </div>
  );
}
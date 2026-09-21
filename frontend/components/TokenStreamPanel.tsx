"use client";

/**
 * Side panel that shows the running text of the model's reasoning
 * trace, with self-check / revisit tokens highlighted.
 */

import { useApp } from "@/lib/store";

export default function TokenStreamPanel() {
  const frames = useApp((s) => s.frames);
  const fullText = useApp((s) => s.fullText);

  return (
    <div className="flex flex-col gap-3 p-4 rounded-lg bg-panel border border-border flex-1 min-h-0">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
          Reasoning Trace
        </h2>
        <span className="text-xs text-gray-500 font-mono">
          {frames.length} tokens
        </span>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto rounded bg-bg/50 border border-border p-3 font-mono text-sm leading-relaxed text-gray-200">
        {frames.length === 0 ? (
          <span className="text-gray-500">awaiting first frame...</span>
        ) : (
          frames.map((f) => {
            const c = f.is_self_check
              ? "bg-orange-500/20 text-orange-300 rounded px-0.5"
              : f.is_revisit
              ? "bg-purple-500/20 text-purple-300 rounded px-0.5"
              : "";
            return (
              <span key={f.step_id} className={c}>
                {f.token || "·"}
              </span>
            );
          })
        )}
      </div>
    </div>
  );
}
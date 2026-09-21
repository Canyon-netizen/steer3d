"use client";

/**
 * Control panel for the dynamic CoT visualizer.
 *  * Prompt input
 *  * Layer dropdown
 *  * Speed control + pause / resume
 *  * Reset button
 */

import { useApp } from "@/lib/store";
import type { ControlMessage } from "@/lib/frame-types";
import { useEffect, useState } from "react";

type Props = {
  sendControl: (msg: ControlMessage) => void;
};

const LAYERS = [4, 8, 12, 14, 16, 20, 24, 28, 32];

export default function ControlPanel({ sendControl }: Props) {
  const layer = useApp((s) => s.layer);
  const speed = useApp((s) => s.speed);
  const paused = useApp((s) => s.paused);
  const setLayer = useApp((s) => s.setLayer);
  const setSpeed = useApp((s) => s.setSpeed);
  const setPaused = useApp((s) => s.setPaused);
  const latest = useApp((s) => s.latest);

  const [prompt, setPrompt] = useState("Why is the sky blue?");
  const [localPrompt, setLocalPrompt] = useState(prompt);

  // Keep local prompt in sync with the store so external resets work.
  useEffect(() => setLocalPrompt(prompt), [prompt]);

  const onStart = () => {
    setPaused(false);
    sendControl({
      kind: "start",
      payload: { prompt: localPrompt, layer },
    });
  };

  const onPauseToggle = () => {
    const next = !paused;
    setPaused(next);
    sendControl({ kind: next ? "pause" : "resume" });
  };

  const onReset = () => {
    setPaused(false);
    sendControl({ kind: "reset" });
  };

  const onLayerChange = (l: number) => {
    setLayer(l);
    sendControl({ kind: "set_layer", payload: { value: l } });
  };

  const onSpeedChange = (s: number) => {
    setSpeed(s);
    sendControl({ kind: "set_speed", payload: { value: s } });
  };

  return (
    <div className="flex flex-col gap-4 p-4 rounded-lg bg-panel border border-border">
      <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
        Controls
      </h2>

      {/* Prompt input */}
      <div className="flex flex-col gap-1">
        <label className="text-xs text-gray-400">Prompt</label>
        <textarea
          className="px-3 py-2 rounded bg-bg border border-border text-sm text-gray-100 focus:outline-none focus:border-baseline resize-none"
          rows={3}
          value={localPrompt}
          onChange={(e) => setLocalPrompt(e.target.value)}
        />
      </div>

      <div className="flex gap-2">
        <button
          onClick={onStart}
          className="flex-1 px-3 py-2 rounded bg-baseline text-bg text-sm font-semibold hover:opacity-90"
        >
          ▶ Run
        </button>
        <button
          onClick={onPauseToggle}
          className={`px-3 py-2 rounded border text-sm ${
            paused
              ? "border-yellow-400 text-yellow-300"
              : "border-border text-gray-300"
          }`}
        >
          {paused ? "▶ resume" : "⏸ pause"}
        </button>
        <button
          onClick={onReset}
          className="px-3 py-2 rounded border border-border text-sm text-gray-300 hover:border-accent"
        >
          ⟲ reset
        </button>
      </div>

      {/* Layer selector */}
      <div className="flex flex-col gap-1">
        <label className="text-xs text-gray-400">Layer (residual stream)</label>
        <select
          className="px-3 py-2 rounded bg-bg border border-border text-sm text-gray-100"
          value={layer}
          onChange={(e) => onLayerChange(parseInt(e.target.value, 10))}
        >
          {LAYERS.map((l) => (
            <option key={l} value={l}>
              layer {l}
            </option>
          ))}
        </select>
      </div>

      {/* Speed */}
      <div className="flex flex-col gap-1">
        <div className="flex items-baseline justify-between">
          <label className="text-xs text-gray-400">Playback speed</label>
          <span className="text-xs text-gray-300 font-mono">{speed.toFixed(2)}x</span>
        </div>
        <input
          type="range"
          min={0.25}
          max={4}
          step={0.25}
          value={speed}
          onChange={(e) => onSpeedChange(parseFloat(e.target.value))}
          className="w-full"
        />
      </div>

      {/* Status line */}
      <div className="text-xs text-gray-500 font-mono leading-relaxed border-t border-border pt-3">
        {latest ? (
          <>
            step <span className="text-gray-300">{latest.step_id}</span> ·
            {" "}
            <span className="text-yellow-300">{latest.token || "·"}</span>
            {latest.is_self_check && (
              <span className="ml-2 px-1.5 py-0.5 rounded bg-orange-500/20 text-orange-300">
                self-check
              </span>
            )}
            {latest.is_revisit && (
              <span className="ml-2 px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300">
                revisit
              </span>
            )}
            <br />
            ppl{" "}
            <span className="text-gray-300">
              {latest.perplexity != null ? latest.perplexity.toFixed(2) : "—"}
            </span>{" "}
            · entropy{" "}
            <span className="text-gray-300">
              {latest.entropy != null ? latest.entropy.toFixed(2) : "—"}
            </span>
          </>
        ) : (
          "waiting for stream..."
        )}
      </div>
    </div>
  );
}
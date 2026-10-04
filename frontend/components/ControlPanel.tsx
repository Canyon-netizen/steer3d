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

// Fallback only, used until the backend's `ready` names the real set. It
// used to be the *only* list, and it was wrong: the archived capture covers
// L4/L12/L20/L26, so this offered eight layers with no data and left L26 --
// the deepest layer, where control and steered trajectories separate most --
// unreachable except by picking a neighbouring value and letting the server
// snap to it.
const FALLBACK_LAYERS = [4, 8, 12, 14, 16, 20, 24, 28, 32];

export default function ControlPanel({ sendControl }: Props) {
  const layer = useApp((s) => s.layer);
  const availableLayers = useApp((s) => s.availableLayers);
  const speed = useApp((s) => s.speed);
  const paused = useApp((s) => s.paused);
  const setLayer = useApp((s) => s.setLayer);
  const setSpeed = useApp((s) => s.setSpeed);
  const setPaused = useApp((s) => s.setPaused);
  const latest = useApp((s) => s.latest);
  const setCurrentTrajectory = useApp((s) => s.setCurrentTrajectory);

  const layers = availableLayers.length > 0 ? availableLayers : FALLBACK_LAYERS;

  // What can actually be replayed. The replay runner matches the prompt
  // against recorded ids and, when nothing matches, silently shows the first
  // recording -- so a free-text box let someone type "Why is the sky blue?"
  // and watch 1983_I_1's real trajectory go by while the box still said
  // something else. When the backend names its recordings, offer only those.
  const trajectories = useApp((s) => s.trajectories);
  const [prompt, setPrompt] = useState("Why is the sky blue?");
  const [localPrompt, setLocalPrompt] = useState(prompt);
  const pickList = trajectories.length > 0;
  // Open on the first recording rather than on a prompt that does not exist.
  const effectivePrompt = pickList
    ? (trajectories.some((t) => t.id === localPrompt) ? localPrompt : trajectories[0].id)
    : localPrompt;

  // Keep local prompt in sync with the store so external resets work.
  useEffect(() => setLocalPrompt(prompt), [prompt]);

  // Publish which recording is on screen. Frames carry no trajectory id of
  // their own, so without this the per-layer derivation panel cannot tell
  // which logit-lens entry belongs to the stream it is drawing next to --
  // it would look up a trajectory and either find nothing or, worse, find
  // a different one and render it confidently.
  useEffect(() => {
    setCurrentTrajectory(pickList ? effectivePrompt : null);
  }, [pickList, effectivePrompt, setCurrentTrajectory]);

  const onStart = () => {
    setPaused(false);
    sendControl({
      kind: "start",
      payload: { prompt: effectivePrompt, layer },
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

      {/* Prompt input. A picker when the backend names its recordings, a free
          text box only when the runner really does accept any prompt. */}
      <div className="flex flex-col gap-1">
        <label className="text-xs text-gray-400">
          {pickList ? "Recording" : "Prompt"}
        </label>
        {pickList ? (
          <>
            <select
              className="px-3 py-2 rounded bg-bg border border-border text-sm text-gray-100"
              value={effectivePrompt}
              onChange={(e) => {
                setLocalPrompt(e.target.value);
                setPrompt(e.target.value);
              }}
            >
              {trajectories.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                  {t.mode ? ` · ${t.mode}` : ""}
                </option>
              ))}
            </select>
            {/* Say where the tokens come from. A picker alone still leaves the
                reader guessing whether the stream is generated or replayed. */}
            {/* ⚠ 第三十一笔：探针去掉「写死的 8 面板名单」之后，这段
                被算成「祖先链为空」。但**它其实被读过** ——
                verify_picker.mjs 里就写着 "Replaying a recorded"，
                只是那是**全文 includes**，不是按标记读。
                ⇒ 「祖先链为空」不等于「没人读」，这两件事必须分开说。
                ⇒ 给它一个标记，让「按标记读」这条路也通。 */}
            <p className="text-[10px] text-gray-500 leading-relaxed"
               data-replay-note="true">
              Replaying a recorded Qwen3-1.7B trajectory — the
              hidden states, tokens and per-step entropy are the ones captured on
              the cluster, not generated here.
            </p>
          </>
        ) : (
          <textarea
            className="px-3 py-2 rounded bg-bg border border-border text-sm text-gray-100 focus:outline-none focus:border-baseline resize-none"
            rows={3}
            value={localPrompt}
            onChange={(e) => setLocalPrompt(e.target.value)}
          />
        )}
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
          {layers.map((l) => (
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
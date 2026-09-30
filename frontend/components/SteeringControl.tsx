"use client";

/**
 * Steering control — injects a semantic direction into the residual
 * stream and shows what it did.
 *
 * The direction list is not hardcoded here: the backend sends a
 * catalog of what it can actually inject, each with the evidence
 * behind it (how many tokens backed the extraction, what Cohen's d
 * the direction achieves). Showing that next to the slider is the
 * point — a steering vector is only as trustworthy as the contrast
 * that produced it, and a slider alone would hide that.
 */

import { useApp } from "@/lib/store";
import type { ActiveIntervention, ControlMessage } from "@/lib/frame-types";
import { useEffect, useState } from "react";
import LayerDivergenceChart from "./LayerDivergenceChart";

type Props = {
  sendControl: (msg: ControlMessage) => void;
};

const STRENGTH_PRESETS = [0.02, 0.05, 0.1, 0.2, 0.4];

function effectQuality(d: number | undefined): { label: string; color: string } {
  if (d == null) return { label: "unvalidated", color: "#9ca3af" };
  const a = Math.abs(d);
  if (a >= 1.5) return { label: "strong", color: "#22c55e" };
  if (a >= 0.8) return { label: "solid", color: "#84cc16" };
  if (a >= 0.4) return { label: "moderate", color: "#eab308" };
  return { label: "weak", color: "#f97316" };
}

export default function SteeringControl({ sendControl }: Props) {
  const available = useApp((s) => s.steeringAvailable);
  const loadError = useApp((s) => s.steeringError);
  const directions = useApp((s) => s.steeringDirections);
  const calibration = useApp((s) => s.steeringCalibration);
  const active = useApp((s) => s.activeInterventions);
  const frames = useApp((s) => s.frames);
  const layer = useApp((s) => s.layer);

  const [selected, setSelected] = useState<string | null>(null);
  const [strength, setStrength] = useState(0.1);
  const [targetLayer, setTargetLayer] = useState(layer);

  useEffect(() => setTargetLayer(layer), [layer]);

  // Default to the first direction once the catalog lands.
  useEffect(() => {
    if (!selected && directions.length > 0) setSelected(directions[0].id);
  }, [directions, selected]);

  const selectedInfo = directions.find((d) => d.id === selected) ?? null;
  const quality = effectQuality(selectedInfo?.validation?.confidence_cohens_d);

  const isLayerCompatible = selectedInfo?.layer == null || selectedInfo.layer === targetLayer;

  // The strength slider is a *fraction of the residual stream's own
  // magnitude*. That only means anything if the backend measured that
  // magnitude for the layer we are injecting at. If it didn't, the
  // percentage shown next to the slider would be a fiction, so we say
  // so rather than letting the number stand.
  const layerRms = calibration?.layer_rms?.[String(targetLayer)];
  const calibrated = calibration?.calibrated === true && layerRms != null;

  const onInject = () => {
    if (!selected) return;
    sendControl({
      kind: "inject_steering",
      payload: { direction: selected, strength, layer: targetLayer },
    });
  };

  const onRevert = (id: number) => {
    sendControl({ kind: "revert_steering", payload: { intervention_id: id } });
  };

  const onClear = () => sendControl({ kind: "clear_steering", payload: {} });

  // Live read-out of the current token's alignment with the steering
  // direction — this is the "is the model actually holding onto the
  // perturbation" signal, straight off the frame.
  const latest = frames.length > 0 ? frames[frames.length - 1] : null;
  const liveAlign = latest?.steer_alignment ?? null;

  if (!available) {
    return (
      <div className="flex flex-col gap-2 p-4 rounded-lg bg-panel border border-border">
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
          Steering Control
        </h2>
        <p className="text-xs text-gray-500 leading-relaxed">
          No steering vectors loaded
          {loadError ? ` — ${loadError}` : "."}
        </p>
        <code className="text-[10px] text-gray-600 bg-bg/50 rounded p-2 block">
          python3 backend/examples/compute_steering_vectors.py
        </code>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 p-4 rounded-lg bg-panel border border-border">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
          Steering Control
        </h2>
        {active.length > 0 && (
          <span className="px-1.5 py-0.5 rounded text-[10px] bg-purple-500/20 text-purple-300">
            {active.length} active
          </span>
        )}
      </div>

      {/* Direction picker, with the evidence for each */}
      <div className="flex flex-col gap-1">
        {directions.map((d) => {
          const q = effectQuality(d.validation?.confidence_cohens_d);
          const isSel = selected === d.id;
          return (
            <button
              key={d.id}
              onClick={() => setSelected(d.id)}
              className={`flex items-center justify-between px-2.5 py-1.5 rounded text-left transition-colors border ${
                isSel
                  ? "bg-accent/15 border-accent/50"
                  : "bg-bg/40 border-border hover:border-accent/25"
              }`}
            >
              <div className="min-w-0">
                <div className={`text-xs font-medium ${isSel ? "text-accent" : "text-gray-200"}`}>
                  {d.label}
                </div>
                <div className="text-[10px] text-gray-500 truncate">{d.hint}</div>
              </div>
              <div className="flex items-center gap-1.5 shrink-0 ml-2">
                <span className="text-[9px]" style={{ color: q.color }}>
                  {q.label}
                </span>
                <span className="text-[9px] text-gray-600 font-mono">
                  L{d.layer ?? "?"}
                </span>
              </div>
            </button>
          );
        })}
      </div>

      {/* Provenance for the selected direction */}
      {selectedInfo && (
        <div className="rounded bg-bg/40 border border-border px-2.5 py-2 text-[10px] text-gray-500 space-y-0.5">
          <div className="flex justify-between">
            <span>extracted at</span>
            <span className="text-gray-400 font-mono">L{selectedInfo.layer ?? "?"}</span>
          </div>
          <div className="flex justify-between">
            <span>from tokens</span>
            <span className="text-gray-400 font-mono">
              {(selectedInfo.n_positive ?? 0).toLocaleString()} /{" "}
              {(selectedInfo.n_negative ?? 0).toLocaleString()}
            </span>
          </div>
          {selectedInfo.validation?.confidence_cohens_d != null && (
            <div className="flex justify-between">
              <span>Cohen&apos;s d</span>
              <span className="font-mono" style={{ color: quality.color }}>
                {selectedInfo.validation.confidence_cohens_d.toFixed(2)}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Strength */}
      <div className="flex flex-col gap-1">
        <div className="flex justify-between items-baseline">
          <span className="text-xs text-gray-400">Strength</span>
          <span className="text-xs font-mono text-accent">
            {(strength * 100).toFixed(0)}%
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={0.5}
          step={0.01}
          value={strength}
          onChange={(e) => setStrength(parseFloat(e.target.value))}
          className="w-full accent-accent"
        />
        <div className="flex gap-1">
          {STRENGTH_PRESETS.map((s) => (
            <button
              key={s}
              onClick={() => setStrength(s)}
              className={`flex-1 text-[10px] py-0.5 rounded border ${
                Math.abs(strength - s) < 1e-9
                  ? "border-accent text-accent"
                  : "border-border text-gray-500 hover:text-gray-300"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        <p className="text-[10px] text-gray-500 leading-snug">
          {calibrated ? (
            <>
              ‖v‖ ={" "}
              <span className="font-mono text-gray-400">
                {(strength * layerRms).toFixed(2)}
              </span>{" "}
              against a measured ‖h‖ ≈{" "}
              <span className="font-mono text-gray-400">{layerRms.toFixed(1)}</span>{" "}
              at L{targetLayer}.
            </>
          ) : (
            <>
              Scale for L{targetLayer} not measured — the percentage
              above is <em>not</em> a fraction of the state. Run{" "}
              <code className="text-gray-400">measure_layers.py</code>{" "}
              and reload.
            </>
          )}
        </p>
      </div>

      {/* Layer */}
      <div className="flex flex-col gap-1">
        <div className="flex justify-between items-baseline">
          <span className="text-xs text-gray-400">Inject at layer</span>
          <span className="text-xs font-mono text-gray-300">L{targetLayer}</span>
        </div>
        <select
          value={targetLayer}
          onChange={(e) => setTargetLayer(parseInt(e.target.value, 10))}
          className="px-2 py-1 rounded bg-bg border border-border text-xs text-gray-200"
        >
          {[4, 8, 10, 12, 14, 16, 18, 20, 24, 28].map((l) => (
            <option key={l} value={l}>
              Layer {l}
            </option>
          ))}
        </select>
        {!isLayerCompatible && selectedInfo?.layer != null && (
          <p className="text-[10px] text-amber-500/80 leading-snug">
            This direction was extracted at L{selectedInfo.layer}. Applying it
            elsewhere works, but the effect size will differ.
          </p>
        )}
      </div>

      <button
        onClick={onInject}
        disabled={!selected}
        className="w-full py-1.5 rounded bg-accent hover:bg-accent/85 disabled:opacity-40 text-bg text-xs font-semibold"
      >
        Inject
      </button>

      {/* Live telemetry from the current frame */}
      {active.length > 0 && latest?.steer_active && (
        <div className="rounded bg-purple-500/10 border border-purple-500/30 px-2.5 py-2 text-[10px] space-y-0.5">
          <div className="text-purple-300 font-medium mb-1">Live effect</div>
          <div className="flex justify-between text-gray-400">
            <span>‖v‖ injected</span>
            <span className="font-mono text-gray-300">
              {latest.steer_norm?.toFixed(3) ?? "—"}
            </span>
          </div>
          <div className="flex justify-between text-gray-400">
            <span>cos(h, v̂)</span>
            <span className="font-mono text-gray-300">
              {liveAlign != null ? liveAlign.toFixed(4) : "—"}
            </span>
          </div>
        </div>
      )}

      {/* How the response develops over the sequence */}
      {active.length > 0 && <LayerDivergenceChart />}

      {/* Active interventions */}
      {active.length > 0 && (
        <div className="flex flex-col gap-1">
          <div className="flex justify-between items-center">
            <span className="text-[10px] text-gray-500 uppercase tracking-wider">
              Active
            </span>
            <button onClick={onClear} className="text-[10px] text-gray-500 hover:text-gray-300">
              clear all
            </button>
          </div>
          {active.map((iv: ActiveIntervention) => {
            const info = directions.find((d) => d.id === iv.direction);
            return (
              <div
                key={iv.id}
                className="flex items-center justify-between bg-bg/40 border border-border rounded px-2 py-1 text-[10px]"
              >
                <span className="text-gray-300 truncate">
                  {info?.label ?? iv.direction}
                  <span className="text-gray-500 ml-1.5 font-mono">
                    L{iv.layer} · {(iv.strength * 100).toFixed(0)}%
                  </span>
                </span>
                <button
                  onClick={() => onRevert(iv.id)}
                  className="text-gray-500 hover:text-red-400 ml-2 shrink-0"
                  title="revert this intervention"
                >
                  ✕
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

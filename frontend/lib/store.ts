"use client";

import { create } from "zustand";
import type {
  ActiveIntervention,
  Frame,
  ReadyMessage,
  SteeringCatalogMessage,
  SteeringDirectionInfo,
} from "./frame-types";

/**
 * Global app state. The key slice is `frames`, a rolling buffer of
 * Frame objects. We cap it at MAX_FRAMES to keep the 3-D scene
 * responsive; for very long traces the scene samples down.
 */

const MAX_FRAMES = 800;

type AppState = {
  // Streamed state
  frames: Frame[];
  latest: Frame | null;
  fullText: string;          // concatenated token text, for the side panel
  /**
   * Step the reader is currently pointing at, for the per-layer derivation
   * chain. `latest.step_id` is the *newest* frame, which is only the right
   * one while playback is following along; the moment the reader scrubs
   * back it is not. Null means "follow the newest frame".
   */
  focusedStep: number | null;
  /**
   * Every time the reader points at a step, `pickSeq` goes up by one.
   *
   * `reset()` compares it against `pickSeqAtResetRequest` to decide whether
   * the backend's `reset_ack` is allowed to clear that pointer. See `reset`.
   */
  pickSeq: number;
  /** `pickSeq` as of the last reset **request** (not its ack). */
  pickSeqAtResetRequest: number;
  /**
   * Which recording is being replayed. The frames themselves do not carry
   * their trajectory id -- a frame from one recording is indistinguishable
   * from a frame of another -- so the per-layer chain could not tell which
   * logit-lens entry belongs to what is on screen. Set by ControlPanel
   * when the picker changes.
   */
  currentTrajectory: string | null;

  // Configuration
  layer: number;
  /** Layers the backend says it can replay; empty until `ready` says otherwise. */
  availableLayers: number[];
  /** {id,label,mode}[] the backend can replay; empty = any prompt allowed. */
  trajectories: { id: string; label: string; mode: string }[];
  prompt: string;
  speed: number;
  paused: boolean;

  // Connection
  availablePresets: string[];
  ready: boolean;
  connected: boolean;
  error: string | null;

  // Steering / intervention state. The catalog is what the backend
  // says it can actually inject (with the evidence for each), and
  // `active` is the live set currently perturbing the stream.
  steeringAvailable: boolean;
  steeringError: string | null;
  steeringDirections: SteeringDirectionInfo[];
  steeringCalibration: { calibrated: boolean; layers: number[]; layer_rms: Record<string, number> } | null;
  activeInterventions: ActiveIntervention[];

  // Setters
  ingestFrame: (f: Frame) => void;
  ingestReady: (r: ReadyMessage) => void;
  ingestSteeringCatalog: (m: SteeringCatalogMessage) => void;
  setActiveInterventions: (list: ActiveIntervention[]) => void;
  setLayer: (l: number) => void;
  setPrompt: (p: string) => void;
  setFocusedStep: (s: number | null) => void;
  requestReset: () => void;
  setCurrentTrajectory: (id: string | null) => void;
  setSpeed: (s: number) => void;
  setPaused: (b: boolean) => void;
  setConnected: (c: boolean) => void;
  setError: (e: string | null) => void;
  reset: () => void;
};

export const useApp = create<AppState>((set) => ({
  frames: [],
  latest: null,
  fullText: "",
  focusedStep: null,
  pickSeq: 0,
  pickSeqAtResetRequest: 0,
  currentTrajectory: null,

  layer: 14,
  availableLayers: [],
  trajectories: [],
  prompt: "Why is the sky blue?",
  speed: 1.0,
  paused: false,

  availablePresets: [],
  ready: false,
  connected: false,
  error: null,

  steeringAvailable: false,
  steeringError: null,
  steeringDirections: [],
  steeringCalibration: null,
  activeInterventions: [],

  ingestFrame: (f) =>
    set((s) => ({
      frames: [...s.frames, f].slice(-MAX_FRAMES),
      latest: f,
      fullText: (s.fullText + (f.token || "")).slice(-4000),
    })),

  ingestReady: (r) =>
    set(() => ({
      ready: true,
      availablePresets: r.payload.presets,
      layer: r.payload.layer,
      availableLayers: r.payload.layers ?? [],
      // Which recordings the backend can replay. Non-empty means the prompt
      // must be one of these ids, so the UI offers a picker instead of a free
      // text box -- see the note on ReadyMessage.trajectories.
      trajectories: r.payload.trajectories ?? [],
    })),

  ingestSteeringCatalog: (m) =>
    set(() => ({
      steeringAvailable: m.payload.available,
      steeringError: m.payload.error,
      steeringDirections: m.payload.directions,
      steeringCalibration: m.payload.calibration ?? null,
    })),

  setActiveInterventions: (list) => set(() => ({ activeInterventions: list })),

  setLayer: (l) => set(() => ({ layer: l })),
  setPrompt: (p) => set(() => ({ prompt: p })),
  // ⚠ Every point the reader makes bumps the sequence counter, *including*
  //   clearing back to "follow the newest frame" (`live` button, set to null).
  //   A null pointer is still a pointer the reader set on purpose.
  setFocusedStep: (s) =>
    set((st) => ({ focusedStep: s, pickSeq: st.pickSeq + 1 })),
  setCurrentTrajectory: (id) => set(() => ({ currentTrajectory: id })),

  // Called at the moment the reader presses reset — *before* the backend
  // answers. It records which pick was current then; `reset()` (the ack
  // handler) compares against it. It deliberately does not clear anything.
  requestReset: () => set((s) => ({ pickSeqAtResetRequest: s.pickSeq })),
  setSpeed: (s) => set(() => ({ speed: s })),
  setPaused: (b) => set(() => ({ paused: b })),
  setConnected: (c) => set(() => ({ connected: c })),
  setError: (e) => set(() => ({ error: e })),
  reset: () =>
    // ⚠ `s`（而不是原来的 `()`）：下面要拿上一次 pickSeq 与请求时的快照比。
    set((s) => ({
      frames: [],
      latest: null,
      fullText: "",
      activeInterventions: [],
      // Both are per-run. Leaving the previous recording's id here would
      // point the per-layer chain at a trajectory that is no longer on
      // screen -- and since a frame carries no id of its own, the chain
      // would render confidently from the wrong record.
      //
      // ⚠⚠ `focusedStep` is NOT simply cleared here, and that is the fix.
      //   This runs on the backend's `reset_ack` (app/page.tsx) — i.e. after a
      //   **network round trip**, not on the click. Pointing the step slider at
      //   a step *after* pressing reset is ordinary use, and the ack landing
      //   used to wipe that pick: the panel then fell back to
      //   `latest.step_id`, which right after a reset is the first frames of
      //   the replay (~step 96), far outside the 32-step readout window, so the
      //   panel sat on "out-of-window" and the reader's pick was gone with no
      //   way back. Measured: `set.afterSet="994"` yet a few hundred ms later
      //   `sliderValue="992"` — this was F9's ~50% flake.
      //   ⇒ Compare against the pickSeq snapshot taken at *request* time: if
      //     the reader pointed somewhere after asking for the reset, that pick
      //     is the newer intent and survives.
      focusedStep: s.pickSeq === s.pickSeqAtResetRequest ? null : s.focusedStep,
    })),
}));
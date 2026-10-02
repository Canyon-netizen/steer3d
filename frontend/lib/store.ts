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

  // Configuration
  layer: number;
  /** Layers the backend says it can replay; empty until `ready` says otherwise. */
  availableLayers: number[];
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

  layer: 14,
  availableLayers: [],
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
  setSpeed: (s) => set(() => ({ speed: s })),
  setPaused: (b) => set(() => ({ paused: b })),
  setConnected: (c) => set(() => ({ connected: c })),
  setError: (e) => set(() => ({ error: e })),
  reset: () =>
    set(() => ({
      frames: [],
      latest: null,
      fullText: "",
      activeInterventions: [],
    })),
}));
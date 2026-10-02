"use client";

/**
 * Frame types shared between the WebSocket layer and the rendering
 * layer. Mirrors backend/core/protocol.py.
 */

export type Point3D = { x: number; y: number; z: number };

export type Frame = {
  ts: number;
  step_id: number;
  token: string;
  token_id: number;
  point: Point3D;
  perplexity?: number | null;
  entropy?: number | null;
  loss?: number | null;
  is_self_check?: boolean;
  is_revisit?: boolean;
  // Intervention telemetry — populated only while steering is active.
  steer_active?: boolean;
  steer_norm?: number | null;
  steer_alignment?: number | null;
  steer_projection?: number | null;
};

export type ReadyMessage = {
  kind: "ready";
  payload: {
    presets: string[];
    layer: number;
    d_model: number;
    sample_every: number;
    /** Layers the runner can actually replay. Empty = runner doesn't say. */
    layers?: number[];
  };
};

/** One steering direction the backend can inject, with its evidence. */
export type SteeringDirectionInfo = {
  id: string;
  label: string;
  hint: string;
  layer: number | null;
  validation: { confidence_cohens_d?: number; [k: string]: unknown };
  n_positive: number | null;
  n_negative: number | null;
};

export type SteeringCatalogMessage = {
  kind: "steering_catalog";
  payload: {
    available: boolean;
    error: string | null;
    directions: SteeringDirectionInfo[];
    calibration?: {
      calibrated: boolean;
      layers: number[];
      layer_rms: Record<string, number>;
    };
  };
};

export type ActiveIntervention = {
  id: number;
  direction: string;
  strength: number;
  layer: number;
  active: boolean;
};

export type SteeringAckMessage = {
  kind: "steering_ack";
  payload: {
    intervention?: ActiveIntervention;
    injected_norm?: number | null;
    reverted?: number | null;
    cleared?: number;
    active: ActiveIntervention[];
  };
};

export type ErrorMessage = { kind: "error"; payload: { message: string } };
export type ResetAckMessage = { kind: "reset_ack" };

export type ServerMessage =
  | Frame
  | ReadyMessage
  | SteeringCatalogMessage
  | SteeringAckMessage
  | ErrorMessage
  | ResetAckMessage;

export type ControlKind =
  | "start"
  | "cancel"
  | "pause"
  | "resume"
  | "set_layer"
  | "set_prompt"
  | "set_speed"
  | "reset"
  | "inject_steering"
  | "revert_steering"
  | "clear_steering";

export type ControlMessage = {
  kind: ControlKind;
  payload?: Record<string, unknown>;
};
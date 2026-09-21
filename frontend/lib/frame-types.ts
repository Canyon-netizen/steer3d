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
};

export type ReadyMessage = {
  kind: "ready";
  payload: {
    presets: string[];
    layer: number;
    d_model: number;
    sample_every: number;
  };
};

export type ErrorMessage = { kind: "error"; payload: { message: string } };
export type ResetAckMessage = { kind: "reset_ack" };

export type ServerMessage = Frame | ReadyMessage | ErrorMessage | ResetAckMessage;

export type ControlKind =
  | "start"
  | "cancel"
  | "pause"
  | "resume"
  | "set_layer"
  | "set_prompt"
  | "set_speed"
  | "reset";

export type ControlMessage = {
  kind: ControlKind;
  payload?: Record<string, unknown>;
};
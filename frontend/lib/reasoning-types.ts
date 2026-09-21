/**
 * TypeScript mirror of `backend/core/reasoning_io.py`.
 *
 * This file is the **single source of truth** for reasoning data
 * shapes on the frontend. Mirrors the JSON Schema in
 * `backend/core/reasoning_io.py:RUN_SCHEMA` (format_version 1.0).
 *
 * Any change to `ReasoningRun` / `Frame` / `Point3D` here must be
 * matched in `reasoning_io.py`. The contract is locked; version
 * bumps require updating `FORMAT_VERSION` on both sides.
 */

// ----- Constants ---------------------------------------------------------

export const FORMAT_VERSION = "1.0";

// ----- Primitive types ---------------------------------------------------

/** A 3-D point in the projected (online PCA / UMAP) space. */
export interface Point3D {
  x: number;
  y: number;
  z: number;
}

/**
 * A single per-token frame. Wire format = `Frame.to_dict()` in
 * backend/core/protocol.py.
 */
export interface Frame {
  ts: number;
  step_id: number;
  token: string;
  token_id: number;
  point: Point3D;
  perplexity: number | null;
  entropy: number | null;
  loss: number | null;
  is_self_check: boolean;
  is_revisit: boolean;
}

/**
 * A complete reasoning run. See docs/REASONING_IO.md.
 */
export interface ReasoningRun {
  format_version: string;
  run_id: string;
  model: string;
  layer: number;
  prompt: string;
  started_at: number;
  finished_at: number | null;
  metadata: Record<string, unknown>;
  generated_text: string;
  frames: Frame[];
}

// ----- Builder pattern (for live streaming) -----------------------------

/**
 * Incremental accumulator for streaming sources (WebSocket, async iter).
 * Mirrors `RunBuilder` in Python.
 */
export class RunBuilder {
  readonly run_id: string;
  model = "";
  layer = 0;
  prompt = "";
  started_at: number;
  metadata: Record<string, unknown> = {};
  private frames: Frame[] = [];
  private finished_at: number | null = null;

  constructor(init: {
    run_id?: string;
    model?: string;
    layer?: number;
    prompt?: string;
    started_at?: number;
    metadata?: Record<string, unknown>;
  } = {}) {
    this.run_id = init.run_id ?? cryptoRandomId();
    this.model = init.model ?? "";
    this.layer = init.layer ?? 0;
    this.prompt = init.prompt ?? "";
    this.started_at = init.started_at ?? Date.now() / 1000;
    this.metadata = { ...(init.metadata ?? {}) };
  }

  /**
   * Append a frame. Throws if step_id is not strictly increasing.
   */
  pushFrame(frame: Frame): void {
    if (this.frames.length > 0 && frame.step_id <= this.frames[this.frames.length - 1].step_id) {
      throw new Error(
        `Frame step_id must be strictly increasing; got ${frame.step_id} after ${this.frames[this.frames.length - 1].step_id}`,
      );
    }
    this.frames.push(frame);
  }

  finish(finished_at?: number): ReasoningRun {
    const ts = finished_at ?? Date.now() / 1000;
    this.finished_at = ts;
    return {
      format_version: FORMAT_VERSION,
      run_id: this.run_id,
      model: this.model,
      layer: this.layer,
      prompt: this.prompt,
      started_at: this.started_at,
      finished_at: this.finished_at,
      metadata: { ...this.metadata },
      generated_text: this.frames.map((f) => f.token).join(""),
      frames: [...this.frames],
    };
  }

  get n_frames(): number {
    return this.frames.length;
  }
}

// ----- JSON Schema validator (lightweight) -------------------------------

/**
 * Lightweight JSON-Schema-flavored validator. Matches the Python
 * `validate_run` in semantics. Not a full JSON Schema implementation;
 * just enough to catch the common bugs.
 */
export function validateRun(data: unknown): asserts data is ReasoningRun {
  if (typeof data !== "object" || data === null) {
    throw new Error(`ReasoningRun must be an object, got ${typeof data}`);
  }
  const d = data as Record<string, unknown>;

  const required = ["format_version", "run_id", "model", "layer", "prompt", "started_at", "metadata", "frames"];
  for (const k of required) {
    if (!(k in d)) {
      throw new Error(`Missing required field: ${k}`);
    }
  }
  if (typeof d["format_version"] !== "string" || !/^\d+\.\d+$/.test(d["format_version"])) {
    throw new Error(`format_version must match X.Y, got ${d["format_version"]}`);
  }
  if (typeof d["layer"] !== "number" || d["layer"] < 0) {
    throw new Error(`layer must be a non-negative number, got ${d["layer"]}`);
  }
  if (typeof d["started_at"] !== "number") {
    throw new Error(`started_at must be a number, got ${typeof d["started_at"]}`);
  }
  if (!Array.isArray(d["frames"])) {
    throw new Error(`frames must be an array, got ${typeof d["frames"]}`);
  }
  let prev = -1;
  for (let i = 0; i < (d["frames"] as unknown[]).length; i++) {
    const f = (d["frames"] as unknown[])[i];
    validateFrame(f, i);
    if ((f as Frame).step_id <= prev) {
      throw new Error(`frames must be sorted by step_id ascending; got ${(f as Frame).step_id} after ${prev} at index ${i}`);
    }
    prev = (f as Frame).step_id;
  }
}

function validateFrame(data: unknown, idx: number): asserts data is Frame {
  if (typeof data !== "object" || data === null) {
    throw new Error(`frame[${idx}] must be an object`);
  }
  const f = data as Record<string, unknown>;
  for (const k of ["ts", "step_id", "token", "token_id", "point"]) {
    if (!(k in f)) {
      throw new Error(`frame[${idx}] missing field: ${k}`);
    }
  }
  if (typeof f["step_id"] !== "number" || f["step_id"] < 0) {
    throw new Error(`frame[${idx}].step_id must be a non-negative number`);
  }
  if (typeof f["token"] !== "string") {
    throw new Error(`frame[${idx}].token must be a string`);
  }
  const pt = f["point"];
  if (typeof pt !== "object" || pt === null ||
      typeof (pt as Point3D).x !== "number" ||
      typeof (pt as Point3D).y !== "number" ||
      typeof (pt as Point3D).z !== "number") {
    throw new Error(`frame[${idx}].point must be {x:number, y:number, z:number}`);
  }
}

// ----- Helpers -----------------------------------------------------------

/** UUID-ish random ID generator (browser-safe, no external dep). */
function cryptoRandomId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // Fallback: timestamp + random
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
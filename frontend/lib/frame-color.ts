"use client";

/**
 * Colour encoding for trajectory points, shared by the WebGL scene and
 * the 2-D fallback so the two can never disagree about what a colour
 * means.
 *
 * The important case is the third one. `entropy` and `perplexity` are
 * only populated by a collection run that captured logits; the archived
 * PCA bundle stores hidden states alone, so replaying it yields
 * `entropy: null` for every single frame. Mapping `null` onto the middle
 * of the heat ramp -- which is what this code did before -- paints the
 * whole trajectory a confident-looking teal and invites the reader to
 * read a confidence value off a pixel that was never measured. So
 * `null` gets its own colour and its own legend row, and says so.
 */

import type { Frame } from "./frame-types";

export type ColorKind = "entropy" | "self_check" | "no_data";

export type FrameColor = {
  r: number;
  g: number;
  b: number;
  kind: ColorKind;
  /** Human-readable meaning, surfaced in tooltips and the legend. */
  label: string;
};

/** Self-check: the model went back to re-examine something. */
const SELF_CHECK: FrameColor = {
  r: 1.0, g: 0.6, b: 0.2, kind: "self_check", label: "self-check token",
};

/**
 * No logits were stored, so there is no entropy to show. Deliberately a
 * desaturated violet rather than a grey-blue: the grid and the axis triad
 * are already grey-blue, and a ribbon the same hue as its own background
 * furniture is hard to read *and* impossible to assert on -- a
 * "did the trajectory paint?" check written against this colour would be
 * satisfied by the grid alone.
 */
const NO_DATA: FrameColor = {
  r: 0.62, g: 0.56, b: 0.80, kind: "no_data", label: "entropy not recorded",
};

/**
 * Measured entropy -> heat ramp. Only called when a real number exists.
 * Entropy is clipped to [0, 3] nats, which covers the useful range for
 * a next-token distribution without letting one wild frame own the ramp.
 */
export function entropyToRgb(entropy: number): { r: number; g: number; b: number } {
  const e = Math.max(0, Math.min(3, entropy));
  const t = e / 3;
  return {
    r: Math.min(1, t * 2),
    g: Math.min(1, 1 - Math.abs(t - 0.5) * 2),
    b: Math.min(1, (1 - t) * 2),
  };
}

export function frameColor(f: Frame | null | undefined): FrameColor {
  if (!f) return NO_DATA;
  if (f.is_self_check) return SELF_CHECK;
  if (f.entropy == null || !Number.isFinite(f.entropy)) return NO_DATA;
  const { r, g, b } = entropyToRgb(f.entropy);
  const label =
    f.entropy < 0.5 ? "confident (low entropy)"
    : f.entropy < 1.5 ? "uncertain"
    : "very uncertain";
  return { r, g, b, kind: "entropy", label };
}

export function toCss(c: FrameColor): string {
  const to255 = (v: number) => Math.round(Math.max(0, Math.min(1, v)) * 255);
  return `rgb(${to255(c.r)}, ${to255(c.g)}, ${to255(c.b)})`;
}

"use client";

/**
 * World scale for the 3-D scene, and the reason it exists.
 *
 * The backend projects the residual stream onto 3 principal components
 * *without* rescaling, so the magnitudes it sends are whatever the
 * model's hidden-state variance happens to be at that layer. Measured
 * over the whole archived bundle (6 problems x 4 layers x 2 arms) the
 * largest absolute coordinate is 1199.3, reached at L26.
 *
 * The scene's furniture -- grid, axis cones, particles -- is authored in
 * unit-scale numbers, because that is what looks right when the data
 * happens to be order 1. Fed the real coordinates those numbers stop
 * being "small" and become sub-pixel: a radius-0.05 particle sitting
 * 1199 units from a camera 9.5 units out covers 0.038 px of an 844 px
 * viewport. The decorations are not drawn small, they are not drawn at
 * all, and the ribbon flies outside the frustum.
 *
 * Dividing every coordinate by one shared constant is a similarity
 * transform. Angles, ratios and relative distances -- everything this
 * visualisation actually claims -- are preserved exactly. Only the
 * arbitrary unit the numbers were counted in changes.
 *
 * One constant for every problem and every layer, deliberately. A
 * per-problem (or per-layer) divisor would make trajectories of wildly
 * different true size all fill the frame, so two paths 60x apart would
 * look identical. That is the opposite of what this view is for. The
 * consequence -- that a shallow layer collapses to a dot next to a deep
 * one -- is a real property of the model, and `trajectoryExtent` is
 * surfaced in the UI so the reader can see it rather than infer it.
 */

/** Largest |coordinate| over the archived bundle, rounded up: 1199.3 -> 1200. */
export const PCA_WORLD_SCALE = 1200;

/** Half-extent of the world box the camera frames: [-1, 1] on each axis. */
export const WORLD_HALF_EXTENT = 1;

/** Raw PCA units -> world units. */
export function scaleCoord(v: number): number {
  return v / PCA_WORLD_SCALE;
}

export type Extent = {
  /** Largest absolute coordinate on any axis, in raw PCA units. */
  maxAbs: number;
  /** Per-axis [min, max], in raw PCA units. */
  min: [number, number, number];
  max: [number, number, number];
};

/**
 * True extent of a set of raw points, in the units the backend sent.
 * Reported to the reader so the normalised view can be read honestly:
 * "this path looks small" and "this path *is* small" are different claims.
 */
export function trajectoryExtent(
  points: readonly { x: number; y: number; z: number }[],
): Extent | null {
  if (points.length === 0) return null;
  const min: [number, number, number] = [Infinity, Infinity, Infinity];
  const max: [number, number, number] = [-Infinity, -Infinity, -Infinity];
  for (const p of points) {
    const v = [p.x, p.y, p.z];
    for (let i = 0; i < 3; i++) {
      if (!Number.isFinite(v[i])) continue;
      if (v[i] < min[i]) min[i] = v[i];
      if (v[i] > max[i]) max[i] = v[i];
    }
  }
  if (!Number.isFinite(min[0])) return null;
  const maxAbs = Math.max(
    Math.abs(min[0]), Math.abs(max[0]),
    Math.abs(min[1]), Math.abs(max[1]),
    Math.abs(min[2]), Math.abs(max[2]),
  );
  return { maxAbs, min, max };
}

/**
 * Fraction of the framed world box this trajectory occupies.
 * A layer whose variance is 90x smaller than the deepest one shows up
 * here as a proportionally tiny number, which is the honest reading.
 */
export function extentFraction(e: Extent | null): number | null {
  if (!e) return null;
  return e.maxAbs / (WORLD_HALF_EXTENT * PCA_WORLD_SCALE);
}

export type AtlasLayer = {
  layer: number;
  mean_auc: number | null;
  mean_auc_cos: number | null;
  mean_auc_cos_oriented: number | null;
  mean_auc_norm: number | null;
  mean_auc_proj_resid: number | null;
  mean_effect: number | null;
  mean_effect_cos: number | null;
  mean_cos_marker: number | null;
  mean_cos_nonmarker: number | null;
  mean_norm_marker: number | null;
  mean_norm_nonmarker: number | null;
  mean_norm: number;
  n_marker: number;
  n_total: number;
  n_trajectories_with_both_classes: number;
  n_trajectories_with_orientation: number;
  n_trajectories_negative_orientation: number;
  cos_orientation: number | null;
};

export type AtlasSeries = {
  id: string;
  problem: string;
  mode: string;
  T: number;
  n_prompt_tokens: number | null;
  n_marker: number;
  tokens: string[] | null;
  token_ids: number[];
  top1_ids: number[] | null;
  marker_mask: number[];
  marker_positions: number[];
  proj: number[][];
  cos: number[][];
  norm: number[][];
};

export type MarkerLayer = {
  layer: number;
  mean_auc_cos: number | null;
  mean_auc_cos_oriented: number | null;
  mean_cos_marker: number | null;
  mean_cos_nonmarker: number | null;
  n_trajectories: number;
};

export type MarkerAtlas = {
  n_occurrences: number;
  n_trajectories: number;
  best_layer: number | null;
  best_layer_mean_auc_cos: number | null;
  best_layer_mean_auc_cos_oriented: number | null;
  best_layer_orientation: number | null;
  layers: MarkerLayer[];
};

export type ReadoutAtlas = {
  schema: string;
  complete: boolean;
  scope: string;
  vector: { path: string; sha256: string; extraction_layer: number; injection_block: number; norm: number };
  model: { name: string; n_layers: number; d_model: number };
  marker_ids: number[];
  aggregate: {
    layers: AtlasLayer[];
    best_layer: number;
    best_layer_mean_auc_proj: number | null;
    best_layer_mean_auc_cos: number | null;
    best_layer_mean_auc_cos_oriented: number | null;
    best_layer_mean_auc_norm: number | null;
    best_layer_mean_auc_proj_resid: number | null;
    best_layer_orientation: number | null;
    n_trajectories_with_orientation: number;
    n_trajectories_negative_orientation: number;
    chance_level: number;
    n_trajectories: number;
    n_marker_total: number;
    n_positions_total: number;
  };
  per_marker: Record<string, MarkerAtlas>;
  series: AtlasSeries[];
  guards: Record<string, unknown>;
  generated_by: string;
};

export const fmt = (value: number | null, digits = 4): string => {
  if (value === null || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
};

export const signed = (value: number | null, digits = 4): string => {
  if (value === null || !Number.isFinite(value)) return "—";
  return (value >= 0 ? "+" : "") + value.toFixed(digits);
};

export const colorFor = (value: number, channel: "cos" | "proj" | "norm", scale: number): string => {
  const clamp = (x: number) => Math.max(-1, Math.min(1, x));
  const mix = (a: number[], b: number[], t: number) => {
    const k = clamp(t);
    return "rgb(" + Math.round(a[0] + (b[0] - a[0]) * k) + "," +
      Math.round(a[1] + (b[1] - a[1]) * k) + "," +
      Math.round(a[2] + (b[2] - a[2]) * k) + ")";
  };
  if (channel === "norm") {
    const t = Math.max(0, Math.min(1, value / Math.max(scale, 1e-9)));
    return mix([15, 23, 42], [56, 189, 248], t);
  }
  const t = Math.max(-1, Math.min(1, value / Math.max(scale, 1e-9)));
  if (t < 0) return mix([248, 250, 252], [251, 113, 133], -t);
  return mix([248, 250, 252], [96, 165, 250], t);
};

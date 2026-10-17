export type SummaryBlock = {
  mean: number; min: number; max: number; n_problems: number; per_problem?: Record<string, number>;
};

export type LayerRow = {
  layer: number;
  block_mean: number;
  restore_mean: number;
  compensation: number;
  support: number;
  action: "supporting" | "compensating" | "weak";
  same_sign: boolean;
  beyond_random_median: boolean;
  random_rank: number;
  random_compensations: number[];
  random_median_abs: number;
  n_random_groups: number;
  block_per_problem: Record<string, number>;
  restore_per_problem: Record<string, number>;
  n_problems: number;
  net_effect_primary: number;
};

export type DoseRow = { dose: number; mean: number; min: number; max: number; n_problems: number };

export type Marker = { id: number; dot: number; freq: number; share: number };
export type AxisLayer = { cos: number; control_cos: number; beats_control: boolean };
export type Axis = {
  label: string; status: string; n_layers_beating_control: number; n_layers: number;
  per_layer: Record<string, AxisLayer>;
};
export type Unit = { unit: number; score: number; baseline_magnitude: number; column_norm: number };
export type UnitLayer = {
  layer: number; n: number; score_mean: number; score_min: number; score_max: number;
  baseline_magnitude_mean: number; column_norm_mean: number; top_units: Unit[];
};
export type Recommendation = {
  priority: "high" | "medium" | "low";
  action: string;
  layer: number | null;
  reason: string;
  evidence: string[];
  confidence: string;
};

export type AtlasLayer = {
  layer: number;
  mean_auc_cos: number | null;
  mean_auc_cos_oriented: number | null;
  mean_auc_norm: number | null;
  mean_auc_proj_resid: number | null;
  n_trajectories_with_both_classes: number;
};

export type PerMarkerSummary = {
  n_occurrences: number;
  n_trajectories: number;
  best_layer: number | null;
  best_layer_mean_auc_cos: number | null;
  best_layer_mean_auc_cos_oriented: number | null;
  best_layer_orientation: number | null;
};

export type ReadoutAtlasSummary = {
  best_layer: number;
  best_layer_mean_auc_cos: number | null;
  best_layer_mean_auc_cos_oriented: number | null;
  best_layer_mean_auc_norm: number | null;
  best_layer_mean_auc_proj_resid: number | null;
  best_layer_orientation: number | null;
  n_trajectories: number;
  n_marker_total: number;
  n_trajectories_with_orientation: number;
  n_trajectories_negative_orientation: number;
  chance_level: number;
  layers: AtlasLayer[];
  per_marker: Record<string, PerMarkerSummary>;
  scope?: string | null;
};

export type ConstructionSummary = {
  n_sites: number;
  by_marker: Record<string, {
    n_sites: number;
    best_candidate: string;
    candidates: Record<string, { mean_delta_logp: number; improved_fraction: number }>;
  }>;
  per_site: {
    trajectory: string | null;
    marker: number;
    n_prefix: number;
    baseline_logp: number;
    candidates: Record<string, number>;
  }[];
  alpha_rule?: string | null;
  scope?: string | null;
};

export type TransferCell = {
  mean_delta_logp: number;
  improved_fraction: number;
  n_sites: number;
};

export type TransferSummary = {
  n_sites: number;
  by_marker: Record<string, Record<string, TransferCell>>;
  cross: Record<string, Record<string, TransferCell>>;
  alpha_rule?: string | null;
  scope?: string | null;
};

export type SweepDoseSummary = {
  dose: number;
  mean_delta_logp: number;
  mean_kl: number;
  mean_delta_entropy: number;
  mean_delta_other_marker_mass: number;
  improved_fraction: number;
  n_sites: number;
};

export type SweepSummary = {
  n_sites: number;
  by_marker: Record<string, {
    directions: Record<string, SweepDoseSummary[]>;
    useful_window: { direction?: string | null; dose?: number | null; mean_delta_logp?: number | null; mean_kl?: number | null; kl_threshold?: number };
  }>;
  doses: number[];
  kl_threshold: number;
  scope?: string | null;
};

export type RecipeSummary = {
  n_markers: number;
  markers: Record<string, {
    readout: { best_layer: number | null; raw_cos_auc: number | null; orientation: number | null };
    heldout_transfer: { w: number | null; mean_g: number | null; sparse_g: number | null; oracle: number | null; n_sites: number | null };
    compiled: {
      direction: string;
      dose: number;
      file: string;
      public_url?: string | null;
      expected_delta_logp: number;
      expected_kl: number;
    };
    verification: { n_sites: number; mean_delta_logp: number; mean_kl: number };
    caveats: string[];
  }>;
};

export type SteeringDesign = {
  schema: string;
  complete: boolean;
  scope: string;
  source_paths: Record<string, string>;
  source_hashes: Record<string, string>;
  vector: {
    arm: string | null; injection_block: number; doses: number[]; primary_strength: number;
    baseline: Record<string, unknown>;
  };
  layers: LayerRow[];
  dose: { "w+": DoseRow[]; "w-": DoseRow[]; random_primary: number; note: string };
  factorial: Record<string, SummaryBlock>;
  transfer: Record<string, SummaryBlock | unknown>;
  readout: {
    marker: {
      arith_mean: number; freq_weighted: number; n_ids_positive: number; n_ids: number;
      freq_total: number; per_id: Marker[];
    };
    axes: Record<string, Axis>;
    logit_lens: { per_layer_mean_p_final: number[]; n_steps: number };
    layer_scan: { headline: string | null; calibration: string | null; retracted: string | null; rows: unknown[] };
  };
  readout_atlas: ReadoutAtlasSummary | null;
  construction: ConstructionSummary | null;
  steering_transfer: TransferSummary | null;
  steering_sweep: SweepSummary | null;
  steering_recipe: RecipeSummary | null;
  units: { n_selected: number; per_layer: UnitLayer[]; caveat: string };
  recommendations: Recommendation[];
  unmeasured: string[];
  warnings: string[];
  headline: string;
};

export const ACTION_LABEL: Record<LayerRow["action"], string> = {
  supporting: "与净效应同向",
  compensating: "抵消净效应",
  weak: "未超过地板",
};

export const ACTION_COLOR: Record<LayerRow["action"], string> = {
  supporting: "#2dd4bf",
  compensating: "#fb7185",
  weak: "#64748b",
};

export const fmt = (value: number | null, digits = 4): string => {
  if (value === null || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
};

export const signed = (value: number | null, digits = 4): string => {
  if (value === null || !Number.isFinite(value)) return "—";
  return (value >= 0 ? "+" : "") + value.toFixed(digits);
};

export const pct = (value: number, digits = 1): string => {
  if (!Number.isFinite(value)) return "—";
  return (value * 100).toFixed(digits) + "%";
};

export const isSummaryBlock = (value: unknown): value is SummaryBlock => {
  if (typeof value !== "object" || value === null) return false;
  const block = value as Record<string, unknown>;
  return typeof block.mean === "number" && typeof block.min === "number" && typeof block.max === "number";
};

export const maxAbs = (values: number[]): number => {
  return values.reduce((acc, value) => Math.max(acc, Math.abs(value)), 1e-9);
};

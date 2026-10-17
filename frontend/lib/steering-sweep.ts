export type SweepDose = {
  dose: number;
  n_sites: number;
  mean_delta_logp: number;
  improved_fraction: number;
  mean_kl: number;
  mean_delta_entropy: number;
  mean_delta_other_marker_mass: number;
};

export type UsefulWindow = {
  direction: string | null;
  dose: number | null;
  mean_delta_logp: number | null;
  mean_kl: number | null;
  kl_threshold: number;
};

export type SweepSite = {
  trajectory: string;
  problem: string;
  mode: string;
  t: number;
  marker: number;
  n_prefix: number;
  dose: number;
  alpha: number;
  direction: string;
  base_target_logp: number;
  target_logp: number;
  delta_logp: number;
  target_probability: number;
  other_marker_mass: number;
  delta_other_marker_mass: number;
  kl: number;
  entropy: number;
  base_entropy: number;
  delta_entropy: number;
  top1_id: number;
};

export type Sweep = {
  schema: string;
  complete: boolean;
  scope: string;
  model: { name: string; injection_layer: number; dtype: string; attention: string };
  vector: { path: string; sha256: string };
  markers: number[];
  doses: number[];
  kl_threshold: number;
  splits: Record<string, { calibration: { trajectory: string; t: number; n_prefix: number }[]; heldout: { trajectory: string; t: number; n_prefix: number }[] }>;
  aggregate: Record<string, { directions: Record<string, SweepDose[]> }>;
  useful_window: Record<string, UsefulWindow>;
  sites: SweepSite[];
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

export const DIRECTION_LABEL: Record<string, string> = {
  w: "w",
  minus_w: "−w",
  mean_g: "mean g",
  sparse_g: "sparse g",
  random: "random",
};

export const DIRECTION_COLOR: Record<string, string> = {
  w: "#fb7185",
  minus_w: "#2dd4bf",
  mean_g: "#60a5fa",
  sparse_g: "#fbbf24",
  random: "#94a3b8",
};

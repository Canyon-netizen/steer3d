export type TransferCell = {
  mean_delta_logp: number;
  improved_fraction: number;
  n_sites: number;
};

export type Transfer = {
  schema: string;
  complete: boolean;
  scope: string;
  model: { name: string; injection_layer: number; dtype: string; attention: string };
  vector: { path: string; sha256: string };
  alpha_rule: string;
  splits: Record<string, {
    calibration: { trajectory: string; t: number; n_prefix: number }[];
    heldout: { trajectory: string; t: number; n_prefix: number }[];
  }>;
  same_marker: Record<string, Record<string, TransferCell>>;
  cross: Record<string, Record<string, TransferCell>>;
  cross_rows: { source: number; target: number; trajectory: string; t: number; delta_logp: number }[];
  sites: {
    trajectory: string;
    problem: string;
    mode: string;
    t: number;
    marker: number;
    split: string;
    n_prefix: number;
    alpha: number;
    baseline_logp: number;
    directions: Record<string, { logp: number; delta_logp: number; baseline_logp: number; probability: number }>;
    oracle: { logp: number; delta_logp: number; baseline_logp: number; probability: number };
  }[];
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

export const CANDIDATE_ORDER = ["w", "minus_w", "g_mean", "g_sparse", "random", "oracle_per_site_gradient"];

export const CANDIDATE_LABEL: Record<string, string> = {
  w: "w",
  minus_w: "−w",
  g_mean: "mean g",
  g_sparse: "sparse g",
  random: "random",
  oracle_per_site_gradient: "oracle g",
};

export const CANDIDATE_COLOR: Record<string, string> = {
  w: "#fb7185",
  minus_w: "#2dd4bf",
  g_mean: "#60a5fa",
  g_sparse: "#fbbf24",
  random: "#94a3b8",
  oracle_per_site_gradient: "#a78bfa",
};

export const heatColor = (value: number, limit = 1.5): string => {
  const clamped = Math.max(-1, Math.min(1, value / limit));
  const mix = (a: number[], b: number[], t: number) => {
    const k = Math.max(0, Math.min(1, t));
    return "rgb(" + Math.round(a[0] + (b[0] - a[0]) * k) + "," +
      Math.round(a[1] + (b[1] - a[1]) * k) + "," +
      Math.round(a[2] + (b[2] - a[2]) * k) + ")";
  };
  if (clamped < 0) return mix([248, 250, 252], [30, 64, 175], -clamped);
  return mix([248, 250, 252], [220, 38, 38], clamped);
};

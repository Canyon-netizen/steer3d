export type CandidateResult = {
  logp: number;
  delta_logp: number;
  probability: number;
};

export type UnitPoint = { layer: number; unit: number; response: number; contribution: number };

export type ConstructionSite = {
  trajectory: string;
  problem: string;
  mode: string;
  t: number;
  marker: number;
  n_prefix: number;
  alpha: number;
  baseline_logp: number;
  candidates: Record<string, CandidateResult>;
  gradient: { layer: number; norm: number; cos_with_w: number };
  decomposition: {
    sum_contribution: number;
    measured_delta_w: number;
    ratio: number | null;
    quadrants: { carrier: number; compensator: number; silent: number; neutral: number; threshold: number };
    layers: { layer: number; sum_contribution: number; positive_units: number; negative_units: number; response_max: number; top_carrier_ids: number[]; top_compensator_ids: number[] }[];
    top_carriers: UnitPoint[];
    top_compensators: UnitPoint[];
  };
};

export type MarkerAggregate = {
  n_sites: number;
  candidates: Record<string, { mean_delta_logp: number; improved_fraction: number; n_sites: number }>;
  best_candidate: string;
};

export type Construction = {
  schema: string;
  complete: boolean;
  scope: string;
  model: { name: string; injection_layer: number; dtype: string; attention: string };
  vector: { path: string; sha256: string };
  alpha_rule: string;
  sites: ConstructionSite[];
  scatter: { response: number; contribution: number }[];
  aggregate: Record<string, MarkerAggregate>;
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

export const CANDIDATE_LABEL: Record<string, string> = {
  w: "w",
  minus_w: "−w",
  gradient: "g",
  w_plus_gradient: "w+g",
  w_minus_gradient: "w−g",
  random: "random",
};

export const CANDIDATE_COLOR: Record<string, string> = {
  w: "#fb7185",
  minus_w: "#2dd4bf",
  gradient: "#60a5fa",
  w_plus_gradient: "#fbbf24",
  w_minus_gradient: "#a78bfa",
  random: "#94a3b8",
};

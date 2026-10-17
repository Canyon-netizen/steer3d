export type RecipeVerificationSite = {
  trajectory: string;
  t: number;
  n_prefix: number;
  dose: number;
  alpha: number;
  delta_logp: number;
  kl: number;
  target_probability: number;
  other_marker_mass: number;
};

export type RecipeEntry = {
  target_marker: number;
  readout: { best_layer: number | null; raw_cos_auc: number | null; orientation: number | null };
  heldout_transfer: { w: number | null; mean_g: number | null; sparse_g: number | null; oracle: number | null; n_sites: number | null };
  compiled: {
    direction: string;
    dose: number;
    file: string;
    public_url?: string;
    expected_delta_logp: number;
    expected_kl: number;
    file_sha256?: string;
    norm?: number;
  };
  verification: {
    n_sites: number;
    mean_delta_logp: number;
    mean_kl: number;
    sites: RecipeVerificationSite[];
  };
  caveats: string[];
};

export type Recipe = {
  schema: string;
  complete: boolean;
  scope: string;
  model: { name: string; injection_layer: number; dtype: string; attention: string };
  vector: { path: string; sha256: string };
  alpha_rule: string;
  markers: Record<string, RecipeEntry>;
  source_hashes: Record<string, string>;
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

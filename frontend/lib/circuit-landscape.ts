export type Point = [number, number, number];
export type Arm = "baseline" | "plus" | "minus" | "random" | "block" | "restore";
/**
 * 读数带（docs/STEERING_LEDGER.md T4）。三段必须无缝铺满 [0,1]：
 * floor < 0.01 < transition < 0.05 <= decision <= 0.95 < ceiling。
 */
export type Regime = "floor" | "transition" | "decision" | "ceiling";
export type Unit = {
  id: number; gate: number; value: number; raw_gate: number; natural_product: number;
  product: number; baseline_product: number; regime: string; patched: boolean;
  in_frozen_group: boolean; write_norm: number; response_norm: number; write: Point; writer: Point;
};
export type LayerTrace = {
  states: Record<"incoming" | "input" | "after_attention" | "out", Point>;
  writes: Record<"attention" | "mlp", Point>; units: Unit[]; remainder: Point;
  closure_l2: number; closure_relative: number; displayed_native_units: number; total_native_units: number;
};
export type Site = {
  trajectory: string; t: number; anchor: boolean; prefix_sha256: string; n_prefix_tokens: number;
  next_token: string; context_before: string; context_after: string; alpha: number;
  /** baseline 下读数事件的概率（= exp(marker_logprob)）。旧 payload 没有，组件会自己算。 */
  p_base?: number;
  /** 读数带。旧 payload 没有，组件会自己算。 */
  regime?: Regime;
  regime_label?: string;
  /** 注入位置的残差范数 ‖h‖（alpha / strength） */
  h_norm?: number;
  /** 相对 baseline 的 ΔlogP，按 arm */
  readout_delta?: Partial<Record<Exclude<Arm, "baseline">, number>>;
  /** 信噪比 |Δ(+v)| / |Δ(random)|；随机臂为 0 时为 null */
  snr?: number | null;
  arms: Record<Arm, { readout: { marker_logprob: number; top_tokens: { id: number; text: string; probability: number }[] };
    layers: Record<string, LayerTrace> }>;
};
/** 逐层写入账本的一行（32 site 聚合） */
export type LedgerRow = {
  layer: number; attn_mean: number; mlp_mean: number; attn_share: number;
  dattn_mean: number; dmlp_mean: number; dmlp_over_mlp: number; dattn_over_attn: number;
  n_sites: number; space: string;
};
export type ReadoutSummary = {
  n_sites: number;
  arms: Record<string, { mean: number; min: number; max: number; n_pos: number; n_neg: number }>;
  log_odds?: Record<string, { mean: number; values: number[] }>;
  snr_median: number | null;
};
export type Evidence = {
  schema: string; complete: boolean; model: string; dtype: string; vector_sha256: string;
  strength: number; layers: number[]; arms: Arm[]; scope: string;
  sources: { id: string; problem_id: string; mode: string; anchor: number; prompt_text: string; positions: number[] }[];
  pca: Record<string, { explained_variance: number[]; fit: string }>;
  patch_group: { units_per_layer: number; total_units: number; selection: string };
  guards: { captured_sites: number; captured_forwards: number; max_residual_closure_relative: number;
    baseline_repeat_exact: boolean; identity_patch_exact: boolean; seconds: number;
    trimmed_sig?: number; source_bytes?: number; true_norm_ledger?: boolean; true_norm_note?: string };
  /** 按读数带分开汇总：决策带是头条，底噪带必须标"不可用于行为主张" */
  readout_summary?: Record<string, ReadoutSummary>;
  readout_bands?: { floor: number; decision: number; ceiling: number };
  /** 逐层写入账本（32 site 聚合，不是 site 0） */
  ledger?: { per_layer: LedgerRow[]; space: string; note: string };
  generated_by?: string;
  sites: Site[];
};
export const ARM_LABEL: Record<Arm, string> = { baseline: "原始", plus: "+v", minus: "−v", random: "随机方向", block: "+v 后阻断", restore: "原始中恢复" };
export const ARM_COLOR: Record<Arm, string> = { baseline: "#94a3b8", plus: "#5eead4", minus: "#fb7185", random: "#c4b5fd", block: "#fbbf24", restore: "#60a5fa" };
export const SOURCE_COLOR = ["#5eead4", "#7dd3fc", "#fda4af", "#c4b5fd"];
export const REGIME_LABEL: Record<Regime, string> = {
  floor: "底噪带",
  transition: "过渡带",
  decision: "决策带",
  ceiling: "天花板带",
};
/** 底噪带的数字**不得作为行为主张**（docs/STEERING_LEDGER.md T4）。 */
export const REGIME_BADGE: Record<Regime, { cls: string; claimable: boolean }> = {
  floor: { cls: "bg-slate-800 text-slate-400", claimable: false },
  transition: { cls: "bg-slate-800 text-slate-300", claimable: false },
  decision: { cls: "bg-emerald-950/60 text-emerald-300", claimable: true },
  ceiling: { cls: "bg-amber-950/60 text-amber-300", claimable: false },
};
/**
 * 读数带判定。阈值与 docs/STEERING_LEDGER.md T4 一致，三段无缝铺满 [0,1]。
 * 存在组件里是因为 payload 可能来自旧构建（没有 p_base/regime 字段），
 * 那样至少还能算出带，而不是崩掉。
 */
export const FLOOR_P = 0.01, DECISION_P = 0.05, CEILING_P = 0.95;
export const regimeOf = (p: number): Regime =>
  p < FLOOR_P ? "floor" : p > CEILING_P ? "ceiling" : p < DECISION_P ? "transition" : "decision";
export const add = (a: Point, b: Point): Point => a.map((v,i) => v+b[i]) as Point;
export const subtract = (a: Point, b: Point): Point => a.map((v,i) => v-b[i]) as Point;
export const norm = (a: Point) => Math.hypot(...a);
export const fmt = (value: number, digits = 3) => Number.isFinite(value) ? value.toFixed(digits) : "—";
export const signed = (value: number, digits = 3) => `${value >= 0 ? "+" : ""}${fmt(value,digits)}`;

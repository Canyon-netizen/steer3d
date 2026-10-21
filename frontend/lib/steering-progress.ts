/**
 * 进度图面板的数据类型。
 *
 * 这些类型描述 `frontend/public/latent/data/steering_progress.json`，
 * 该文件由 `backend/examples/build_circuit_landscape.py` 生成。
 *
 * ⚠ 组件里**不允许**出现写死的数字（框架 §8.3 ⑨）：一个写死的数字会静默过期，
 * 而过期的进度图比没有进度图更坏。这里只声明形状。
 */

export type CellState = "done" | "partial" | "missing";

export type MatrixCell = {
  /** done = 已成立且可引用；partial = 有数据但不足以声称；missing = 显式的"未测" */
  state: CellState;
  /** 当前依据：这一格凭什么这么说 */
  here: string;
  /** 本级的门禁：`needs` 解锁的是本级，不是下一级 */
  gate: string;
  /** 最便宜的下一级：升到下一格要做什么 */
  next: string;
};

export type ProgressRow = {
  level: string;
  claim: string;
  needs: string;
  state: CellState;
  here: string;
  note: string;
  /** 作用对象 → 格子。缺 key 表示"该级不按此对象分级"，不是 0。 */
  cells: Record<string, MatrixCell>;
};

export type StageState = "pass" | "fail" | "locked";

export type Stage = {
  id: string;
  title: string;
  goal: string;
  /** 门禁：不达标不进下一阶段 */
  gate: string;
  state: StageState;
  /** 阻塞项（需 GPU 采集等） */
  blocks: string[];
  needs: string;
  /** 这一级产出的文件名（如果有） */
  output?: string;
};

export type ReadoutSummary = {
  n_sites: number;
  arms: Record<string, {
    mean: number; min: number; max: number; n_pos: number; n_neg: number;
  }>;
  log_odds?: Record<string, { mean: number; values: number[] }>;
  snr_median: number | null;
};

export type Progress = {
  schema: string;
  generated_by: string;
  objects: string[];
  rows: ProgressRow[];
  stages: Stage[];
  readout_summary?: Record<string, ReadoutSummary>;
  ladder_source: string | null;
  /** "最高能声称" —— 与 max_level_with_data 是两个量，必须分开印 */
  ladder_max_level_claimed: string | null;
  /** "最高有数据" */
  ladder_max_level_with_data: string | null;
  why_two_numbers: string;
  guards: {
    ladder_found: boolean;
    n_sites: number;
    n_rows: number;
    n_stages: number;
    payload_bytes: number;
  };
};

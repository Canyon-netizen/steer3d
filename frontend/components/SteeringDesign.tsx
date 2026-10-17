"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Em } from "@/components/md";
import { ACTION_COLOR, ACTION_LABEL, fmt, signed, pct, maxAbs } from "@/lib/steering-design";
import type { ConstructionSummary, RecipeSummary, SteeringDesign, LayerRow, ReadoutAtlasSummary, Recommendation, SweepSummary, TransferSummary } from "@/lib/steering-design";

const panel = "rounded-2xl border border-slate-800 bg-slate-900/60";
const smallLabel = "text-[11px] uppercase tracking-wider text-slate-500";

const ACTION_TEXT: Record<string, string> = {
  define_target: "先定义目标 readout",
  avoid_positive_injection: "不要在这里注入 +v",
  test_compensator_removal: "优先测试移除/反转抵消单元",
  do_not_use_as_lever: "不要把这些层当杠杆",
  choose_direction_by_sign: "按目标选择方向符号",
  condition_on_wording: "先固定措辞条件",
  do_not_treat_marker_set_as_one_concept: "不要把 marker 集合当单一概念",
  do_not_use_readout_axis_blindly: "不要盲用读出轴",
  prefer_late_layers_for_answer: "影响最终答案优先用后层",
  replicate_before_building: "先复现再构造",
};

const PRIORITY_COLOR: Record<string, string> = {
  high: "#fb7185",
  medium: "#fbbf24",
  low: "#94a3b8",
};

function Section(props: { title: string; subtitle?: string; children: ReactNode; testid?: string }) {
  return (
    <section className={panel + " p-5"} data-testid={props.testid}>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-base font-medium text-white">{props.title}</h2>
          {props.subtitle ? <p className="mt-1 max-w-3xl text-xs leading-5 text-slate-400">{props.subtitle}</p> : null}
        </div>
      </div>
      <div className="mt-4">{props.children}</div>
    </section>
  );
}

function Stat(props: { label: string; value: string; hint?: string; color?: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-2">
      <div className={smallLabel}>{props.label}</div>
      <div className="mt-1 font-mono text-sm" style={{ color: props.color || "#e2e8f0" }}>{props.value}</div>
      {props.hint ? <div className="mt-1 text-[10px] leading-4 text-slate-500">{props.hint}</div> : null}
    </div>
  );
}

function sameSignCount(values: Record<string, number>, mean: number): string {
  const list = Object.values(values);
  const sign = mean >= 0 ? 1 : -1;
  const same = list.filter((value) => (value >= 0 ? 1 : -1) === sign).length;
  return same + "/" + list.length;
}

function LayerStrategy({ rows }: { rows: LayerRow[] }) {
  const bound = maxAbs(rows.map((row) => row.support));
  return (
    <Section
      title="层策略：哪一层在承载效应，哪一层在抵消"
      subtitle="support = -(block+restore)/2。正值表示该层单元与 +v 的净效应同向；负值表示它们在抵消净效应。block/restore 是组级测量，不是单单元因果。"
      testid="layer-strategy"
    >
      <div className="mb-3 flex flex-wrap gap-4 text-[11px] text-slate-400">
        <span><span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: ACTION_COLOR.supporting }} />支持（与负净效应同向）</span>
        <span><span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: ACTION_COLOR.compensating }} />抵消（可测试移除）</span>
        <span><span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: ACTION_COLOR.weak }} />未超过地板</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-[10px] uppercase text-slate-500">
            <tr>
              <th className="px-2 py-2 font-medium">层</th>
              <th className="px-2 py-2 font-medium">block</th>
              <th className="px-2 py-2 font-medium">restore</th>
              <th className="px-2 py-2 font-medium">support</th>
              <th className="px-2 py-2 font-medium">逐题同号</th>
              <th className="px-2 py-2 font-medium">随机名次</th>
              <th className="px-2 py-2 font-medium">结论</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const width = (Math.abs(row.support) / bound) * 50;
              const left = row.support >= 0 ? 50 : 50 - width;
              const color = ACTION_COLOR[row.action];
              return (
                <tr key={row.layer} className="border-t border-slate-800/70">
                  <td className="px-2 py-2 font-mono text-slate-200">{row.layer}</td>
                  <td className="px-2 py-2 font-mono text-slate-400">{signed(row.block_mean)}</td>
                  <td className="px-2 py-2 font-mono text-slate-400">{signed(row.restore_mean)}</td>
                  <td className="px-2 py-2">
                    <div className="flex items-center gap-2">
                      <div className="relative h-2 w-40 rounded bg-slate-950">
                        <div className="absolute top-0 h-2 rounded" style={{ left: left + "%", width: width + "%", background: color }} />
                        <div className="absolute left-1/2 top-[-2px] h-3 w-px bg-slate-600" />
                      </div>
                      <span className="font-mono" style={{ color: color }}>{signed(row.support)}</span>
                    </div>
                  </td>
                  <td className="px-2 py-2 font-mono text-slate-400">{sameSignCount(row.block_per_problem, row.block_mean)} / {sameSignCount(row.restore_per_problem, row.restore_mean)}</td>
                  <td className="px-2 py-2 font-mono text-slate-400">{row.random_rank}/{row.n_random_groups + 1}</td>
                  <td className="px-2 py-2">
                    <span className="rounded px-2 py-1 text-[10px]" style={{ color: color, background: color + "1a" }}>{ACTION_LABEL[row.action]}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-[11px] leading-5 text-slate-500">
        逐题同号 = block / restore 在 6 道留出题里与本层均值同号的题数；出现 x/6 就说明该层有反向案例。随机名次 = 该层 |support| 在“本层 + 4 个匹配随机组”里的排名（1 = 最大）；名次 2/5 说明方向一致但幅度与最强随机组重叠，当前只当描述性证据。
      </p>
    </Section>
  );
}

function DoseChart({ design }: { design: SteeringDesign }) {
  const plus = design.dose["w+"];
  const minus = design.dose["w-"];
  const values = plus.map((row) => row.mean).concat(minus.map((row) => row.mean)).concat([design.dose.random_primary]);
  const yMin = Math.min(...values, 0);
  const yMax = Math.max(...values, 0);
  const y = (value: number) => 190 - ((value - yMin) / (yMax - yMin || 1)) * 150;
  const x = (index: number, n: number) => 60 + (index * 440) / Math.max(n - 1, 1);
  const points = (rows: { mean: number }[]) => rows.map((row, index) => x(index, rows.length) + "," + y(row.mean)).join(" ");
  return (
    <Section
      title="剂量 / 方向策略"
      subtitle="剂量是注入点 block-input L2 范数的比例。+v 在正确性读数上是负的，−v 在每一档都是正的；随机方向只到主剂量。"
      testid="dose-chart"
    >
      <svg viewBox="0 0 560 220" className="h-auto w-full" role="img" aria-label="dose response">
        <line x1="60" y1={y(0)} x2="500" y2={y(0)} stroke="#334155" strokeDasharray="4 4" />
        <polyline points={points(plus)} fill="none" stroke="#fb7185" strokeWidth="2" />
        <polyline points={points(minus)} fill="none" stroke="#2dd4bf" strokeWidth="2" />
        {rowsMarkers(plus, x, y, "#fb7185")}
        {rowsMarkers(minus, x, y, "#2dd4bf")}
        <text x="60" y="208" fill="#64748b" fontSize="10">0.02</text>
        <text x="272" y="208" fill="#64748b" fontSize="10">0.10</text>
        <text x="480" y="208" fill="#64748b" fontSize="10">0.25</text>
        <text x="60" y="14" fill="#64748b" fontSize="10">score change (correct − incorrect)</text>
        <text x="470" y="30" fill="#fb7185" fontSize="11">+v</text>
        <text x="470" y="46" fill="#2dd4bf" fontSize="11">−v</text>
      </svg>
      <div className="mt-2 grid gap-2 sm:grid-cols-4">
        {plus.map((row, index) => (
          <Stat key={row.dose} label={"dose " + row.dose} value={signed(row.mean)} hint={"n=" + row.n_problems} color="#fb7185" />
        ))}
        <Stat label="random primary" value={signed(design.dose.random_primary)} hint="同剂量随机方向" color="#a78bfa" />
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {Object.entries(design.factorial).map(([name, block]) => (
          <Stat key={name} label={name.replace(/_/g, " / ")} value={signed(block.mean)} hint={"range " + signed(block.min) + " … " + signed(block.max)} />
        ))}
      </div>
    </Section>
  );
}

function rowsMarkers(rows: { mean: number }[], x: (i: number, n: number) => number, y: (v: number) => number, color: string) {
  return rows.map((row, index) => (
    <circle key={index} cx={x(index, rows.length)} cy={y(row.mean)} r="3.5" fill={color} />
  ));
}

function LogitLens({ values, nSteps }: { values: number[]; nSteps: number }) {
  const n = values.length;
  const x = (index: number) => 40 + (index * 480) / Math.max(n - 1, 1);
  const y = (value: number) => 130 - value * 100;
  const points = values.map((value, index) => x(index) + "," + y(value)).join(" ");
  return (
    <Section
      title="读出：最终 token 在哪一层变得可解码"
      subtitle="logit lens 把每层的 hidden state 过最终 RMSNorm + unembedding，看它离模型实际说出的 token 有多远。这是 hidden-state 读出基线，不是因果。"
      testid="logit-lens"
    >
      <svg viewBox="0 0 560 150" className="h-auto w-full" role="img" aria-label="logit lens">
        <line x1="40" y1={y(0)} x2="520" y2={y(0)} stroke="#334155" />
        <line x1={x(18)} y1="20" x2={x(18)} y2="130" stroke="#fbbf24" strokeDasharray="4 3" />
        <polyline points={points} fill="none" stroke="#60a5fa" strokeWidth="2" />
        <text x={x(18) + 4} y="30" fill="#fbbf24" fontSize="10">layer 18</text>
        <text x="40" y="145" fill="#64748b" fontSize="10">layer 0</text>
        <text x="490" y="145" fill="#64748b" fontSize="10">layer {n - 1}</text>
        <text x="40" y="16" fill="#64748b" fontSize="10">mean p(final token)</text>
      </svg>
      <div className="mt-2 grid gap-2 sm:grid-cols-3">
        <Stat label="layer 0" value={pct(values[0], 2)} />
        <Stat label="layer 18" value={pct(values[18] || 0, 2)} color="#fbbf24" />
        <Stat label={"layer " + (n - 1)} value={pct(values[n - 1], 2)} color="#60a5fa" hint={nSteps + " steps"} />
      </div>
    </Section>
  );
}

function ReadoutPanel({ design }: { design: SteeringDesign }) {
  const marker = design.readout.marker;
  const bound = maxAbs(marker.per_id.map((row) => row.dot));
  return (
    <Section
      title="读出通道：这个方向在 unembedding 里指向什么"
      subtitle="静态 w·U 是读出，不是控制。7 个 marker id 全为正，但这不保证注入会抬高它们；下面的轴表说明目前也没有一个既非循环、又专属的读出轴。"
      testid="readout"
    >
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <div className="mb-2 flex flex-wrap gap-4 text-[11px] text-slate-400">
            <span>freq-weighted w·U <b className="font-mono text-teal-300">{signed(marker.freq_weighted, 5)}</b></span>
            <span>{marker.n_ids_positive}/{marker.n_ids} ids positive</span>
          </div>
          <div className="space-y-2">
            {marker.per_id.map((row) => (
              <div key={row.id} className="grid grid-cols-[80px_1fr_110px] items-center gap-2 text-xs">
                <span className="font-mono text-slate-300">{row.id}</span>
                <div className="h-2 rounded bg-slate-950">
                  <div className="h-2 rounded bg-teal-400" style={{ width: (Math.abs(row.dot) / bound) * 100 + "%" }} />
                </div>
                <span className="text-right font-mono text-slate-400">{signed(row.dot)} · {pct(row.share, 0)}</span>
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className={smallLabel}>readout axes</div>
          <table className="mt-2 w-full text-left text-xs">
            <thead className="text-[10px] uppercase text-slate-500">
              <tr><th className="py-1 font-medium">axis</th><th className="py-1 font-medium">status</th><th className="py-1 font-medium">layers</th><th className="py-1 font-medium">best cos</th></tr>
            </thead>
            <tbody>
              {Object.entries(design.readout.axes).map(([name, axis]) => {
                const best = Math.max(...Object.values(axis.per_layer).map((cell) => cell.cos));
                return (
                  <tr key={name} className="border-t border-slate-800/70">
                    <td className="py-1.5 text-slate-300">{name}</td>
                    <td className="py-1.5 text-slate-400">{axis.status}</td>
                    <td className="py-1.5 font-mono text-slate-400">{axis.n_layers_beating_control}/{axis.n_layers}</td>
                    <td className="py-1.5 font-mono text-slate-400">{fmt(best, 3)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <details className="mt-2 text-[11px] leading-5 text-slate-500">
            <summary className="cursor-pointer">注入层扫描：读出与注入不是同一个量</summary>
            <p className="mt-2"><Em s={design.readout.layer_scan.headline || ""} /></p>
            {design.readout.layer_scan.calibration ? <p className="mt-2"><Em s={design.readout.layer_scan.calibration} /></p> : null}
            {design.readout.layer_scan.retracted ? <p className="mt-2 text-amber-300/80"><Em s={design.readout.layer_scan.retracted} /></p> : null}
          </details>
        </div>
      </div>
    </Section>
  );
}

function UnitsPanel({ design }: { design: SteeringDesign }) {
  return (
    <Section
      title="单元策略：选中的 256 个单元"
      subtitle={design.units.caveat}
      testid="units"
    >
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-[10px] uppercase text-slate-500">
            <tr>
              <th className="px-2 py-2 font-medium">层</th>
              <th className="px-2 py-2 font-medium">n</th>
              <th className="px-2 py-2 font-medium">score mean</th>
              <th className="px-2 py-2 font-medium">score range</th>
              <th className="px-2 py-2 font-medium">top unit</th>
            </tr>
          </thead>
          <tbody>
            {design.units.per_layer.map((row) => {
              const top = row.top_units[0];
              return (
                <tr key={row.layer} className="border-t border-slate-800/70">
                  <td className="px-2 py-2 font-mono text-slate-200">{row.layer}</td>
                  <td className="px-2 py-2 font-mono text-slate-400">{row.n}</td>
                  <td className="px-2 py-2 font-mono text-slate-400">{fmt(row.score_mean, 3)}</td>
                  <td className="px-2 py-2 font-mono text-slate-400">{fmt(row.score_min, 2)} … {fmt(row.score_max, 2)}</td>
                  <td className="px-2 py-2 font-mono text-slate-400">{top ? top.unit + " (" + fmt(top.score, 2) + ")" : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function Recommendations({ recs }: { recs: Recommendation[] }) {
  return (
    <Section
      title="设计建议：每条都带证据与置信标签"
      subtitle="measured = 数存在于源产物；descriptive = 方向一致但幅度与随机组重叠。两者都不是统计显著性证明。"
      testid="recommendations"
    >
      <div className="grid gap-3 lg:grid-cols-2">
        {recs.map((rec, index) => {
          const color = PRIORITY_COLOR[rec.priority] || "#94a3b8";
          return (
            <article key={index} className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded px-2 py-0.5 text-[10px] font-medium" style={{ color: color, background: color + "1a" }}>{rec.priority}</span>
                <span className="text-sm font-medium text-slate-100">{ACTION_TEXT[rec.action] || rec.action}</span>
                <span className="ml-auto font-mono text-[10px] text-slate-500">{rec.layer === null ? "global" : "layer " + rec.layer} · {rec.confidence}</span>
              </div>
              <p className="mt-2 text-xs leading-5 text-slate-400">{rec.reason}</p>
              <ul className="mt-2 space-y-1">
                {rec.evidence.map((item, itemIndex) => (
                  <li key={itemIndex} className="font-mono text-[10px] leading-4 text-slate-500">{item}</li>
                ))}
              </ul>
            </article>
          );
        })}
      </div>
    </Section>
  );
}


function ReadoutAtlasPanel({ atlas }: { atlas: ReadoutAtlasSummary }) {
  const layers = atlas.layers;
  const n = layers.length;
  const x = (index: number) => 40 + (index * 480) / Math.max(n - 1, 1);
  const y = (value: number) => 130 - value * 100;
  const line = (key: "mean_auc_cos" | "mean_auc_cos_oriented" | "mean_auc_norm") => layers
    .map((row, index) => {
      const value = row[key];
      return value === null ? null : x(index) + "," + y(value);
    })
    .filter((point): point is string => point !== null)
    .join(" ");
  return (
    <Section
      title="Hidden-state 读出：w·h 在哪一层区分 marker"
      subtitle="把每层 hidden state 投影到 steering 向量 w 上，标签是下一个生成 token 是否为 7 个 marker 之一。raw cos AUC < 0.5 表示 marker 位置的 cos(h,w) 更低；oriented 只是把方向翻过来看的描述性上界。"
      testid="readout-atlas-panel"
    >
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="best layer" value={String(atlas.best_layer)} hint={atlas.best_layer_orientation === -1 ? "orientation −1（反相关）" : "orientation +1"} />
        <Stat label="raw cos AUC" value={atlas.best_layer_mean_auc_cos === null ? "—" : fmt(atlas.best_layer_mean_auc_cos, 4)} hint="< 0.5：marker 处投影更低" color="#fb7185" />
        <Stat label="oriented AUC" value={atlas.best_layer_mean_auc_cos_oriented === null ? "—" : fmt(atlas.best_layer_mean_auc_cos_oriented, 4)} hint={atlas.n_trajectories_negative_orientation + "/" + atlas.n_trajectories_with_orientation + " 条轨迹为负向"} color="#2dd4bf" />
        <Stat label="norm control" value={atlas.best_layer_mean_auc_norm === null ? "—" : fmt(atlas.best_layer_mean_auc_norm, 4)} hint="范数本身的 AUC" color="#94a3b8" />
      </div>
      <svg viewBox="0 0 560 150" className="mt-4 h-auto w-full" role="img" aria-label="readout atlas auc">
        <line x1="40" y1={y(0.5)} x2="520" y2={y(0.5)} stroke="#334155" strokeDasharray="4 4" />
        <line x1={x(atlas.best_layer)} y1="20" x2={x(atlas.best_layer)} y2="130" stroke="#fbbf24" strokeDasharray="4 3" />
        <polyline points={line("mean_auc_cos")} fill="none" stroke="#fb7185" strokeWidth="2" />
        <polyline points={line("mean_auc_cos_oriented")} fill="none" stroke="#2dd4bf" strokeWidth="2" strokeDasharray="5 3" />
        <polyline points={line("mean_auc_norm")} fill="none" stroke="#94a3b8" strokeWidth="1.5" strokeDasharray="2 3" />
        <text x={x(atlas.best_layer) + 4} y="30" fill="#fbbf24" fontSize="10">layer {atlas.best_layer}</text>
        <text x="40" y="145" fill="#64748b" fontSize="10">layer 0</text>
        <text x="490" y="145" fill="#64748b" fontSize="10">layer {n - 1}</text>
        <text x="40" y="16" fill="#64748b" fontSize="10">AUC / chance 0.5</text>
        <text x="420" y="30" fill="#fb7185" fontSize="10">raw cos</text>
        <text x="420" y="44" fill="#2dd4bf" fontSize="10">oriented</text>
        <text x="420" y="58" fill="#94a3b8" fontSize="10">norm</text>
      </svg>
      <div className="mt-3 flex flex-wrap items-center gap-4 text-[11px] text-slate-400">
        <span>n_marker {atlas.n_marker_total} · n_traj {atlas.n_trajectories}</span>
        <span>residualised raw AUC {atlas.best_layer_mean_auc_proj_resid === null ? "—" : fmt(atlas.best_layer_mean_auc_proj_resid, 4)}</span>
        <a href="/readout-atlas" className="text-teal-300 hover:text-teal-200">打开完整 readout atlas →</a>
      </div>
      <div className="mt-4 overflow-x-auto">
        <div className={smallLabel}>per-marker（set-level 曲线掩盖了符号分裂）</div>
        <table className="mt-2 w-full text-left text-xs">
          <thead className="text-[10px] uppercase text-slate-500">
            <tr>
              <th className="px-2 py-1.5 font-medium">marker</th>
              <th className="px-2 py-1.5 font-medium">n</th>
              <th className="px-2 py-1.5 font-medium">best layer</th>
              <th className="px-2 py-1.5 font-medium">raw cos AUC</th>
              <th className="px-2 py-1.5 font-medium">orientation</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(atlas.per_marker)
              .sort((a, b) => b[1].n_occurrences - a[1].n_occurrences)
              .map(([marker, item]) => (
                <tr key={marker} className="border-t border-slate-800/70">
                  <td className="px-2 py-1.5 font-mono text-slate-300">{marker}</td>
                  <td className="px-2 py-1.5 font-mono text-slate-400">{item.n_occurrences}</td>
                  <td className="px-2 py-1.5 font-mono text-slate-400">{item.best_layer === null ? "—" : item.best_layer}</td>
                  <td className="px-2 py-1.5 font-mono" style={{ color: (item.best_layer_orientation || 0) > 0 ? "#2dd4bf" : "#fb7185" }}>{fmt(item.best_layer_mean_auc_cos, 4)}</td>
                  <td className="px-2 py-1.5 font-mono text-slate-400">{item.best_layer_orientation === null ? "—" : item.best_layer_orientation}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[11px] leading-5 text-slate-500">这是描述性统计：per-marker 的符号与最佳层不同（例如 7196 与其余 marker 方向相反），不要用 set-level 曲线单独决定注入层或方向。</p>
    </Section>
  );
}


function ConstructionPanel({ construction }: { construction: ConstructionSummary }) {
  const markers = Object.keys(construction.by_marker).sort();
  return (
    <Section
      title="Construction probe：局部梯度 vs 原向量"
      subtitle="在 6 条短前缀上，把 f = log p(marker) 对 block-20 输入求梯度 g，比较 w、−w、g、w+g、random 在同一 alpha 下对 f 的改变。这是局部白盒测量，不是通用配方。"
      testid="construction-panel"
    >
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-[10px] uppercase text-slate-500">
            <tr>
              <th className="px-2 py-2 font-medium">marker</th>
              <th className="px-2 py-2 font-medium">n</th>
              <th className="px-2 py-2 font-medium">mean Δw</th>
              <th className="px-2 py-2 font-medium">mean Δg</th>
              <th className="px-2 py-2 font-medium">mean Δ(w+g)</th>
              <th className="px-2 py-2 font-medium">best</th>
            </tr>
          </thead>
          <tbody>
            {markers.map((marker) => {
              const item = construction.by_marker[marker];
              const w = item.candidates.w;
              const g = item.candidates.gradient;
              const wg = item.candidates.w_plus_gradient;
              return (
                <tr key={marker} className="border-t border-slate-800/70">
                  <td className="px-2 py-2 font-mono text-slate-300">{marker}</td>
                  <td className="px-2 py-2 font-mono text-slate-400">{item.n_sites}</td>
                  <td className="px-2 py-2 font-mono" style={{ color: (w?.mean_delta_logp || 0) > 0 ? "#2dd4bf" : "#fb7185" }}>{signed(w?.mean_delta_logp ?? null, 5)}</td>
                  <td className="px-2 py-2 font-mono text-sky-300">{signed(g?.mean_delta_logp ?? null, 5)}</td>
                  <td className="px-2 py-2 font-mono text-amber-300">{signed(wg?.mean_delta_logp ?? null, 5)}</td>
                  <td className="px-2 py-2 font-mono text-slate-400">{item.best_candidate}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-4 text-[11px] text-slate-400">
        <span>{construction.n_sites} sites · alpha {construction.alpha_rule}</span>
        <a href="/steering-construction" className="text-teal-300 hover:text-teal-200">打开完整 construction probe →</a>
      </div>
      <p className="mt-2 text-[11px] leading-5 text-slate-500">g 是局部白盒方向；它提高 f 不等于得到一个有语义的 steering vector。unit decomposition 只作诊断，不作 mediation 百分比。</p>
    </Section>
  );
}


function TransferPanel({ transfer }: { transfer: TransferSummary }) {
  const markers = Object.keys(transfer.by_marker).sort();
  const names = ["w", "g_mean", "g_sparse", "random", "oracle_per_site_gradient"];
  const colors: Record<string, string> = { w: "#fb7185", g_mean: "#60a5fa", g_sparse: "#fbbf24", random: "#94a3b8", oracle_per_site_gradient: "#a78bfa" };
  return (
    <Section
      title="Held-out transfer：方向能不能迁移"
      subtitle="每个 marker 用 calibration sites 的梯度均值构造一个方向，在没参与构造的 held-out sites 上评估；cross 矩阵是 source marker 的均值梯度作用到 target marker。"
      testid="transfer-panel"
    >
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-[10px] uppercase text-slate-500">
            <tr>
              <th className="px-2 py-2 font-medium">marker</th>
              {names.map((name) => <th key={name} className="px-2 py-2 font-medium" style={{ color: colors[name] }}>{name}</th>)}
            </tr>
          </thead>
          <tbody>
            {markers.map((marker) => (
              <tr key={marker} className="border-t border-slate-800/70">
                <td className="px-2 py-2 font-mono text-slate-300">{marker}</td>
                {names.map((name) => {
                  const cell = transfer.by_marker[marker]?.[name];
                  return <td key={name} className="px-2 py-2 font-mono" style={{ color: colors[name] }}>{cell ? signed(cell.mean_delta_logp, 4) : "—"}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4">
        <div className={smallLabel}>cross-marker mean g</div>
        <div className="mt-2 inline-grid gap-1 text-[10px]" style={{ gridTemplateColumns: "44px repeat(" + markers.length + ", 72px)" }}>
          <span />
          {markers.map((target) => <span key={"h" + target} className="text-center font-mono text-slate-500">{target}</span>)}
          {markers.map((source) => (
            <div key={source} className="contents">
              <span className="font-mono text-slate-500">{source}</span>
              {markers.map((target) => {
                const cell = transfer.cross[source]?.[target];
                if (!cell) return <span key={target} className="rounded bg-slate-950 px-1 py-1 text-center text-slate-700">—</span>;
                const alpha = Math.min(0.55, Math.abs(cell.mean_delta_logp) / 1.5 * 0.55);
                const bg = cell.mean_delta_logp >= 0 ? "rgba(45,212,191," + alpha + ")" : "rgba(251,113,133," + alpha + ")";
                return <span key={target} className="rounded px-1 py-1 text-center font-mono" style={{ background: bg }}>{signed(cell.mean_delta_logp, 2)}</span>;
              })}
            </div>
          ))}
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-4 text-[11px] text-slate-400">
        <span>{transfer.n_sites} held-out sites · alpha {transfer.alpha_rule}</span>
        <a href="/steering-transfer" className="text-teal-300 hover:text-teal-200">打开完整 held-out transfer →</a>
      </div>
      <p className="mt-2 text-[11px] leading-5 text-slate-500">每个 marker 只有 2 个 calibration + 2 个 held-out site；cross 只有 2 个/格。描述性证据，不是统计显著结论。</p>
    </Section>
  );
}


function SweepPanel({ sweep }: { sweep: SweepSummary }) {
  const markers = Object.keys(sweep.by_marker).sort();
  return (
    <Section
      title="Alpha / side-effect：效果 vs 副作用窗口"
      subtitle="在 held-out site 上扫描 dose；mean KL 是完整 softmax 对 baseline 的 KL。这里不是找最强剂量，而是找 KL 预算内可用的 direction/dose。"
      testid="sweep-panel"
    >
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-[10px] uppercase text-slate-500">
            <tr>
              <th className="px-2 py-2 font-medium">marker</th>
              <th className="px-2 py-2 font-medium">useful direction</th>
              <th className="px-2 py-2 font-medium">dose</th>
              <th className="px-2 py-2 font-medium">mean Δlogp</th>
              <th className="px-2 py-2 font-medium">mean KL</th>
            </tr>
          </thead>
          <tbody>
            {markers.map((marker) => {
              const window = sweep.by_marker[marker].useful_window;
              return (
                <tr key={marker} className="border-t border-slate-800/70">
                  <td className="px-2 py-2 font-mono text-slate-300">{marker}</td>
                  <td className="px-2 py-2 font-mono text-slate-400">{window.direction ?? "—"}</td>
                  <td className="px-2 py-2 font-mono text-slate-400">{window.dose ?? "—"}</td>
                  <td className="px-2 py-2 font-mono text-teal-300">{signed(window.mean_delta_logp ?? null, 4)}</td>
                  <td className="px-2 py-2 font-mono text-slate-400">{fmt(window.mean_kl ?? null, 4)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-4 text-[11px] text-slate-400">
        <span>{sweep.n_sites} held-out sites · KL threshold {sweep.kl_threshold}</span>
        <a href="/steering-sweep" className="text-teal-300 hover:text-teal-200">打开完整 dose / side-effect sweep →</a>
      </div>
      <p className="mt-2 text-[11px] leading-5 text-slate-500">mean g 的 Δlogp 更大但 KL 也大；sparse g 在相同 dose 下 KL 更低；w 最安全但更弱。高 dose 的 −w 极端 off-manifold，不能当方向有效的证据。</p>
    </Section>
  );
}


function RecipePanel({ recipe }: { recipe: RecipeSummary }) {
  const markers = Object.keys(recipe.markers).sort();
  return (
    <Section
      title="Compiled recipe：每个 marker 的候选向量"
      subtitle="从 readout atlas 选层、calibration 平均梯度构造方向、sweep 选 KL 预算内 dose，并保存为 .npy；在 held-out site 上验证。"
      testid="recipe-panel"
    >
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-[10px] uppercase text-slate-500">
            <tr>
              <th className="px-2 py-2 font-medium">marker</th>
              <th className="px-2 py-2 font-medium">direction</th>
              <th className="px-2 py-2 font-medium">dose</th>
              <th className="px-2 py-2 font-medium">expected Δ / KL</th>
              <th className="px-2 py-2 font-medium">verified Δ / KL</th>
              <th className="px-2 py-2 font-medium">file</th>
            </tr>
          </thead>
          <tbody>
            {markers.map((marker) => {
              const entry = recipe.markers[marker];
              const compiled = entry.compiled;
              const verification = entry.verification;
              return (
                <tr key={marker} className="border-t border-slate-800/70">
                  <td className="px-2 py-2 font-mono text-slate-300">{marker}</td>
                  <td className="px-2 py-2 font-mono text-sky-300">{compiled.direction}</td>
                  <td className="px-2 py-2 font-mono text-slate-400">{compiled.dose}</td>
                  <td className="px-2 py-2 font-mono text-teal-300">{signed(compiled.expected_delta_logp, 4)} / {fmt(compiled.expected_kl, 4)}</td>
                  <td className="px-2 py-2 font-mono text-amber-300">{signed(verification.mean_delta_logp, 4)} / {fmt(verification.mean_kl, 4)}</td>
                  <td className="px-2 py-2 font-mono"><a className="text-teal-300 hover:text-teal-200" href={compiled.public_url || "#"} download>{compiled.file.split("/").pop()}</a></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-4 text-[11px] text-slate-400">
        <span>{recipe.n_markers} compiled markers · verification reuses the transfer/sweep held-out sites</span>
        <a href="/steering-recipe" className="text-teal-300 hover:text-teal-200">打开完整 compiled recipe →</a>
      </div>
      <p className="mt-2 text-[11px] leading-5 text-slate-500">这些是本地白盒候选方向，不是生产级向量；换前缀/层/剂量前必须重新验证。</p>
    </Section>
  );
}

export default function SteeringDesignPage() {
  const [data, setData] = useState<SteeringDesign | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetch("/latent/data/steering_design.json", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then((json: SteeringDesign) => {
        if (json.schema !== "steer3d.steering_design/1" || !json.complete || !json.layers.length) {
          throw new Error("采集未完成或数据格式不匹配");
        }
        setData(json);
      })
      .catch((reason) => {
        if (reason.name !== "AbortError") setError(reason.message);
      });
    return () => controller.abort();
  }, []);

  const baseline = useMemo(() => {
    if (!data) return "";
    const block = data.vector.baseline;
    const p = typeof block.p_correct === "number" ? pct(block.p_correct, 1) : "—";
    return "P(correct) = " + p;
  }, [data]);

  if (error) {
    return <main className="min-h-screen bg-slate-950 p-10 text-rose-300">数据加载失败：{error}</main>;
  }
  if (!data) {
    return <main className="min-h-screen bg-slate-950 p-10 text-slate-400">正在读取设计指南…</main>;
  }

  return (
    <main className="min-h-screen bg-[#080e1a] px-4 py-6 text-slate-200 sm:px-8" data-testid="steering-design">
      <div className="mx-auto max-w-[1500px] space-y-5">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[11px] uppercase tracking-[.23em] text-teal-400">Hidden states × vector design</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Steering Design Guide</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
              从现有 hidden-state 读数、原生单元干预与 logit lens 产物生成的设计指南。它不重跑模型，只把“哪一层承载效应、哪一层抵消、该选什么方向/剂量/层”连同证据一起摆出来。
            </p>
          </div>
          <nav className="flex gap-4 pt-2 text-xs text-slate-400">
            <a className="hover:text-teal-300" href="/">实时轨迹</a>
            <a className="hover:text-teal-300" href="/circuit-landscape">状态与原生 circuit</a>
            <a className="hover:text-teal-300" href="/readout-atlas">hidden-state 读出</a>
            <a className="hover:text-teal-300" href="/steering-construction">构造 probe</a>
            <a className="hover:text-teal-300" href="/steering-transfer">held-out 迁移</a>
            <a className="hover:text-teal-300" href="/steering-sweep">剂量/副作用</a>
            <a className="hover:text-teal-300" href="/steering-recipe">编译 recipe</a>
            <a className="hover:text-teal-300" href="/steering-workbench.html">总工作台</a>
            <a className="hover:text-teal-300" href="/bpath-explorer">向量响应实验</a>
            <a className="hover:text-teal-300" href="/latent/index.html">隐空间观察台</a>
          </nav>
        </header>

        <section className={panel + " p-5"}>
          <p className="text-sm leading-6 text-slate-200">{data.headline}</p>
          <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="vector arm" value={data.vector.arm || "—"} hint={"injection block " + data.vector.injection_block} />
            <Stat label="primary dose" value={String(data.vector.primary_strength)} hint={baseline} />
            <Stat label="marker readout" value={signed(data.readout.marker.freq_weighted, 5)} hint={data.readout.marker.n_ids_positive + "/" + data.readout.marker.n_ids + " ids positive"} />
            <Stat label="+v primary effect" value={signed(data.layers[0].net_effect_primary, 5)} hint={"n=" + data.layers[0].n_problems + " held-out problems"} color="#fb7185" />
          </div>
        </section>

        <LayerStrategy rows={data.layers} />
        <DoseChart design={data} />
        <LogitLens values={data.readout.logit_lens.per_layer_mean_p_final} nSteps={data.readout.logit_lens.n_steps} />
        {data.readout_atlas ? <ReadoutAtlasPanel atlas={data.readout_atlas} /> : null}
        {data.construction ? <ConstructionPanel construction={data.construction} /> : null}
        {data.steering_transfer ? <TransferPanel transfer={data.steering_transfer} /> : null}
        {data.steering_sweep ? <SweepPanel sweep={data.steering_sweep} /> : null}
        {data.steering_recipe ? <RecipePanel recipe={data.steering_recipe} /> : null}
        <ReadoutPanel design={data} />
        <UnitsPanel design={data} />
        <Recommendations recs={data.recommendations} />

        <Section title="还没有测的东西" subtitle="这些是把“诊断”变成“构造配方”之前必须补的测量；当前指南不假装它们存在。" testid="unmeasured">
          <ul className="grid gap-2 text-xs leading-5 text-slate-400 lg:grid-cols-2">
            {data.unmeasured.map((item, index) => (
              <li key={index} className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">{item}</li>
            ))}
          </ul>
          <div className="mt-4 space-y-2">
            {data.warnings.map((item, index) => (
              <p key={index} className="text-[11px] leading-5 text-amber-300/80">{item}</p>
            ))}
          </div>
        </Section>

        <footer className={panel + " p-4 text-[10px] leading-5 text-slate-500"}>
          <div>schema {data.schema} · {data.scope}</div>
          <div className="mt-1 break-all font-mono">
            {Object.entries(data.source_paths).map(([name, path]) => (
              <span key={name} className="mr-3">{name}: {path}</span>
            ))}
          </div>
        </footer>
      </div>
    </main>
  );
}

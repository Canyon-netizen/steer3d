"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { colorFor, fmt } from "@/lib/readout-atlas";
import type { AtlasLayer, AtlasSeries, ReadoutAtlas } from "@/lib/readout-atlas";

const panel = "rounded-2xl border border-slate-800 bg-slate-900/60";
const smallLabel = "text-[11px] uppercase tracking-wider text-slate-500";

function Section(props: { title: string; subtitle?: string; children: ReactNode; testid?: string }) {
  return (
    <section className={panel + " p-5"} data-testid={props.testid}>
      <h2 className="text-base font-medium text-white">{props.title}</h2>
      {props.subtitle ? <p className="mt-1 max-w-4xl text-xs leading-5 text-slate-400">{props.subtitle}</p> : null}
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

function AucCurve({ atlas }: { atlas: ReadoutAtlas }) {
  const layers = atlas.aggregate.layers;
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
    <svg viewBox="0 0 560 150" className="h-auto w-full" role="img" aria-label="readout atlas auc">
      <line x1="40" y1={y(0.5)} x2="520" y2={y(0.5)} stroke="#334155" strokeDasharray="4 4" />
      <line x1={x(atlas.aggregate.best_layer)} y1="20" x2={x(atlas.aggregate.best_layer)} y2="130" stroke="#fbbf24" strokeDasharray="4 3" />
      <polyline points={line("mean_auc_cos")} fill="none" stroke="#fb7185" strokeWidth="2" />
      <polyline points={line("mean_auc_cos_oriented")} fill="none" stroke="#2dd4bf" strokeWidth="2" strokeDasharray="5 3" />
      <polyline points={line("mean_auc_norm")} fill="none" stroke="#94a3b8" strokeWidth="1.5" strokeDasharray="2 3" />
      <text x={x(atlas.aggregate.best_layer) + 4} y="30" fill="#fbbf24" fontSize="10">layer {atlas.aggregate.best_layer}</text>
      <text x="40" y="145" fill="#64748b" fontSize="10">layer 0</text>
      <text x="490" y="145" fill="#64748b" fontSize="10">layer {n - 1}</text>
      <text x="40" y="16" fill="#64748b" fontSize="10">AUC / chance 0.5</text>
      <text x="420" y="30" fill="#fb7185" fontSize="10">raw cos</text>
      <text x="420" y="44" fill="#2dd4bf" fontSize="10">oriented</text>
      <text x="420" y="58" fill="#94a3b8" fontSize="10">norm</text>
    </svg>
  );
}

function Heatmap(props: {
  series: AtlasSeries;
  channel: "cos" | "proj" | "norm";
  selected: number;
  onSelect: (token: number) => void;
}) {
  const matrix = props.series[props.channel];
  const total = props.series.T;
  const maxColumns = 320;
  const stride = Math.max(1, Math.ceil(total / maxColumns));
  const columns = Math.ceil(total / stride);
  const left = 56;
  const top = 22;
  const width = 900;
  const height = 28 * 13;
  const cellWidth = (width - left - 10) / columns;
  const cellHeight = height / 28;

  const scale = useMemo(() => {
    let maximum = 0;
    for (let t = 0; t < total; t += 1) {
      for (let layer = 0; layer < 28; layer += 1) {
        maximum = Math.max(maximum, Math.abs(matrix[t][layer]));
      }
    }
    return props.channel === "cos" ? Math.max(maximum, 0.05) : maximum;
  }, [matrix, total, props.channel]);

  const cellValue = (layer: number, column: number) => {
    let sum = 0;
    let count = 0;
    const start = column * stride;
    const end = Math.min(total, start + stride);
    for (let t = start; t < end; t += 1) {
      sum += matrix[t][layer];
      count += 1;
    }
    return count === 0 ? 0 : sum / count;
  };

  const click = (event: React.MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * (width + left);
    const column = Math.max(0, Math.min(columns - 1, Math.floor((x - left) / cellWidth)));
    props.onSelect(Math.min(total - 1, column * stride + Math.floor(stride / 2)));
  };

  const selectedColumn = Math.floor(props.selected / stride);
  return (
    <svg viewBox={"0 0 " + (width + left) + " " + (height + top + 24)} className="h-auto w-full" role="img" aria-label="cosine heatmap" onClick={click} style={{ cursor: "crosshair" }}>
      {Array.from({ length: 28 }).map((_, layer) => (
        <g key={layer}>
          <text x={left - 6} y={top + layer * cellHeight + cellHeight * 0.8} textAnchor="end" fill="#64748b" fontSize="9">{layer}</text>
          {Array.from({ length: columns }).map((__, column) => (
            <rect
              key={column}
              x={left + column * cellWidth}
              y={top + layer * cellHeight}
              width={Math.max(1, cellWidth)}
              height={Math.max(1, cellHeight)}
              fill={colorFor(cellValue(layer, column), props.channel, scale)}
            />
          ))}
        </g>
      ))}
      {props.series.marker_positions.map((position) => {
        const column = Math.floor(position / stride);
        return <line key={position} x1={left + column * cellWidth} y1={top} x2={left + column * cellWidth} y2={top + height} stroke="#111827" strokeWidth="0.6" opacity="0.85" />;
      })}
      <line x1={left + selectedColumn * cellWidth} y1={top} x2={left + selectedColumn * cellWidth} y2={top + height} stroke="#fbbf24" strokeWidth="1.5" />
      <text x={left} y={height + top + 18} fill="#64748b" fontSize="9">token 0</text>
      <text x={width - 40} y={height + top + 18} fill="#64748b" fontSize="9">token {total - 1}</text>
      <text x={left} y={12} fill="#64748b" fontSize="9">rows = layers 0-27; black ticks = marker next-token; click to inspect</text>
    </svg>
  );
}

function LayerTable({ layers }: { layers: AtlasLayer[] }) {
  return (
    <div className="max-h-72 overflow-auto rounded-xl border border-slate-800">
      <table className="w-full text-left text-xs">
        <thead className="sticky top-0 bg-slate-950 text-[10px] uppercase text-slate-500">
          <tr>
            <th className="px-2 py-2 font-medium">layer</th>
            <th className="px-2 py-2 font-medium">raw cos</th>
            <th className="px-2 py-2 font-medium">oriented</th>
            <th className="px-2 py-2 font-medium">norm</th>
            <th className="px-2 py-2 font-medium">resid raw</th>
            <th className="px-2 py-2 font-medium">neg traj</th>
            <th className="px-2 py-2 font-medium">n marker</th>
          </tr>
        </thead>
        <tbody>
          {layers.map((row) => (
            <tr key={row.layer} className="border-t border-slate-800/70">
              <td className="px-2 py-1.5 font-mono text-slate-300">{row.layer}</td>
              <td className="px-2 py-1.5 font-mono text-slate-400">{fmt(row.mean_auc_cos)}</td>
              <td className="px-2 py-1.5 font-mono text-slate-400">{fmt(row.mean_auc_cos_oriented)}</td>
              <td className="px-2 py-1.5 font-mono text-slate-400">{fmt(row.mean_auc_norm)}</td>
              <td className="px-2 py-1.5 font-mono text-slate-400">{fmt(row.mean_auc_proj_resid)}</td>
              <td className="px-2 py-1.5 font-mono text-slate-400">{row.n_trajectories_negative_orientation}/{row.n_trajectories_with_orientation}</td>
              <td className="px-2 py-1.5 font-mono text-slate-400">{row.n_marker}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ReadoutAtlasPage() {
  const [data, setData] = useState<ReadoutAtlas | null>(null);
  const [error, setError] = useState("");
  const [seriesIndex, setSeriesIndex] = useState(0);
  const [channel, setChannel] = useState<"cos" | "proj" | "norm">("cos");
  const [selected, setSelected] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/latent/data/readout_atlas.json", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then((json: ReadoutAtlas) => {
        if (json.schema !== "steer3d.readout_atlas/1" || !json.complete || !json.series.length) {
          throw new Error("atlas 未完成或格式不匹配");
        }
        setData(json);
        setSelected(json.series[0].n_marker > 0 ? json.series[0].marker_positions[0] : 0);
      })
      .catch((reason) => {
        if (reason.name !== "AbortError") setError(reason.message);
      });
    return () => controller.abort();
  }, []);

  const series = data ? data.series[Math.min(seriesIndex, data.series.length - 1)] : null;
  const token = series ? Math.max(0, Math.min(selected, series.T - 1)) : 0;

  if (error) return <main className="min-h-screen bg-slate-950 p-10 text-rose-300">数据加载失败：{error}</main>;
  if (!data || !series) return <main className="min-h-screen bg-slate-950 p-10 text-slate-400">正在读取 readout atlas…</main>;

  const atlas = data.aggregate;
  const nextToken = series.tokens && series.tokens[token] !== undefined ? series.tokens[token] : "id " + series.token_ids[token];
  const markerNext = token < series.marker_mask.length ? series.marker_mask[token] === 1 : false;
  const top1 = series.top1_ids && series.top1_ids[token] !== undefined ? series.top1_ids[token] : null;
  const layerRows = [20, 21, 25].filter((layer) => layer < series.cos[0].length);

  return (
    <main className="min-h-screen bg-[#080e1a] px-4 py-6 text-slate-200 sm:px-8" data-testid="readout-atlas">
      <div className="mx-auto max-w-[1500px] space-y-5">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[11px] uppercase tracking-[.23em] text-teal-400">Hidden states × readout atlas</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Readout Atlas</h1>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-400">
              把每条轨迹每一层的 hidden state 投影到 steering 向量 w 上，标签是下一个生成 token 是否为 7 个 marker 之一。这里展示的是 <b className="text-slate-200">读出</b>：它告诉你 w·h 在哪一层有区分度、方向是正还是负；它不证明因果。
            </p>
          </div>
          <nav className="flex gap-4 pt-2 text-xs text-slate-400">
            <a className="hover:text-teal-300" href="/">实时轨迹</a>
            <a className="hover:text-teal-300" href="/circuit-landscape">状态与原生 circuit</a>
            <a className="hover:text-teal-300" href="/steering-design">向量设计指南</a>
            <a className="hover:text-teal-300" href="/latent/index.html">隐空间观察台</a>
          </nav>
        </header>

        <section className={panel + " p-5"}>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="best layer" value={String(atlas.best_layer)} hint={"orientation " + (atlas.best_layer_orientation === null ? "—" : atlas.best_layer_orientation)} />
            <Stat label="raw cos AUC" value={fmt(atlas.best_layer_mean_auc_cos)} hint="< 0.5：marker 处投影更低" color="#fb7185" />
            <Stat label="oriented AUC" value={fmt(atlas.best_layer_mean_auc_cos_oriented)} hint={atlas.n_trajectories_negative_orientation + "/" + atlas.n_trajectories_with_orientation + " 条轨迹为负向"} color="#2dd4bf" />
            <Stat label="norm control" value={fmt(atlas.best_layer_mean_auc_norm)} hint="范数本身的 AUC" color="#94a3b8" />
          </div>
          <div className="mt-3 text-[11px] leading-5 text-slate-500">
            n_marker {atlas.n_marker_total} · n_traj {atlas.n_trajectories} · n_positions {atlas.n_positions_total} · chance {atlas.chance_level} · residualised raw AUC {fmt(atlas.best_layer_mean_auc_proj_resid)}
          </div>
        </section>

        <Section title="层曲线：raw / oriented / norm" subtitle="raw cos AUC 低于 0.5 表示 marker 位置的 cos(h,w) 更低；oriented 是把方向翻过来看的描述性上界；norm 是混杂控制。" testid="readout-atlas-curve">
          <AucCurve atlas={data} />
        </Section>

        <Section title="逐 token 热图" subtitle="颜色是 cos(h,w)（可切换 proj / norm）；黑线是下一个 token 为 marker 的位置；黄线是当前选中 token。点击热图可切换 token。" testid="readout-atlas-heatmap">
          <div className="mb-3 flex flex-wrap gap-2">
            {data.series.map((item, index) => (
              <button key={item.id} onClick={() => { setSeriesIndex(index); setSelected(item.n_marker > 0 ? item.marker_positions[0] : 0); }} className={"rounded-lg border px-3 py-1.5 text-xs " + (index === seriesIndex ? "border-teal-500 bg-teal-500/10 text-teal-300" : "border-slate-700 text-slate-400")}>
                {item.id} · {item.mode} · {item.n_marker} markers
              </button>
            ))}
            <span className="mx-2 h-6 w-px bg-slate-700" />
            {(["cos", "proj", "norm"] as const).map((item) => (
              <button key={item} onClick={() => setChannel(item)} className={"rounded-lg border px-3 py-1.5 text-xs " + (channel === item ? "border-sky-500 bg-sky-500/10 text-sky-300" : "border-slate-700 text-slate-400")}>
                {item}
              </button>
            ))}
          </div>
          <Heatmap series={series} channel={channel} selected={token} onSelect={setSelected} />
          <div className="mt-3 grid gap-3 rounded-xl border border-slate-800 bg-slate-950/50 p-4 text-xs sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="token" value={String(token)} hint={nextToken + (top1 === null ? "" : " · top1 " + top1)} />
            <Stat label="next is marker" value={markerNext ? "yes" : "no"} />
            {layerRows.map((layer) => (
              <Stat key={layer} label={"layer " + layer} value={"cos " + fmt(series.cos[token][layer], 3)} hint={"proj " + fmt(series.proj[token][layer], 2)} />
            ))}
          </div>
        </Section>

        <Section title="Per-marker readout" subtitle="set-level AUC 会把符号相反的 marker 混在一起；这张表按 marker 分开，给出各自的 n、最佳层、raw/oriented AUC 与方向。" testid="readout-atlas-per-marker">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-[10px] uppercase text-slate-500">
                <tr>
                  <th className="px-2 py-2 font-medium">marker</th>
                  <th className="px-2 py-2 font-medium">n</th>
                  <th className="px-2 py-2 font-medium">n traj</th>
                  <th className="px-2 py-2 font-medium">best layer</th>
                  <th className="px-2 py-2 font-medium">raw cos AUC</th>
                  <th className="px-2 py-2 font-medium">oriented</th>
                  <th className="px-2 py-2 font-medium">orientation</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.per_marker)
                  .sort((a, b) => b[1].n_occurrences - a[1].n_occurrences)
                  .map(([marker, item]) => (
                    <tr key={marker} className="border-t border-slate-800/70">
                      <td className="px-2 py-2 font-mono text-slate-300">{marker}</td>
                      <td className="px-2 py-2 font-mono text-slate-400">{item.n_occurrences}</td>
                      <td className="px-2 py-2 font-mono text-slate-400">{item.n_trajectories}</td>
                      <td className="px-2 py-2 font-mono text-slate-400">{item.best_layer === null ? "—" : item.best_layer}</td>
                      <td className="px-2 py-2 font-mono" style={{ color: (item.best_layer_orientation || 0) > 0 ? "#2dd4bf" : "#fb7185" }}>{fmt(item.best_layer_mean_auc_cos)}</td>
                      <td className="px-2 py-2 font-mono text-slate-400">{fmt(item.best_layer_mean_auc_cos_oriented)}</td>
                      <td className="px-2 py-2 font-mono text-slate-400">{item.best_layer_orientation === null ? "—" : item.best_layer_orientation}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </Section>

        <Section title="逐层统计" subtitle="所有轨迹等权平均；n_trajectories_with_both_classes 才是 AUC 的有效轨迹数。" testid="readout-atlas-table">
          <LayerTable layers={atlas.layers} />
        </Section>

        <footer className={panel + " p-4 text-[10px] leading-5 text-slate-500"}>
          <div>schema {data.schema} · {data.scope}</div>
          <div className="mt-1 break-all font-mono">vector {data.vector.sha256} · {data.vector.path}</div>
          <div className="mt-1">guards {JSON.stringify(data.guards)}</div>
        </footer>
      </div>
    </main>
  );
}

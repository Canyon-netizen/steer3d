"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { DIRECTION_COLOR, DIRECTION_LABEL, fmt, signed } from "@/lib/steering-sweep";
import type { Sweep, SweepDose } from "@/lib/steering-sweep";

const panel = "rounded-2xl border border-slate-800 bg-slate-900/60";
const smallLabel = "text-[11px] uppercase tracking-wider text-slate-500";
const DIRECTIONS = ["w", "minus_w", "mean_g", "sparse_g", "random"];
const PLOT_DIRECTIONS = ["w", "mean_g", "sparse_g", "random"];

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

function LineChart(props: { marker: string; sweep: Sweep; metric: "mean_delta_logp" | "mean_kl" }) {
  const rows = props.sweep.aggregate[props.marker].directions;
  const doses = props.sweep.doses;
  const directions = props.metric === "mean_delta_logp" ? PLOT_DIRECTIONS : ["mean_g", "sparse_g"];
  const values: number[] = [];
  for (const direction of directions) {
    for (const row of rows[direction] ?? []) values.push(row[props.metric]);
  }
  const yMin = Math.min(...values, 0);
  const yMax = Math.max(...values, 0.001);
  const width = 520;
  const height = 220;
  const left = 50;
  const top = 20;
  const x = (dose: number) => left + (doses.indexOf(dose) / Math.max(doses.length - 1, 1)) * (width - left - 20);
  const y = (value: number) => {
    if (props.metric === "mean_kl") {
      const logMin = Math.log10(Math.max(Math.min(...values.filter((item) => item > 0)), 1e-4));
      const logMax = Math.log10(Math.max(...values, 1e-3));
      return top + (logMax - Math.log10(Math.max(value, 1e-5))) / Math.max(logMax - logMin, 1e-6) * (height - top - 30);
    }
    return top + (yMax - value) / Math.max(yMax - yMin, 1e-9) * (height - top - 30);
  };
  const line = (direction: string) => (rows[direction] ?? []).map((row) => x(row.dose) + "," + y(row[props.metric])).join(" ");
  return (
    <svg viewBox={"0 0 " + width + " " + height} className="h-auto w-full" role="img" aria-label={props.metric}>
      <line x1={left} y1={y(0)} x2={width - 20} y2={y(0)} stroke="#334155" />
      <line x1={left} y1={top} x2={left} y2={height - 30} stroke="#334155" />
      {directions.map((direction) => (
        <polyline key={direction} points={line(direction)} fill="none" stroke={DIRECTION_COLOR[direction]} strokeWidth="2" />
      ))}
      <text x={left} y={height - 8} fill="#64748b" fontSize="10">dose (fraction of input norm)</text>
      <text x="8" y={top + 10} fill="#64748b" fontSize="10">{props.metric === "mean_kl" ? "KL (log)" : "delta log p"}</text>
      {directions.map((direction, index) => (
        <text key={direction} x={width - 130} y={top + 12 + index * 13} fill={DIRECTION_COLOR[direction]} fontSize="10">{DIRECTION_LABEL[direction]}</text>
      ))}
    </svg>
  );
}

function DirectionTable(props: { marker: string; sweep: Sweep }) {
  const aggregate = props.sweep.aggregate[props.marker];
  const window = props.sweep.useful_window[props.marker];
  return (
    <div className="max-h-96 overflow-auto rounded-xl border border-slate-800">
      <table className="w-full text-left text-xs">
        <thead className="sticky top-0 bg-slate-950 text-[10px] uppercase text-slate-500">
          <tr>
            <th className="px-2 py-2 font-medium">direction</th>
            <th className="px-2 py-2 font-medium">dose</th>
            <th className="px-2 py-2 font-medium">Δlogp</th>
            <th className="px-2 py-2 font-medium">improved</th>
            <th className="px-2 py-2 font-medium">KL</th>
            <th className="px-2 py-2 font-medium">Δentropy</th>
            <th className="px-2 py-2 font-medium">Δother mass</th>
          </tr>
        </thead>
        <tbody>
          {DIRECTIONS.map((direction) => (
            (aggregate.directions[direction] ?? []).map((row: SweepDose) => {
              const selected = window.direction === direction && window.dose === row.dose;
              return (
                <tr key={direction + ":" + row.dose} className={"border-t border-slate-800/70 " + (selected ? "bg-teal-500/10" : "")}>
                  <td className="px-2 py-1.5 font-mono" style={{ color: DIRECTION_COLOR[direction] }}>{DIRECTION_LABEL[direction]}</td>
                  <td className="px-2 py-1.5 font-mono text-slate-400">{row.dose}</td>
                  <td className="px-2 py-1.5 font-mono text-slate-200">{signed(row.mean_delta_logp, 4)}</td>
                  <td className="px-2 py-1.5 font-mono text-slate-400">{Math.round(row.improved_fraction * 100)}%</td>
                  <td className="px-2 py-1.5 font-mono text-slate-400">{fmt(row.mean_kl, 4)}</td>
                  <td className="px-2 py-1.5 font-mono text-slate-400">{signed(row.mean_delta_entropy, 4)}</td>
                  <td className="px-2 py-1.5 font-mono text-slate-400">{signed(row.mean_delta_other_marker_mass, 5)}</td>
                </tr>
              );
            })
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function SteeringSweepPage() {
  const [data, setData] = useState<Sweep | null>(null);
  const [error, setError] = useState("");
  const [marker, setMarker] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetch("/latent/data/steering_sweep.json", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then((json: Sweep) => {
        if (json.schema !== "steer3d.steering_sweep/1" || !json.complete || !json.markers.length) {
          throw new Error("sweep 未完成或格式不匹配");
        }
        setData(json);
        setMarker(String(json.markers[0]));
      })
      .catch((reason) => {
        if (reason.name !== "AbortError") setError(reason.message);
      });
    return () => controller.abort();
  }, []);

  if (error) return <main className="min-h-screen bg-slate-950 p-10 text-rose-300">数据加载失败：{error}</main>;
  if (!data) return <main className="min-h-screen bg-slate-950 p-10 text-slate-400">正在读取 alpha sweep…</main>;

  const markers = data.markers.map(String);
  const selected = marker || markers[0];
  const nHeldout = Object.values(data.splits).reduce((sum, split) => sum + split.heldout.length, 0);

  return (
    <main className="min-h-screen bg-[#080e1a] px-4 py-6 text-slate-200 sm:px-8" data-testid="steering-sweep">
      <div className="mx-auto max-w-[1500px] space-y-5">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[11px] uppercase tracking-[.23em] text-teal-400">Hidden states × dose / side effects</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Alpha & Side-Effect Sweep</h1>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-400">
              对 held-out marker site 扫描剂量，比较 w、−w、mean g、sparse g、random 的 Δlogp、KL、熵变化与其它 marker 质量。
              它不是找“最强剂量”，而是把“效果 vs 副作用”的窗口摆出来。
            </p>
          </div>
          <nav className="flex gap-4 pt-2 text-xs text-slate-400">
            <a className="hover:text-teal-300" href="/">实时轨迹</a>
            <a className="hover:text-teal-300" href="/readout-atlas">hidden-state 读出</a>
            <a className="hover:text-teal-300" href="/steering-construction">构造 probe</a>
            <a className="hover:text-teal-300" href="/steering-transfer">held-out 迁移</a>
            <a className="hover:text-teal-300" href="/steering-recipe">编译 recipe</a>
            <a className="hover:text-teal-300" href="/steering-design">向量设计指南</a>
          </nav>
        </header>

        <section className={panel + " p-5"}>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="held-out sites" value={String(nHeldout)} hint={markers.join(", ")} />
            <Stat label="doses" value={data.doses.join(" / ")} hint="fraction of block-20 input norm" />
            <Stat label="KL threshold" value={String(data.kl_threshold)} hint="used for the useful-window pick" />
            <Stat label="injection layer" value={String(data.model.injection_layer)} hint={data.model.dtype + " · " + data.model.attention} />
          </div>
        </section>

        <Section title="有用窗口（KL 预算内）" subtitle="在 mean KL <= threshold 的格子里，选 mean Δlogp 最大的 direction/dose；这是描述性挑选，不是统计检验。" testid="sweep-window">
          <div className="grid gap-3 sm:grid-cols-3">
            {markers.map((item) => {
              const window = data.useful_window[item];
              return (
                <Stat
                  key={item}
                  label={"marker " + item}
                  value={window.direction === null ? "no window" : (window.direction + " @ " + window.dose)}
                  hint={window.mean_delta_logp === null ? "—" : "Δlogp " + signed(window.mean_delta_logp, 4) + " · KL " + fmt(window.mean_kl, 4)}
                  color="#2dd4bf"
                />
              );
            })}
          </div>
        </Section>

        <Section title="剂量响应与副作用" subtitle="左：Δlogp vs dose；右：mean KL vs dose（log）。−w 在高剂量下灾难性 off-manifold，图中省略，表里保留。" testid="sweep-charts">
          <div className="mb-3 flex flex-wrap gap-2">
            {markers.map((item) => (
              <button key={item} onClick={() => setMarker(item)} className={"rounded-lg border px-3 py-1.5 text-xs " + (item === selected ? "border-teal-500 bg-teal-500/10 text-teal-300" : "border-slate-700 text-slate-400")}>{item}</button>
            ))}
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <LineChart marker={selected} sweep={data} metric="mean_delta_logp" />
            <LineChart marker={selected} sweep={data} metric="mean_kl" />
          </div>
        </Section>

        <Section title="逐 direction × dose" subtitle="选中行是高亮的有用窗口。Δother mass 是其它 marker 概率质量的变化（本数据里接近 0，KL 才是主要副作用读数）。" testid="sweep-table">
          <DirectionTable marker={selected} sweep={data} />
        </Section>

        <Section title="边界" subtitle="这份 sweep 能说什么、不能说什么。" testid="sweep-caveats">
          <ul className="grid gap-2 text-xs leading-5 text-slate-400 lg:grid-cols-2">
            <li className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">每 marker 2 个 calibration + 2 个 held-out site；dose 扫描是描述性。</li>
            <li className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">KL/熵是对完整 softmax 的全局副作用，不是只对 marker 集合。</li>
            <li className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">mean g 的 Δlogp 更大但 KL 也大；sparse g 在相同 dose 下 KL 更低；w 最安全但更弱。</li>
            <li className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">高 dose 的 −w 读数极端 off-manifold，不能当“方向本身有效”的证据。</li>
          </ul>
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

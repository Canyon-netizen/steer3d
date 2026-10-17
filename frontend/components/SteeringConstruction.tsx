"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { CANDIDATE_COLOR, CANDIDATE_LABEL, fmt, signed } from "@/lib/steering-construction";
import type { Construction, ConstructionSite } from "@/lib/steering-construction";

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

function Scatter({ points }: { points: { response: number; contribution: number }[] }) {
  const width = 620;
  const height = 280;
  const left = 60;
  const top = 20;
  const maxResponse = Math.max(...points.map((point) => point.response), 1e-9);
  const maxContribution = Math.max(...points.map((point) => Math.abs(point.contribution)), 1e-9);
  const x = (value: number) => left + (Math.log10(Math.max(value, 1e-9)) - Math.log10(1e-9)) / (Math.log10(maxResponse) - Math.log10(1e-9)) * (width - left - 20);
  const y = (value: number) => top + (maxContribution - value) / (2 * maxContribution) * (height - top - 30);
  return (
    <svg viewBox={"0 0 " + width + " " + height} className="h-auto w-full" role="img" aria-label="response vs contribution">
      <line x1={left} y1={y(0)} x2={width - 20} y2={y(0)} stroke="#334155" />
      <line x1={left} y1={top} x2={left} y2={height - 30} stroke="#334155" />
      {points.map((point, index) => (
        <circle key={index} cx={x(point.response)} cy={y(point.contribution)} r="2.6" fill={point.contribution > 0 ? "#2dd4bf" : "#fb7185"} opacity="0.55" />
      ))}
      <text x={left} y={height - 8} fill="#64748b" fontSize="10">response |Δa| · ||d|| (log)</text>
      <text x="8" y={top + 10} fill="#64748b" fontSize="10">c_i</text>
      <text x={width - 190} y="18" fill="#2dd4bf" fontSize="10">carrier (c&gt;0)</text>
      <text x={width - 90} y="18" fill="#fb7185" fontSize="10">compensator (c&lt;0)</text>
    </svg>
  );
}

function SiteTable({ site }: { site: ConstructionSite }) {
  const carriers = site.decomposition.top_carriers;
  const compensators = site.decomposition.top_compensators;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="overflow-x-auto">
        <div className={smallLabel}>top carriers (c &gt; 0)</div>
        <table className="mt-2 w-full text-left text-xs">
          <thead className="text-[10px] uppercase text-slate-500">
            <tr><th className="px-2 py-1.5 font-medium">layer</th><th className="px-2 py-1.5 font-medium">unit</th><th className="px-2 py-1.5 font-medium">response</th><th className="px-2 py-1.5 font-medium">c</th></tr>
          </thead>
          <tbody>
            {carriers.map((unit) => (
              <tr key={unit.layer + ":" + unit.unit} className="border-t border-slate-800/70">
                <td className="px-2 py-1.5 font-mono text-slate-400">{unit.layer}</td>
                <td className="px-2 py-1.5 font-mono text-slate-300">{unit.unit}</td>
                <td className="px-2 py-1.5 font-mono text-slate-400">{fmt(unit.response, 2)}</td>
                <td className="px-2 py-1.5 font-mono text-teal-300">{signed(unit.contribution, 5)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="overflow-x-auto">
        <div className={smallLabel}>top compensators (c &lt; 0)</div>
        <table className="mt-2 w-full text-left text-xs">
          <thead className="text-[10px] uppercase text-slate-500">
            <tr><th className="px-2 py-1.5 font-medium">layer</th><th className="px-2 py-1.5 font-medium">unit</th><th className="px-2 py-1.5 font-medium">response</th><th className="px-2 py-1.5 font-medium">c</th></tr>
          </thead>
          <tbody>
            {compensators.map((unit) => (
              <tr key={unit.layer + ":" + unit.unit} className="border-t border-slate-800/70">
                <td className="px-2 py-1.5 font-mono text-slate-400">{unit.layer}</td>
                <td className="px-2 py-1.5 font-mono text-slate-300">{unit.unit}</td>
                <td className="px-2 py-1.5 font-mono text-slate-400">{fmt(unit.response, 2)}</td>
                <td className="px-2 py-1.5 font-mono text-rose-300">{signed(unit.contribution, 5)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function SteeringConstructionPage() {
  const [data, setData] = useState<Construction | null>(null);
  const [error, setError] = useState("");
  const [siteIndex, setSiteIndex] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/latent/data/steering_construction.json", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then((json: Construction) => {
        if (json.schema !== "steer3d.steering_construction/1" || !json.complete || !json.sites.length) {
          throw new Error("construction probe 未完成或格式不匹配");
        }
        setData(json);
      })
      .catch((reason) => {
        if (reason.name !== "AbortError") setError(reason.message);
      });
    return () => controller.abort();
  }, []);

  const site = data ? data.sites[Math.min(siteIndex, data.sites.length - 1)] : null;
  const markers = useMemo(() => (data ? Object.keys(data.aggregate).sort() : []), [data]);

  if (error) return <main className="min-h-screen bg-slate-950 p-10 text-rose-300">数据加载失败：{error}</main>;
  if (!data || !site) return <main className="min-h-screen bg-slate-950 p-10 text-slate-400">正在读取 construction probe…</main>;

  const candidateNames = ["w", "minus_w", "gradient", "w_plus_gradient", "random"];

  return (
    <main className="min-h-screen bg-[#080e1a] px-4 py-6 text-slate-200 sm:px-8" data-testid="steering-construction">
      <div className="mx-auto max-w-[1500px] space-y-5">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[11px] uppercase tracking-[.23em] text-teal-400">Hidden states × constructive directions</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Steering Construction Probe</h1>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-400">
              在短 AIME 前缀上把 f = log p(marker) 对 block-20 输入求梯度 g，比较 w、−w、g、w+g、random 在同一 alpha 下对 f 的改变；再把 g 分解到 layer 20-27 的原生单元，看哪些单元是载体、哪些是抵消者。
            </p>
          </div>
          <nav className="flex gap-4 pt-2 text-xs text-slate-400">
            <a className="hover:text-teal-300" href="/">实时轨迹</a>
            <a className="hover:text-teal-300" href="/readout-atlas">hidden-state 读出</a>
            <a className="hover:text-teal-300" href="/steering-transfer">held-out 迁移</a>
            <a className="hover:text-teal-300" href="/steering-design">向量设计指南</a>
            <a className="hover:text-teal-300" href="/latent/index.html">隐空间观察台</a>
          </nav>
        </header>

        <section className={panel + " p-5"}>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="sites" value={String(data.sites.length)} hint={"markers " + markers.join(", ")} />
            <Stat label="injection layer" value={String(data.model.injection_layer)} hint={data.model.dtype + " · " + data.model.attention} />
            <Stat label="alpha rule" value="0.1 × input norm" hint={data.alpha_rule} />
            <Stat label="best candidate" value="gradient" hint="all tested markers" color="#60a5fa" />
          </div>
        </section>

        <Section title="按 marker 聚合：均值与改善比例" subtitle="delta = 注入后 f − baseline f；improved = 该候选在多少比例的 site 上提高 f。gradient 是局部白盒方向，不是有语义命名的向量。" testid="construction-aggregate">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-[10px] uppercase text-slate-500">
                <tr>
                  <th className="px-2 py-2 font-medium">marker</th>
                  <th className="px-2 py-2 font-medium">n</th>
                  {candidateNames.map((name) => (
                    <th key={name} className="px-2 py-2 font-medium" style={{ color: CANDIDATE_COLOR[name] }}>{CANDIDATE_LABEL[name]}</th>
                  ))}
                  <th className="px-2 py-2 font-medium">best</th>
                </tr>
              </thead>
              <tbody>
                {markers.map((marker) => {
                  const item = data.aggregate[marker];
                  return (
                    <tr key={marker} className="border-t border-slate-800/70">
                      <td className="px-2 py-2 font-mono text-slate-300">{marker}</td>
                      <td className="px-2 py-2 font-mono text-slate-400">{item.n_sites}</td>
                      {candidateNames.map((name) => {
                        const candidate = item.candidates[name];
                        return (
                          <td key={name} className="px-2 py-2 font-mono" style={{ color: CANDIDATE_COLOR[name] }}>
                            {signed(candidate?.mean_delta_logp ?? null, 4)}
                            <span className="ml-1 text-[10px] text-slate-500">{candidate ? Math.round(candidate.improved_fraction * 100) + "%" : "—"}</span>
                          </td>
                        );
                      })}
                      <td className="px-2 py-2 font-mono text-slate-400">{item.best_candidate}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Section>

        <Section title="逐 site：方向对比" subtitle="所有候选共享同一 alpha；baseline f 是未注入时的 log p(marker)。" testid="construction-sites">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-[10px] uppercase text-slate-500">
                <tr>
                  <th className="px-2 py-2 font-medium">site</th>
                  <th className="px-2 py-2 font-medium">marker</th>
                  <th className="px-2 py-2 font-medium">prefix</th>
                  <th className="px-2 py-2 font-medium">f0</th>
                  {candidateNames.map((name) => (
                    <th key={name} className="px-2 py-2 font-medium" style={{ color: CANDIDATE_COLOR[name] }}>Δ{CANDIDATE_LABEL[name]}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.sites.map((row, index) => (
                  <tr key={row.trajectory + ":" + row.t} className={"border-t border-slate-800/70 cursor-pointer " + (index === siteIndex ? "bg-teal-500/10" : "")} onClick={() => setSiteIndex(index)}>
                    <td className="px-2 py-2 font-mono text-slate-300">{row.trajectory}</td>
                    <td className="px-2 py-2 font-mono text-slate-400">{row.marker}</td>
                    <td className="px-2 py-2 font-mono text-slate-400">{row.n_prefix}</td>
                    <td className="px-2 py-2 font-mono text-slate-400">{signed(row.baseline_logp, 3)}</td>
                    {candidateNames.map((name) => (
                      <td key={name} className="px-2 py-2 font-mono" style={{ color: CANDIDATE_COLOR[name] }}>{signed(row.candidates[name]?.delta_logp ?? null, 4)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        <Section title="单元四象限：response vs 一阶贡献" subtitle="c_i = (g · d_i) * Δa_i；这是 first-order 诊断，不是 mediation 百分比。高响应阈值取该 site 的 90 分位。" testid="construction-quadrants">
          <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
            <div>
              <Scatter points={data.scatter} />
            </div>
            <div className="space-y-2">
              <Stat label="selected site" value={site.marker + " · " + site.n_prefix} hint={site.trajectory} />
              <Stat label="quadrants" value={"carrier " + site.decomposition.quadrants.carrier + " / compensator " + site.decomposition.quadrants.compensator} hint={"silent " + site.decomposition.quadrants.silent + " · neutral " + site.decomposition.quadrants.neutral} />
              <Stat label="sum c / measured Δw" value={signed(site.decomposition.sum_contribution, 4) + " / " + signed(site.decomposition.measured_delta_w, 4)} hint={"ratio " + fmt(site.decomposition.ratio, 2)} />
              <Stat label="cos(g, w)" value={signed(site.gradient.cos_with_w, 3)} hint={"g at layer " + site.gradient.layer} />
            </div>
          </div>
          <div className="mt-4">
            <SiteTable site={site} />
          </div>
        </Section>

        <Section title="边界" subtitle="这份 probe 能说什么、不能说什么。" testid="construction-caveats">
          <ul className="grid gap-2 text-xs leading-5 text-slate-400 lg:grid-cols-2">
            <li className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">局部白盒：只测 6 个短前缀、3 个 marker、一个 alpha；不是通用构造配方。</li>
            <li className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">gradient 是数值方向，不保证语义；它只说明在这个前缀/层/剂量下提高 f 的方向。</li>
            <li className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">unit decomposition 是一阶诊断；sum c 与实测 Δ 的比例跨 site 不稳定，不能报成 mediation 百分比。</li>
            <li className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">naive 去掉 write-direction 分量的修复原型失败；不要把它当已验证的修复方法。</li>
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

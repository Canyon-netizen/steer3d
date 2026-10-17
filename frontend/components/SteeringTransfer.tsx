"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { CANDIDATE_COLOR, CANDIDATE_LABEL, CANDIDATE_ORDER, fmt, heatColor, signed } from "@/lib/steering-transfer";
import type { Transfer } from "@/lib/steering-transfer";

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

export default function SteeringTransferPage() {
  const [data, setData] = useState<Transfer | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetch("/latent/data/steering_transfer.json", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then((json: Transfer) => {
        if (json.schema !== "steer3d.steering_transfer/1" || !json.complete || !json.sites.length) {
          throw new Error("transfer 未完成或格式不匹配");
        }
        setData(json);
      })
      .catch((reason) => {
        if (reason.name !== "AbortError") setError(reason.message);
      });
    return () => controller.abort();
  }, []);

  if (error) return <main className="min-h-screen bg-slate-950 p-10 text-rose-300">数据加载失败：{error}</main>;
  if (!data) return <main className="min-h-screen bg-slate-950 p-10 text-slate-400">正在读取 held-out transfer…</main>;

  const markers = Object.keys(data.same_marker);
  const nHeldout = Object.values(data.splits).reduce((sum, split) => sum + split.heldout.length, 0);
  const nCalibration = Object.values(data.splits).reduce((sum, split) => sum + split.calibration.length, 0);

  return (
    <main className="min-h-screen bg-[#080e1a] px-4 py-6 text-slate-200 sm:px-8" data-testid="steering-transfer">
      <div className="mx-auto max-w-[1500px] space-y-5">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[11px] uppercase tracking-[.23em] text-teal-400">Hidden states × held-out transfer</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Held-out Steering Transfer</h1>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-400">
              每个 marker 用 calibration sites 的梯度均值构造一个方向，在**没参与构造**的 held-out sites 上评估；cross 矩阵把 source marker 的均值梯度用到 target marker 的 held-out site。它回答“一个方向能不能迁移”，而不只是“在这个 site 上有效”。
            </p>
          </div>
          <nav className="flex gap-4 pt-2 text-xs text-slate-400">
            <a className="hover:text-teal-300" href="/">实时轨迹</a>
            <a className="hover:text-teal-300" href="/readout-atlas">hidden-state 读出</a>
            <a className="hover:text-teal-300" href="/steering-construction">构造 probe</a>
            <a className="hover:text-teal-300" href="/steering-sweep">剂量/副作用</a>
            <a className="hover:text-teal-300" href="/steering-design">向量设计指南</a>
          </nav>
        </header>

        <section className={panel + " p-5"}>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="markers" value={markers.join(", ")} hint={data.model.name} />
            <Stat label="sites" value={String(data.sites.length)} hint={nCalibration + " calibration + " + nHeldout + " held-out"} />
            <Stat label="injection layer" value={String(data.model.injection_layer)} hint={data.model.dtype + " · " + data.model.attention} />
            <Stat label="alpha rule" value="0.1 × input norm" hint={data.alpha_rule} />
          </div>
        </section>

        <Section title="同 marker 的 held-out 迁移" subtitle="mean g 只用 calibration sites 构造；oracle g 是 held-out site 自己的梯度（上界）。括号内为改善比例。" testid="transfer-same-marker">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-[10px] uppercase text-slate-500">
                <tr>
                  <th className="px-2 py-2 font-medium">marker</th>
                  {CANDIDATE_ORDER.map((name) => (
                    <th key={name} className="px-2 py-2 font-medium" style={{ color: CANDIDATE_COLOR[name] }}>{CANDIDATE_LABEL[name]}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {markers.map((marker) => (
                  <tr key={marker} className="border-t border-slate-800/70">
                    <td className="px-2 py-2 font-mono text-slate-300">{marker}</td>
                    {CANDIDATE_ORDER.map((name) => {
                      const cell = data.same_marker[marker][name];
                      return (
                        <td key={name} className="px-2 py-2 font-mono" style={{ color: CANDIDATE_COLOR[name] }}>
                          {signed(cell?.mean_delta_logp ?? null, 4)}
                          <span className="ml-1 text-[10px] text-slate-500">{cell ? Math.round(cell.improved_fraction * 100) + "%" : "—"}</span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        <Section title="cross-marker 迁移矩阵（mean g）" subtitle="行 = source marker 的均值梯度，列 = target marker 的 held-out site。对角线未测（留白）；颜色在 ±1.5 处截断，格内数字是原始 delta。" testid="transfer-cross">
          <div className="overflow-x-auto">
            <table className="border-collapse text-center text-xs">
              <thead>
                <tr>
                  <th className="px-3 py-2 text-[10px] uppercase text-slate-500">source \ target</th>
                  {markers.map((target) => <th key={target} className="px-3 py-2 font-mono text-slate-400">{target}</th>)}
                </tr>
              </thead>
              <tbody>
                {markers.map((source) => (
                  <tr key={source}>
                    <th className="px-3 py-2 font-mono text-slate-400">{source}</th>
                    {markers.map((target) => {
                      const cell = data.cross[source]?.[target];
                      if (!cell) return <td key={target} className="border border-slate-800 px-3 py-3 text-slate-600">—</td>;
                      const color = heatColor(cell.mean_delta_logp);
                      const textColor = Math.abs(cell.mean_delta_logp) > 0.825 ? "#f8fafc" : "#0f172a";
                      return (
                        <td key={target} className="border border-slate-800 px-3 py-3 font-mono" style={{ background: color, color: textColor }}>
                          {signed(cell.mean_delta_logp, 3)}
                          <div className="text-[9px] opacity-80">{Math.round(cell.improved_fraction * 100)}%</div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-[11px] leading-5 text-slate-500">7196 的均值梯度对 10061/6771 是负的（-0.457 / -5.711），而 10061/6771 的均值梯度对其它 marker 为正 ⇒ 7196 方向含 marker-specific 成分；10061/6771 更像共享的 marker-raising 成分。cross 只有 2 个 held-out sites/格，描述性。</p>
        </Section>

        <Section title="逐 held-out site" subtitle="所有方向共享该 site 的 baseline 与 alpha。" testid="transfer-sites">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-[10px] uppercase text-slate-500">
                <tr>
                  <th className="px-2 py-2 font-medium">site</th>
                  <th className="px-2 py-2 font-medium">marker</th>
                  <th className="px-2 py-2 font-medium">prefix</th>
                  <th className="px-2 py-2 font-medium">f0</th>
                  <th className="px-2 py-2 font-medium">Δw</th>
                  <th className="px-2 py-2 font-medium">Δ mean g</th>
                  <th className="px-2 py-2 font-medium">Δ sparse g</th>
                  <th className="px-2 py-2 font-medium">Δ oracle</th>
                </tr>
              </thead>
              <tbody>
                {data.sites.map((site) => (
                  <tr key={site.trajectory + ":" + site.t} className="border-t border-slate-800/70">
                    <td className="px-2 py-2 font-mono text-slate-400">{site.trajectory}</td>
                    <td className="px-2 py-2 font-mono text-slate-300">{site.marker}</td>
                    <td className="px-2 py-2 font-mono text-slate-400">{site.n_prefix}</td>
                    <td className="px-2 py-2 font-mono text-slate-400">{signed(site.baseline_logp, 3)}</td>
                    <td className="px-2 py-2 font-mono" style={{ color: CANDIDATE_COLOR.w }}>{signed(site.directions.w?.delta_logp ?? null, 4)}</td>
                    <td className="px-2 py-2 font-mono" style={{ color: CANDIDATE_COLOR.g_mean }}>{signed(site.directions.g_mean?.delta_logp ?? null, 4)}</td>
                    <td className="px-2 py-2 font-mono" style={{ color: CANDIDATE_COLOR.g_sparse }}>{signed(site.directions.g_sparse?.delta_logp ?? null, 4)}</td>
                    <td className="px-2 py-2 font-mono" style={{ color: CANDIDATE_COLOR.oracle_per_site_gradient }}>{signed(site.oracle?.delta_logp ?? null, 4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        <Section title="边界" subtitle="这份 transfer 能说什么、不能说什么。" testid="transfer-caveats">
          <ul className="grid gap-2 text-xs leading-5 text-slate-400 lg:grid-cols-2">
            <li className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">每个 marker 只有 2 个 calibration + 2 个 held-out site；不是统计显著结论。</li>
            <li className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">calibration 与 held-out 按 prefix 长度排序切分，可能带来长度/位置混杂。</li>
            <li className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">mean g 是局部梯度平均，不保证语义；sparse g 保留 10% 坐标，仍是白盒方向。</li>
            <li className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">cross 的 -5.711 是极端 off-manifold 读数；颜色已截断，数字原样保留。</li>
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

"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { fmt, signed } from "@/lib/steering-recipe";
import type { Recipe } from "@/lib/steering-recipe";

const panel = "rounded-2xl border border-slate-800 bg-slate-900/60";
const smallLabel = "text-[11px] uppercase tracking-wider text-slate-500";
const usageLines = [
  "import numpy as np",
  "v = np.load('experiments/steering_recipe_v1/vectors/7196_sparse_g.npy')",
  "alpha = dose * np.linalg.norm(h_block20_last)",
  "h_block20_last += alpha * v",
  "# 然后在你的前缀上重新测 target marker logp / KL，不要直接复用本页数字",
];

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

export default function SteeringRecipePage() {
  const [data, setData] = useState<Recipe | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetch("/latent/data/steering_recipe.json", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then((json: Recipe) => {
        if (json.schema !== "steer3d.steering_recipe/1" || !json.complete || !Object.keys(json.markers).length) {
          throw new Error("recipe 未完成或格式不匹配");
        }
        setData(json);
      })
      .catch((reason) => {
        if (reason.name !== "AbortError") setError(reason.message);
      });
    return () => controller.abort();
  }, []);

  if (error) return <main className="min-h-screen bg-slate-950 p-10 text-rose-300">数据加载失败：{error}</main>;
  if (!data) return <main className="min-h-screen bg-slate-950 p-10 text-slate-400">正在读取 compiled recipe…</main>;

  const markers = Object.keys(data.markers).sort();

  return (
    <main className="min-h-screen bg-[#080e1a] px-4 py-6 text-slate-200 sm:px-8" data-testid="steering-recipe">
      <div className="mx-auto max-w-[1500px] space-y-5">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[11px] uppercase tracking-[.23em] text-teal-400">Hidden states × compiled recipes</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Compiled Steering Recipes</h1>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-400">
              每个 marker 一个可复现的候选方向：readout atlas 选层，calibration 梯度均值构造方向，sweep 选 KL 预算内的 dose，
              在 held-out site 上验证，并保存为 .npy。它是可复现的起点，不是生产级 steering vector。
            </p>
          </div>
          <nav className="flex gap-4 pt-2 text-xs text-slate-400">
            <a className="hover:text-teal-300" href="/">实时轨迹</a>
            <a className="hover:text-teal-300" href="/readout-atlas">hidden-state 读出</a>
            <a className="hover:text-teal-300" href="/steering-construction">构造 probe</a>
            <a className="hover:text-teal-300" href="/steering-transfer">held-out 迁移</a>
            <a className="hover:text-teal-300" href="/steering-sweep">剂量/副作用</a>
            <a className="hover:text-teal-300" href="/steering-design">向量设计指南</a>
          </nav>
        </header>

        <section className={panel + " p-5"}>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="markers" value={markers.join(", ")} hint={data.model.name} />
            <Stat label="injection layer" value={String(data.model.injection_layer)} hint={data.model.dtype + " · " + data.model.attention} />
            <Stat label="alpha rule" value="dose × input norm" hint={data.alpha_rule} />
            <Stat label="vector sha" value={data.vector.sha256.slice(0, 16) + "…"} hint={data.vector.path} />
          </div>
        </section>

        <div className="grid gap-5 lg:grid-cols-3">
          {markers.map((marker) => {
            const entry = data.markers[marker];
            const compiled = entry.compiled;
            const verification = entry.verification;
            return (
              <Section key={marker} title={"marker " + marker} subtitle={"readout layer " + (entry.readout.best_layer ?? "—") + " · cos AUC " + fmt(entry.readout.raw_cos_auc) + " · orientation " + (entry.readout.orientation ?? "—")} testid={"recipe-" + marker}>
                <div className="grid grid-cols-2 gap-2">
                  <Stat label="direction" value={compiled.direction} color="#60a5fa" />
                  <Stat label="dose" value={String(compiled.dose)} hint="× input norm" />
                  <Stat label="expected Δ" value={signed(compiled.expected_delta_logp)} hint={"KL " + fmt(compiled.expected_kl)} color="#2dd4bf" />
                  <Stat label="verified Δ" value={signed(verification.mean_delta_logp)} hint={"KL " + fmt(verification.mean_kl) + " · n=" + verification.n_sites} color="#fbbf24" />
                </div>
                <div className="mt-3 text-xs text-slate-400">
                  <div className="mb-1"><span className={smallLabel}>file</span></div>
                  <a className="break-all font-mono text-teal-300 hover:text-teal-200" href={compiled.public_url || "#"} download>{compiled.file}</a>
                </div>
                <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/40 p-2 text-[11px] leading-5 text-slate-400">
                  held-out transfer: w {signed(entry.heldout_transfer.w)} · mean g {signed(entry.heldout_transfer.mean_g)} · sparse g {signed(entry.heldout_transfer.sparse_g)} · oracle {signed(entry.heldout_transfer.oracle)}
                </div>
                <details className="mt-3 text-[11px] text-slate-400">
                  <summary className="cursor-pointer">verification sites</summary>
                  <table className="mt-2 w-full text-left text-[10px]">
                    <thead className="uppercase text-slate-500">
                      <tr><th className="py-1 font-medium">site</th><th className="py-1 font-medium">Δlogp</th><th className="py-1 font-medium">KL</th></tr>
                    </thead>
                    <tbody>
                      {verification.sites.map((site) => (
                        <tr key={site.trajectory + ":" + site.t} className="border-t border-slate-800/70">
                          <td className="py-1 font-mono">{site.trajectory} · t={site.t}</td>
                          <td className="py-1 font-mono text-teal-300">{signed(site.delta_logp)}</td>
                          <td className="py-1 font-mono">{fmt(site.kl)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </details>
              </Section>
            );
          })}
        </div>

        <Section title="怎么用这个 recipe" subtitle="候选方向是本地白盒产物；换前缀/模型/层/剂量前必须重新验证。" testid="recipe-usage">
          <div className="overflow-x-auto rounded-xl bg-slate-950 p-4 font-mono text-[11px] leading-6 text-slate-300">
            {usageLines.map((line, index) => <div key={index}>{line}</div>)}
          </div>
          <ul className="mt-3 grid gap-2 text-xs leading-5 text-slate-400 lg:grid-cols-2">
            <li className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">verification 用的是 transfer/sweep 的 held-out site，不是第三个独立 split。</li>
            <li className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">mean g / sparse g 是数值方向，不保证语义；高 dose 可能 off-manifold。</li>
            <li className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">单模型、单层 20、短 AIME 前缀；不能直接外推到生产。</li>
            <li className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">改前缀/层/剂量后，必须重新测 target logp、KL 与任务级指标。</li>
          </ul>
        </Section>

        <Section title="每个 recipe 的 caveats" subtitle="这些限制必须和文件一起传递。" testid="recipe-caveats">
          <div className="grid gap-3 lg:grid-cols-3">
            {markers.map((marker) => (
              <div key={marker} className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
                <div className="font-mono text-sm text-slate-200">marker {marker}</div>
                <ul className="mt-2 space-y-1 text-[11px] leading-5 text-slate-500">
                  {data.markers[marker].caveats.map((item, index) => <li key={index}>· {item}</li>)}
                </ul>
              </div>
            ))}
          </div>
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

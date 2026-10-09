"use client";

import { useEffect, useMemo, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Html, Line, OrbitControls } from "@react-three/drei";
import { useWebGLSupport } from "@/lib/use-webgl";

type Direction = "w+" | "w-" | "rand";
type Point = [number, number, number];
type Readout = {
  marker_lse: number; marker_logprob: number; marker_logits: number[];
  marker_logprobs: number[]; argmax_id: number;
};
type Variant = {
  direction: Direction; rel: number; alpha: number;
  d_marker_lse: number; d_marker_logprob: number;
  readout: Readout; projection: Record<string, Point>;
};
type Layer = {
  layer: number; d_marker_lse: number; d_marker_logprob: number; d_marker_logits: number[];
  calibration?: { ok: boolean; prediction: number[]; observed: number[]; residual: number[] };
};
type Site = {
  t: number; inject_abs: number; marker_id: number; marker_text: string; prefix_tail: string;
  baseline: Readout; baseline_repeated_exact: boolean; input_norm: number;
  variants: Variant[]; layers: Layer[];
};
type NormVariant = {
  direction: Direction; rel: number; block_norm_gain: number; norm_norm_gain: number;
  post_norm_alignment: number; norm_reconstruction_ok: boolean;
  marker_logit_transmitted: number[]; marker_logit_rescaled: number[];
};
type Trajectory = {
  id: string; mode: string; n_tok: number; positions: number[]; sites: Site[];
  norm_transport: { t: number; variants: NormVariant[] };
};
type Evidence = {
  schema: string; complete: boolean; vector_sha256: string; dtype: string; layer: number;
  dose: number[]; gap: number; marker_ids: number[]; marker_text: string[];
  trajectories: Trajectory[]; pca: Record<string, { explained_variance: number[] }>;
  frequency: { total: number; rows: { id: number; dot: number; count: number; text: string }[] };
  original_p9: { passed: number; total: number; ok: boolean };
  original_dose_audit: { d3: boolean; d4: boolean };
};
const DIRECTIONS: Direction[] = ["w+", "w-", "rand"];
const COLORS: Record<Direction, string> = { "w+": "#6ee7b7", "w-": "#fda4af", rand: "#a5b4fc" };
const LABELS: Record<Direction, string> = { "w+": "+w", "w-": "−w", rand: "随机方向" };
const fmt = (n: number, digits = 4) => (n >= 0 ? "+" : "") + n.toFixed(digits);
const probability = (lp: number) => Math.exp(lp) < 0.0001 ? Math.exp(lp).toExponential(2) : Math.exp(lp).toFixed(5);

function Chart({ xs, series, labels, selectedX, title }: {
  xs: number[]; series: { name: string; color: string; ys: number[] }[];
  labels?: string[]; selectedX?: number; title: string;
}) {
  const width = 650, height = 240, left = 60, right = 18, top = 14, bottom = 36;
  const values = series.flatMap((s) => s.ys);
  const lo = Math.min(0, ...values), hi = Math.max(0, ...values), padding = (hi - lo || 1) * 0.12;
  const yMin = lo - padding, yMax = hi + padding;
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const x = (v: number) => left + ((v - xMin) / (xMax - xMin || 1)) * (width - left - right);
  const y = (v: number) => top + ((yMax - v) / (yMax - yMin)) * (height - top - bottom);
  return <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label={title}>
    {[yMin, yMin + (yMax-yMin)/2, yMax].map((v) => <g key={v}>
      <line x1={left} x2={width-right} y1={y(v)} y2={y(v)} stroke="#273344" />
      <text x={left-7} y={y(v)+4} textAnchor="end" fill="#94a3b8" fontSize="11">{v.toFixed(2)}</text>
    </g>)}
    <line x1={left} x2={width-right} y1={y(0)} y2={y(0)} stroke="#64748b" strokeDasharray="4 4" />
    {selectedX !== undefined && <line x1={x(selectedX)} x2={x(selectedX)} y1={top} y2={height-bottom} stroke="#f8fafc" strokeDasharray="3 5" />}
    {xs.map((v, i) => ((labels && (v < 26 || i === xs.length-1)) || (!labels && (v === 0 || v >= 0.1))) &&
      <text key={v} x={x(v)} y={height-12} textAnchor="middle" fill="#94a3b8" fontSize="11">{labels?.[i] ?? v}</text>)}
    {series.map((s) => <g key={s.name}>
      <polyline points={s.ys.map((v,i) => `${x(xs[i])},${y(v)}`).join(" ")} fill="none" stroke={s.color} strokeWidth="2" />
      {s.ys.map((v,i) => <circle key={i} cx={x(xs[i])} cy={y(v)} r={selectedX === xs[i] ? 5 : 3} fill={s.color}><title>{s.name} · {labels?.[i] ?? xs[i]} · {fmt(v,6)}</title></circle>)}
    </g>)}
  </svg>;
}

function StatePlot({ curves, selected, rel, layer, coverage }: {
  curves: Record<Direction, Point[]>; selected: Direction; rel: number; layer: string; coverage: number;
}) {
  const support = useWebGLSupport();
  const [view, setView] = useState<"3d" | "2d">("3d");
  const extent = Math.max(1e-9, ...DIRECTIONS.flatMap((name) => curves[name].map((p) => Math.hypot(...p))));
  const scaled = Object.fromEntries(DIRECTIONS.map((name) => [name, curves[name].map((p) => p.map((v) => v/extent*3) as Point)])) as Record<Direction, Point[]>;
  return <section className="rounded-xl border border-slate-700 bg-slate-900/60 p-5">
    <div className="flex items-center justify-between gap-4">
      <h2 className="font-semibold">当前 token 的状态位移</h2>
      <div className="flex gap-2">
        <button onClick={() => setView("2d")} aria-pressed={view === "2d"} className="rounded border border-slate-600 px-3 py-1 text-xs">2D</button>
        <button onClick={() => setView("3d")} aria-pressed={view === "3d"} disabled={support === false} className="rounded border border-slate-600 px-3 py-1 text-xs disabled:opacity-40">3D</button>
      </div>
    </div>
    <p className="mt-2 text-xs leading-5 text-slate-400">{layer === "-1" ? "最终 norm 输出" : `block ${layer} 输入`} · 共享 PCA 基，前三维覆盖 {Number(coverage*100).toFixed(1)}% 方差。原点为该位置 baseline；连线连接已测剂量。</p>
    <div className="mt-3 h-[330px]" data-testid="bpath-state-plot" data-view={support && view === "3d" ? "3d" : "2d"} data-layer={layer} data-rel-index={rel}>
      {support === null ? <p className="text-sm text-slate-400">正在检测图形支持…</p> : support && view === "3d" ?
        <Canvas camera={{ position: [5, 4, 6], fov: 45 }} gl={{ preserveDrawingBuffer: true }} dpr={[1, 1.5]}>
          <ambientLight intensity={1.2} />
          <axesHelper args={[3.3]} />
          <mesh position={[0,0,0]}><sphereGeometry args={[0.07,16,16]} /><meshBasicMaterial color="#ffffff" /></mesh>
          <Html position={[0,0,0]}><span className="pointer-events-none whitespace-nowrap text-[10px] text-white">baseline</span></Html>
          {DIRECTIONS.map((name) => <group key={name}>
            <Line points={scaled[name]} color={COLORS[name]} lineWidth={name === selected ? 2.5 : 1.3} />
            {scaled[name].map((p, i) => <mesh key={i} position={p}>
              <sphereGeometry args={[i === rel && name === selected ? 0.10 : 0.045,12,12]} />
              <meshBasicMaterial color={COLORS[name]} />
            </mesh>)}
          </group>)}
          <OrbitControls makeDefault />
        </Canvas> : <svg viewBox="-3.8 -3.8 7.6 7.6" className="h-full w-full" role="img" aria-label="状态位移 2D 投影">
          <line x1="-3.4" x2="3.4" y1="0" y2="0" stroke="#475569" strokeWidth="0.015" />
          <line x1="0" x2="0" y1="-3.4" y2="3.4" stroke="#475569" strokeWidth="0.015" />
          {DIRECTIONS.map((name) => <g key={name}>
            <polyline points={scaled[name].map((p) => `${p[0]},${-p[1]}`).join(" ")} fill="none" stroke={COLORS[name]} strokeWidth="0.025" />
            {scaled[name].map((p,i) => <circle key={i} cx={p[0]} cy={-p[1]} r={i === rel && name === selected ? 0.075 : 0.035} fill={COLORS[name]} />)}
          </g>)}
          <circle cx="0" cy="0" r="0.05" fill="white" />
        </svg>}
    </div>
    <p className="text-xs text-slate-400">{support ? "拖动旋转，滚轮缩放。" : "当前浏览器使用 2D 投影。"} 图形范围对应最大投影位移 {extent.toFixed(3)}；PCA 轴不代表推理概念。</p>
  </section>;
}

export default function BPathEvidenceExplorer() {
  const [data, setData] = useState<Evidence | null>(null), [error, setError] = useState<string | null>(null);
  const [trajectoryId, setTrajectoryId] = useState(""), [siteIndex, setSiteIndex] = useState(0);
  const [relIndex, setRelIndex] = useState(3), [direction, setDirection] = useState<Direction>("w+");
  const [metric, setMetric] = useState<"probability" | "logit">("probability");
  const [target, setTarget] = useState("group"), [stateLayer, setStateLayer] = useState("20");
  useEffect(() => {
    const controller = new AbortController();
    fetch("/latent/data/bpath_explorer.json", { signal: controller.signal }).then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    }).then((j: Evidence) => {
      if (!j.complete || j.schema !== "steer3d.bpath_explorer/1") throw new Error("扫描结果尚未完成或格式不匹配");
      setData(j); setTrajectoryId(j.trajectories[0].id);
    }).catch((e) => { if (e.name !== "AbortError") setError(e.message); });
    return () => controller.abort();
  }, []);
  const trajectory = useMemo(() => data?.trajectories.find((t) => t.id === trajectoryId), [data, trajectoryId]);
  if (error) return <main className="min-h-screen bg-slate-950 p-10 text-rose-300">实验数据加载失败：{error}</main>;
  if (!data || !trajectory) return <main className="min-h-screen bg-slate-950 p-10 text-slate-300">正在读取已完成的干预实验…</main>;
  const site = trajectory.sites[siteIndex] ?? trajectory.sites[0];
  const rel = relIndex === 0 ? 0 : data.dose[relIndex-1];
  const tokenIndex = target === "group" ? -1 : data.marker_ids.indexOf(Number(target));
  const targetName = tokenIndex < 0 ? "marker 集合" : JSON.stringify(data.marker_text[tokenIndex]);
  const getDelta = (v: Variant, base: Readout) => tokenIndex < 0
    ? metric === "probability" ? v.d_marker_logprob : v.d_marker_lse
    : metric === "probability" ? v.readout.marker_logprobs[tokenIndex] - base.marker_logprobs[tokenIndex]
      : v.readout.marker_logits[tokenIndex] - base.marker_logits[tokenIndex];
  const variant = (name: Direction, dose: number) => site.variants.find((v) => v.direction === name && v.rel === dose)!;
  const current = rel === 0 ? null : variant(direction, rel);
  const doseCurves = DIRECTIONS.map((name) => ({ name: LABELS[name], color: COLORS[name], ys: [0, ...data.dose.map((d) => getDelta(variant(name,d), site.baseline))] }));
  const layerSite = trajectory.sites[0];
  const layers = [...layerSite.layers].sort((a,b) => (a.layer === -1 ? 28 : a.layer) - (b.layer === -1 ? 28 : b.layer));
  const layerDelta = (row: Layer) => tokenIndex < 0 ? metric === "probability" ? row.d_marker_logprob : row.d_marker_lse
    : row.d_marker_logits[tokenIndex] - (metric === "probability" ? row.d_marker_lse - row.d_marker_logprob : 0);
  const curves = Object.fromEntries(DIRECTIONS.map((name) => [name, [[0,0,0], ...data.dose.map((d) => variant(name,d).projection[stateLayer])]])) as Record<Direction, Point[]>;
  const calibration = layers.find((l) => l.layer === -1)?.calibration;
  const transport = rel === 0 ? null : trajectory.norm_transport.variants.find((v) => v.direction === direction && v.rel === rel);
  const mechanismToken = tokenIndex < 0
    ? layerSite.baseline.marker_logits.indexOf(Math.max(...layerSite.baseline.marker_logits)) : tokenIndex;
  const selectClass = "mt-1 w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-100";
  return <main className="min-h-screen bg-slate-950 px-5 py-7 text-slate-100 md:px-10" data-testid="bpath-explorer" data-trajectory={trajectory.id} data-position={site.t} data-rel={rel} data-target={target}>
    <header className="mx-auto max-w-7xl">
      <nav className="mb-5 flex gap-5 text-sm text-sky-300"><a href="/">3D 推理轨迹</a><a href="/latent/index.html">2D 隐空间观察台</a></nav>
      <p className="text-xs tracking-widest text-emerald-300">QWEN3 · AIME · 臂 B</p>
      <h1 className="mt-2 text-3xl font-semibold">向量如何改变下一步 token</h1>
      <p className="mt-3 max-w-4xl text-sm leading-6 text-slate-400">固定相同前缀，在 block {data.layer} 输入的最后一个 token 加入向量，重新运行模型。这里展示局部响应，帮助区分方向、剂量、位置与下游传播。</p>
      <div className="mt-4 rounded-lg border border-amber-800/70 bg-amber-950/20 p-3 text-sm text-amber-200" data-testid="bpath-verdict">
        原 P9：{data.original_p9.passed}/{data.original_p9.total} 通过。本轮不发布 correct／wrong 主判决；当前图形是补充机制测量。
      </div>
    </header>
    <div className="mx-auto mt-6 max-w-7xl">
      <section className="grid gap-4 rounded-xl border border-slate-700 bg-slate-900/60 p-5 md:grid-cols-4">
        <label className="text-xs text-slate-400">轨迹<select aria-label="轨迹" className={selectClass} value={trajectoryId} onChange={(e) => { setTrajectoryId(e.target.value); setSiteIndex(0); }}>
          {data.trajectories.map((t) => <option key={t.id} value={t.id}>{t.id.replace("aime__aime25__", "")} · {t.n_tok} tokens</option>)}
        </select></label>
        <label className="text-xs text-slate-400">marker 位置<select aria-label="marker 位置" className={selectClass} value={siteIndex} onChange={(e) => setSiteIndex(Number(e.target.value))}>
          {trajectory.sites.map((s,i) => <option key={s.t} value={i}>t={s.t} · id {s.marker_id} · {JSON.stringify(s.marker_text)}</option>)}
        </select></label>
        <label className="text-xs text-slate-400">读数<select aria-label="读数" className={selectClass} value={metric} onChange={(e) => setMetric(e.target.value as typeof metric)}>
          <option value="probability">归一化概率 · Δlogprob</option><option value="logit">原始分数 · Δlogit / ΔLSE</option>
        </select></label>
        <label className="text-xs text-slate-400">状态读取层<select aria-label="状态读取层" className={selectClass} value={stateLayer} onChange={(e) => setStateLayer(e.target.value)}>
          {Object.keys(data.pca).filter((key) => key !== "-1").map((key) => <option key={key} value={key}>block {key} 输入</option>)}<option value="-1">最终 norm 输出</option>
        </select></label>
        <div className="md:col-span-4"><div className="flex flex-wrap items-center justify-between gap-3 text-sm"><label htmlFor="bpath-dose">剂量 rel={rel} · α={(rel*data.gap).toFixed(3)}</label>
          <div className="flex gap-2">{DIRECTIONS.map((name) => <button key={name} aria-pressed={direction === name} onClick={() => setDirection(name)} style={{ color: COLORS[name] }} className={`rounded border px-3 py-1 ${direction === name ? "border-slate-300" : "border-slate-700"}`}>{LABELS[name]}</button>)}</div>
        </div><input id="bpath-dose" aria-label="剂量" className="mt-3 w-full accent-emerald-400" type="range" min={0} max={data.dose.length} value={relIndex} onChange={(e) => setRelIndex(Number(e.target.value))} /></div>
      </section>
      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <section className="rounded-xl border border-slate-700 bg-slate-900/60 p-5">
          <h2 className="font-semibold">{targetName} 随剂量的变化</h2>
          <p className="mt-2 text-xs leading-5 text-slate-400">t={site.t}，注入绝对位置 {site.inject_abs}。{metric === "probability" ? "完整 softmax 后的 Δlogprob；正值表示概率增加。" : "未归一化的分数变化；集合读数为 logsumexp，不能直接当作概率。"}</p>
          <Chart xs={[0,...data.dose]} series={doseCurves} selectedX={rel} title="逐位置剂量响应" />
          <div className="flex flex-wrap gap-5 text-xs">{doseCurves.map((s) => <span key={s.name} style={{ color: s.color }}>{s.name} · {fmt(s.ys[relIndex])}</span>)}</div>
          <p className="mt-4 text-xs text-slate-400">固定剂量 {data.dose.join(" / ")}；同一个随机方向用于全部位置。最小剂量的数值受 {data.dtype} 精度影响，不等于零点导数。</p>
        </section>
        <StatePlot curves={curves} selected={direction} rel={relIndex} layer={stateLayer} coverage={data.pca[stateLayer].explained_variance.reduce((a,b) => a+b,0)} />
        <section className="rounded-xl border border-slate-700 bg-slate-900/60 p-5">
          <h2 className="font-semibold">改变注入层，效果怎样传播</h2>
          <p className="mt-2 text-xs leading-5 text-slate-400">这张图固定该轨迹首个抽样位置 t={layerSite.t}、+w、rel=1。Norm 后为线性读出校准点，位于所有 block 之后。</p>
          <Chart xs={layers.map((l) => l.layer === -1 ? 28 : l.layer)} labels={layers.map((l) => l.layer === -1 ? "Norm后" : String(l.layer))}
            series={[{ name: "层响应", color: "#7dd3fc", ys: layers.map(layerDelta) }]} title="固定剂量注入层扫描" />
          <p className="text-xs text-slate-400">norm 后逐 token 校准：{calibration?.ok ? "通过" : "未建立"}。校准使用实际状态增量与 lm_head 权重，误差界包括数值舍入。</p>
        </section>
        <section className="rounded-xl border border-slate-700 bg-slate-900/60 p-5">
          <h2 className="font-semibold">从 token 反查方向与响应</h2>
          <p className="mt-2 text-xs leading-5 text-slate-400">点选一行，剂量图切换到该 token。w·U 描述 norm 后空间的直接读出；频次是整个 120 轨迹语料的频次。</p>
          <button onClick={() => setTarget("group")} className="mt-3 text-xs text-sky-300">查看 marker 集合</button>
          <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-xs"><thead className="text-slate-400"><tr><th className="pb-2">token / id</th><th>w·U</th><th>频次</th><th>当前 Δlogprob</th></tr></thead><tbody>
            {data.frequency.rows.map((row,i) => <tr key={row.id} className={`cursor-pointer border-t border-slate-800 ${target === String(row.id) ? "bg-sky-950/60" : "hover:bg-slate-800/70"}`} onClick={() => setTarget(String(row.id))} data-marker-id={row.id}>
              <td className="py-2"><button aria-label={`选择 token ${row.id}`} onClick={() => setTarget(String(row.id))} className="text-left"><code>{JSON.stringify(row.text)}</code><span className="block text-slate-500">{row.id}</span></button></td>
              <td>{fmt(row.dot,5)}</td><td>{(100*row.count/data.frequency.total).toFixed(1)}%</td>
              <td>{fmt(current ? current.readout.marker_logprobs[i]-site.baseline.marker_logprobs[i] : 0)}</td>
            </tr>)}
          </tbody></table></div>
        </section>
      </div>
      <section className="mt-5 rounded-xl border border-slate-700 bg-slate-900/60 p-5" data-testid="bpath-norm-mechanism">
        <h2 className="font-semibold">状态传播与 RMSNorm 的机制分解</h2>
        <p className="mt-2 text-xs leading-5 text-slate-400">固定该轨迹首个位置 t={trajectory.norm_transport.t}，方向与剂量跟随上方选择。范数增益衡量位移大小，不能解释为语义功能的贡献比例。</p>
        {transport ? <>
          <div className="mt-4 grid gap-4 text-sm sm:grid-cols-3">
            <p>后续 block 范数增益 <b className="block text-sky-300">{transport.block_norm_gain.toFixed(3)}×</b></p>
            <p>最终 RMSNorm 范数增益 <b className="block text-sky-300">{transport.norm_norm_gain.toFixed(4)}×</b></p>
            <p>norm 后位移与注入方向的余弦 <b className="block text-sky-300">{transport.post_norm_alignment.toFixed(4)}</b></p>
          </div>
          <p className="mt-4 text-xs leading-5 text-slate-300">{JSON.stringify(data.marker_text[mechanismToken])} / {data.marker_ids[mechanismToken]}：理想 RMSNorm 的前传项 · U = {fmt(transport.marker_logit_transmitted[mechanismToken])}，重缩放项 · U = {fmt(transport.marker_logit_rescaled[mechanismToken])}。{tokenIndex < 0 ? "此 token 是首位置 baseline 中概率最高的 marker。" : "此 token 跟随反查选择。"}</p>
          <p className="mt-2 text-xs leading-5 text-slate-400">N(h₁)−N(h₀) = γ⊙(h₁−h₀)/r₁ + γ⊙h₀·(1/r₁−1/r₀)，rᵢ = √(mean(hᵢ²)+ε)。与实际状态位移的重建校验{transport.norm_reconstruction_ok ? "通过数值误差界" : "失败"}；浮点 logits 还包含输出舍入。概率变化还需要减去完整 softmax 的归一化变化。</p>
        </> : <p className="mt-3 text-sm text-slate-400">零剂量的状态位移为零；范数增益和方向余弦没有定义。</p>}
      </section>
      <section className="mt-5 rounded-xl border border-slate-700 bg-slate-900/60 p-5 text-sm">
        <h2 className="font-semibold">这个干预改变了什么</h2>
        <p className="mt-2 leading-6 text-slate-300" data-testid="bpath-current-effect">当前 {LABELS[direction]}、rel={rel}：marker 集合 Δlogprob={fmt(current?.d_marker_logprob ?? 0,6)}，raw ΔLSE={fmt(current?.d_marker_lse ?? 0,6)}。baseline 集合概率 {probability(site.baseline.marker_logprob)}，干预后 {probability(current?.readout.marker_logprob ?? site.baseline.marker_logprob)}。</p>
        <p className="mt-2 leading-6 text-slate-400">这说明该前缀下一步的概率如何变化。验证、修订和推理深度的功能归属还需要独立的行为判据与内部计算对应；图中的位移与自检词变化没有提供这项对应。</p>
        <details className="mt-4"><summary className="cursor-pointer text-sky-300">固定前缀与来源</summary><pre className="mt-3 overflow-auto whitespace-pre-wrap rounded bg-slate-950 p-3 text-xs text-slate-400">{site.prefix_tail}</pre>
          <p className="mt-2 break-all text-xs text-slate-500">向量 SHA-256：{data.vector_sha256}。本扫描 {data.trajectories.reduce((n,t) => n+t.sites.length,0)} 个位置。重复 baseline：{site.baseline_repeated_exact ? "逐位一致" : "失败"}。</p>
          <a className="mt-2 inline-block text-xs text-sky-300" href="/latent/data/bpath_explorer.json">读取完整测量数据</a>
        </details>
      </section>
    </div>
  </main>;
}

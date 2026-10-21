"use client";

import { useEffect, useMemo, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Html, Line, OrbitControls } from "@react-three/drei";
import { Quaternion, Vector3 } from "three";
import { useWebGLSupport } from "@/lib/use-webgl";
import { add, subtract, norm, fmt, signed, ARM_LABEL, ARM_COLOR, SOURCE_COLOR, REGIME_LABEL, REGIME_BADGE, regimeOf } from "@/lib/circuit-landscape";
import type { Arm, Evidence, Point, Regime, Site, LayerTrace, Unit } from "@/lib/circuit-landscape";
import SteeringProgressMap from "@/components/SteeringProgressMap";

const panel = "rounded-2xl border border-slate-800 bg-slate-900/60";
const select = "rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100";
const label = "text-[11px] uppercase tracking-wider text-slate-500";
type Arrow = { from: Point; to: Point; color: string; label: string; dashed?: boolean };

function Arrow3D({ arrow, scale }: { arrow: Arrow; scale: (p: Point) => Point }) {
  const from = scale(arrow.from), to = scale(arrow.to);
  const dir = new Vector3(...subtract(to,from));
  const length = dir.length();
  if (length < 1e-7) return null;
  const rotation = new Quaternion().setFromUnitVectors(new Vector3(0,1,0),dir.normalize());
  return <group>
    <Line points={[from,to]} color={arrow.color} lineWidth={1.7} dashed={arrow.dashed} dashSize={0.07} gapSize={0.04} />
    <mesh position={to} quaternion={rotation}><coneGeometry args={[0.035,0.1,10]} /><meshBasicMaterial color={arrow.color} /></mesh>
  </group>;
}

function Plot({ paths, selected, onSelect, arrows = [], local = false, forceView, extentPoints }: {
  paths: { sites: Site[]; points: Point[]; color: string; ghost?: boolean }[];
  selected: Site; onSelect?: (site: Site) => void; arrows?: Arrow[]; local?: boolean; forceView?: "2d" | "3d";
  /** 用于算缩放的点集。**必须与勾选状态无关**，否则勾一下"展开写入"整张图会重排。 */
  extentPoints?: Point[];
}) {
  const support = useWebGLSupport();
  const [view,setView] = useState<"2d" | "3d">("3d");
  const base = extentPoints ?? paths.flatMap(p => p.points);
  const all = base.length > 0 ? base : [[0,0,0] as Point];
  const lo = [0,1,2].map(i=>Math.min(...all.map(p=>p[i]))) as Point;
  const hi = [0,1,2].map(i=>Math.max(...all.map(p=>p[i]))) as Point;
  const mid = lo.map((v,i)=>(v+hi[i])/2) as Point;
  const extent = Math.max(...hi.map((v,i)=>v-lo[i]),1e-9);
  const scale = (p: Point): Point => p.map((v,i)=>(v-mid[i])/extent*6) as Point;
  const use3d = support === true && (forceView ?? view) === "3d";
  return <div>
    <div className="flex items-center justify-between px-5 pt-4 text-xs text-slate-500">
      <span>{local ? "当前 block 的实际残差写入" : "每个点 = 实际 block 输出 hidden state"}</span>
      <div className="flex gap-1">{(["2d","3d"] as const).map(v=><button key={v} disabled={v === "3d" && support === false} aria-pressed={(forceView ?? view) === v} onClick={()=>setView(v)} className={`rounded px-2 py-1 disabled:opacity-30 ${(forceView ?? view) === v ? "bg-slate-700 text-white" : "text-slate-400"}`}>{v.toUpperCase()}</button>)}</div>
    </div>
    <div className={local ? "h-[300px]" : "h-[440px] xl:h-[510px]"} data-testid={local ? "write-plot" : "landscape-plot"} data-view={use3d ? "3d" : "2d"}>
      {use3d ? <Canvas camera={{position:[5,3.5,6],fov:45}} dpr={[1,1.5]} gl={{preserveDrawingBuffer:true}}>
        <axesHelper args={[3]} />
        <Html position={[3.5,0,0]}><span className="pointer-events-none text-[10px] text-slate-500">PC1</span></Html>
        <Html position={[0,3.5,0]}><span className="pointer-events-none text-[10px] text-slate-500">PC2</span></Html>
        <Html position={[0,0,3.5]}><span className="pointer-events-none text-[10px] text-slate-500">PC3</span></Html>
        {paths.map((path,index)=><group key={index}>
          {path.points.length > 1 && <Line points={path.points.map(scale)} color={path.color} transparent opacity={path.ghost ? 0.28 : 0.8} dashed={path.ghost} dashSize={0.06} gapSize={0.05} lineWidth={path.ghost ? 1 : 1.8} />}
          {path.points.map((p,i)=><mesh key={i} position={scale(p)} onClick={e=>{e.stopPropagation();onSelect?.(path.sites[i]);}}>
            <sphereGeometry args={[path.sites[i]?.trajectory === selected.trajectory && path.sites[i]?.t === selected.t ? 0.065 : 0.033,12,12]} />
            <meshBasicMaterial color={path.color} transparent opacity={path.ghost ? 0.35 : 1} />
          </mesh>)}
        </group>)}
        {arrows.map((a,i)=><Arrow3D key={i} arrow={a} scale={scale} />)}
        {local && arrows.slice(0,2).map(a=><Html key={a.label} position={scale(a.to)}><span style={{color:a.color}} className="pointer-events-none whitespace-nowrap rounded bg-slate-950/80 px-1 text-[10px]">{a.label}</span></Html>)}
        <OrbitControls makeDefault />
      </Canvas> : <svg viewBox="-3.4 -3.4 6.8 6.8" className="h-full w-full" aria-label={local ? "实际写入的共享 PCA 投影" : "真实 hidden states 轨迹"} role="img">
        <defs>{arrows.map((a,i)=><marker key={i} id={`${local ? "local" : "main"}-arrow-${i}`} markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L5,2.5 L0,5" fill={a.color} /></marker>)}</defs>
        {[-3,-1.5,0,1.5,3].map(x=><g key={x}><line x1={x} x2={x} y1={-3.1} y2={3.1} stroke="#1e293b" strokeWidth="0.008" /><line x1={-3.2} x2={3.2} y1={x} y2={x} stroke="#1e293b" strokeWidth="0.008" /></g>)}
        <text x="3.15" y="3.4" textAnchor="end" fill="#64748b" fontSize="0.13">PC1</text><text x="-3.4" y="-3.1" fill="#64748b" fontSize="0.13">PC2</text>
        {paths.map((path,index)=><g key={index} opacity={path.ghost ? 0.3 : 1}>
          <polyline points={path.points.map(p=>{const q=scale(p);return `${q[0]},${-q[1]}`;}).join(" ")} fill="none" stroke={path.color} strokeWidth={path.ghost ? 0.015 : 0.025} strokeDasharray={path.ghost ? ".07 .05" : undefined} />
          {path.points.map((p,i)=>{const q=scale(p),s=path.sites[i],active=s?.trajectory === selected.trajectory && s?.t === selected.t;return <circle key={i} cx={q[0]} cy={-q[1]} r={active ? .065 : .035} fill={path.color} stroke={active ? "white" : "none"} strokeWidth=".017" tabIndex={onSelect ? 0 : undefined} role={onSelect ? "button" : undefined} aria-label={s ? `${s.trajectory} t=${s.t}` : undefined} onKeyDown={e=>{if((e.key === "Enter" || e.key === " ") && s) onSelect?.(s);}} onClick={()=>s && onSelect?.(s)} style={{cursor:onSelect ? "pointer" : "default"}}><title>{s ? `${s.trajectory} · t=${s.t}` : "hidden state"}</title></circle>;})}
        </g>)}
        {arrows.map((a,i)=>{const f=scale(a.from),t=scale(a.to);return <g key={i}><line x1={f[0]} y1={-f[1]} x2={t[0]} y2={-t[1]} stroke={a.color} strokeWidth=".025" strokeDasharray={a.dashed ? ".08 .04" : undefined} markerEnd={`url(#${local ? "local" : "main"}-arrow-${i})`}><title>{a.label}</title></line>{local && i < 2 && <text x={t[0]+.06} y={-t[1]-.08} fill={a.color} fontSize=".13">{a.label}</text>}</g>;})}
      </svg>}
    </div>
  </div>;
}

/**
 * 写入箭头。
 *
 * ⚠ 账本必须**闭合**：MLP 合计 = 当前单元 + 其余展示单元 + 未展示单元。
 * 旧版把"其余 MLP 合计"画成"合计 − 当前单元"，与 JSON 的 `remainder`
 * （合计 − 全部展示单元）**同名不同义**；这里改成三条虚线，加起来正好是合计。
 */
function writeArrows(trace: LayerTrace, unit?: Unit, delta?: LayerTrace): Arrow[] {
  const start = delta ? [0,0,0] as Point : trace.states.input;
  const attention = delta ? subtract(trace.writes.attention,delta.writes.attention) : trace.writes.attention;
  const mlp = delta ? subtract(trace.writes.mlp,delta.writes.mlp) : trace.writes.mlp;
  const middle = add(start,attention);
  const arrows: Arrow[] = [
    {from:start,to:middle,color:"#7dd3fc",label:delta ? "Δattention" : "attention"},
    {from:middle,to:add(middle,mlp),color:"#5eead4",label:delta ? "ΔMLP 合计" : "MLP 合计"},
  ];
  if (unit) {
    const b = delta?.units.find(u=>u.id === unit.id);
    const write = delta ? subtract(unit.write,b?.write ?? [0,0,0]) : unit.write;
    arrows.push({from:middle,to:add(middle,write),color:"#fbbf24",label:`unit ${unit.id}${delta ? " Δ写入" : " 写入"}`});
    // 其余**展示**单元（当前选中那个之外的）——把账本补齐
    const others = trace.units.filter(u=>u.id !== unit.id)
      .reduce((acc,u)=>add(acc,u.write),[0,0,0] as Point);
    if (norm(others) > 1e-9) {
      arrows.push({from:middle,to:add(middle,others),color:"#a78bfa",label:"其余展示单元",dashed:true});
    }
    // 未展示单元 —— 与 JSON 的 remainder 同义
    const remainder = trace.remainder;
    if (norm(remainder) > 1e-9) {
      arrows.push({from:middle,to:add(middle,remainder),color:"#64748b",label:"未展示单元",dashed:true});
    }
  }
  return arrows;
}

export default function CircuitLandscape() {
  const [data,setData] = useState<Evidence | null>(null), [error,setError] = useState("");
  const [source,setSource] = useState(""), [t,setT] = useState(0), [layer,setLayer] = useState("25");
  const [arm,setArm] = useState<Arm>("plus"), [unitId,setUnitId] = useState<number | null>(null);
  const [allSources,setAllSources] = useState(true), [showWrites,setShowWrites] = useState(true);
  const [delta,setDelta] = useState(false), [sort,setSort] = useState<"response" | "activation">("response");
  useEffect(()=>{
    const controller=new AbortController();
    fetch("/latent/data/circuit_landscape.json",{signal:controller.signal}).then(r=>{if(!r.ok)throw Error(`HTTP ${r.status}`);return r.json();}).then((j:Evidence)=>{
      if(j.schema !== "steer3d.circuit_landscape/1" || !j.complete || !j.sites.length)throw Error("采集未完成或数据格式不匹配");
      setData(j);setSource(j.sources[0].id);setT(j.sources[0].anchor);
    }).catch(e=>{if(e.name !== "AbortError")setError(e.message);});
    return ()=>controller.abort();
  },[]);
  const site=useMemo(()=>data?.sites.find(s=>s.trajectory === source && s.t === t),[data,source,t]);
  if(error)return <main className="min-h-screen bg-slate-950 p-10 text-rose-300">数据加载失败：{error}</main>;
  if(!data || !site)return <main className="min-h-screen bg-slate-950 p-10 text-slate-400">正在读取真实状态与原生写入…</main>;
  const row=site.arms[arm].layers[layer], baseline=site.arms.baseline.layers[layer];
  const units=[...row.units].sort((a,b)=>(sort === "response" ? b.response_norm-a.response_norm : b.write_norm-a.write_norm));
  const unit=units.find(u=>u.id === unitId) ?? units[0];
  const currentSource=data.sources.find(s=>s.id === source)!;
  const sites=data.sites.filter(s=>s.trajectory === source);
  const choose=(s:Site)=>{setSource(s.trajectory);setT(s.t);setUnitId(null);};
  const paths=data.sources.filter(s=>allSources || s.id === source).flatMap((s)=>{
    const subset=data.sites.filter(p=>p.trajectory === s.id),color=SOURCE_COLOR[data.sources.indexOf(s)];
    const selected={sites:subset,points:subset.map(p=>p.arms[arm].layers[layer].states.out),color};
    return arm === "baseline" ? [selected] : [{sites:subset,points:subset.map(p=>p.arms.baseline.layers[layer].states.out),color,ghost:true},selected];
  });
  const arrows=writeArrows(row,unit);
  const localArrowsBase=arrows;
  const localArrowsDelta=writeArrows(row,unit,baseline);
  const localArrows=delta ? localArrowsDelta : localArrowsBase;
  const localPointsBase=[row.states.input,row.states.after_attention,row.states.out];
  const localPointsDelta=[[0,0,0] as Point,add(subtract(row.writes.attention,baseline.writes.attention),subtract(row.writes.mlp,baseline.writes.mlp))];
  const localPoints=delta ? localPointsDelta : localPointsBase;
  // 缩放用的点集：与"展开写入"和"Δ写入"两个勾选**无关**，所以勾选不会让整张图重排
  const mainExtent=[...paths.flatMap(p=>p.points), ...arrows.flatMap(a=>[a.from,a.to])];
  const localExtent=[...localPointsBase, ...localPointsDelta,
    ...localArrowsBase.flatMap(a=>[a.from,a.to]), ...localArrowsDelta.flatMap(a=>[a.from,a.to])];
  const coverage=data.pca[layer].explained_variance;
  const baseLP=site.arms.baseline.readout.marker_logprob;
  const pBase=site.p_base ?? Math.exp(baseLP);
  const regime: Regime = site.regime ?? regimeOf(pBase);
  const blockEffect=site.arms.plus.readout.marker_logprob-site.arms.block.readout.marker_logprob;
  const restoreEffect=site.arms.restore.readout.marker_logprob-baseLP;
  const matched=site.arms.plus.layers[layer].units.find(u=>u.id === unit.id)!;
  const naturalChange=matched.natural_product-matched.baseline_product;
  const projWrite=norm(unit.write);
  const projDeltaOf=(u:Unit):number|null=>{
    const b=site.arms.baseline.layers[layer].units.find(x=>x.id===u.id);
    return b ? norm(subtract(u.write,b.write)) : null;
  };
  // 随机臂数量：由 arms 里以 "random" 开头的键数得到（采集器若改成抽多个方向，键会变成 random0..randomN）
  const randomArms=data.arms.filter(a=>a.startsWith("random")).length;
  const randomQuantile=randomArms>0 ? randomArms/(randomArms+1) : null;
  const decision=data.readout_summary?.decision;
  const floorBand=data.readout_summary?.floor;
  const isFloor=regime === "floor";
  const ledger=data.ledger?.per_layer ?? [];
  return <main className="min-h-screen bg-[#080e1a] px-4 py-6 text-slate-200 sm:px-8" data-testid="circuit-landscape" data-source={source} data-position={t} data-layer={layer} data-arm={arm}
      data-regime={regime} data-p-base={pBase} data-snr={String(site.snr ?? "")}
      data-random-arms={String(randomArms)} data-random-quantile={String(randomQuantile ?? "")}
      data-ledger-space={data.ledger?.space ?? ""} data-alpha={String(site.alpha)} data-h-norm={String(site.h_norm)}>
    <div className="mx-auto max-w-[1560px]">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div><p className="text-[11px] uppercase tracking-[.23em] text-teal-400">Hidden states × Native circuits</p><h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">推理状态与真实写入</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">在 hidden states 中追踪推理，展开每个状态的原生计算，再查看向量改变了什么。</p></div>
        <nav className="flex gap-4 pt-2 text-xs text-slate-400"><a className="hover:text-teal-300" href="/">实时轨迹</a><a className="hover:text-teal-300" href="/bpath-explorer">向量响应实验</a><a className="hover:text-teal-300" href="/latent/index.html">隐空间观察台</a></nav>
      </header>

      {/* ---- 口径条：常驻，不随面板切换消失 ---- */}
      <section className={`${panel} mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 text-[11px]`}
               data-context-bar="true" data-context-p={pBase} data-context-regime={regime}>
        <span className="text-slate-500">口径</span>
        <span className="text-slate-300">baseline p = <b className="font-mono">{pBase.toFixed(4)}</b></span>
        <span className={`rounded px-2 py-0.5 ${REGIME_BADGE[regime].cls}`} data-regime-badge={regime}>
          {REGIME_LABEL[regime]}
        </span>
        <span className="text-slate-300">α = <b className="font-mono">{fmt(site.alpha, 2)}</b>（= 0.1·‖h‖，‖h‖ = {fmt(site.h_norm, 1)}）</span>
        <span className="text-slate-300">随机臂 n = <b className="font-mono">{randomArms}</b>
          {randomQuantile !== null && <span className="text-slate-500">（只能否证到 {randomQuantile.toFixed(2)} 分位）</span>}</span>
        <span className="text-slate-300">信噪比 |Δ+v|/|Δ随机| = <b className="font-mono">{site.snr === null ? "—" : site.snr.toFixed(2)}</b></span>
        {isFloor && <span className="rounded bg-amber-950/50 px-2 py-0.5 text-amber-300">此位点在底噪带：Δ 不得作为行为主张</span>}
        {site.anchor && <span className="rounded bg-teal-950/50 px-2 py-0.5 text-teal-300">下一个 token 就是 marker</span>}
      </section>

      <div className="mt-5 flex flex-wrap gap-x-6 gap-y-2 border-y border-slate-800 py-3 text-xs text-slate-400"><span><b className="font-medium text-white">{data.model}</b> · {data.dtype}</span><span>2 个问题 · 4 条来源轨迹 · {data.guards.captured_sites} 个连续位置</span><span>{data.guards.captured_forwards} 次主测量 · 6 种条件</span><span className="text-teal-400">真实模型重跑 · 固定共享 PCA</span></div>
      <section className={`${panel} mt-5 flex flex-wrap items-end gap-4 p-4`}>
        <label className="flex min-w-[220px] flex-1 flex-col gap-1.5"><span className={label}>问题与轨迹</span><select aria-label="问题与轨迹" className={select} value={source} onChange={e=>{const s=data.sources.find(x=>x.id === e.target.value)!;setSource(s.id);setT(s.anchor);setUnitId(null);}}>{data.sources.map(s=><option key={s.id} value={s.id}>{s.problem_id} · {s.mode}</option>)}</select></label>
        <label className="flex flex-col gap-1.5"><span className={label}>读取层</span><select aria-label="读取层" className={select} value={layer} onChange={e=>{setLayer(e.target.value);setUnitId(null);}}>{data.layers.map(l=><option key={l} value={l}>block {l}</option>)}</select></label>
        <div className="flex flex-col gap-1.5"><span className={label}>相同前缀下的条件</span><div className="flex flex-wrap gap-1">{data.arms.map(a=><button key={a} aria-pressed={arm === a} onClick={()=>setArm(a)} className={`rounded-lg border px-3 py-2 text-xs ${arm === a ? "border-slate-400 bg-slate-800" : "border-slate-800"}`} style={{color:ARM_COLOR[a]}}>{ARM_LABEL[a]}</button>)}</div></div>
        <label className="ml-auto flex items-center gap-2 pb-2 text-xs text-slate-400"><input type="checkbox" checked={allSources} onChange={e=>setAllSources(e.target.checked)} />叠加四条轨迹</label>
      </section>
      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_410px]">
        <div className="min-w-0 space-y-5">
          <section className={panel}>
            <div className="flex items-start justify-between gap-3 px-5 pt-5"><div><h2 className="text-base font-medium text-white">Hidden-state landscape</h2><p className="mt-1 text-xs leading-5 text-slate-400">连续局部窗口 · block {layer} 输出 · 点击状态点展开计算</p></div><label className="flex items-center gap-2 text-xs text-slate-400"><input type="checkbox" checked={showWrites} onChange={e=>setShowWrites(e.target.checked)} />展开当前写入</label></div>
            <Plot paths={paths} selected={site} onSelect={choose} arrows={showWrites ? arrows : []} extentPoints={mainExtent} />
            <div className="flex flex-wrap gap-4 px-5 text-[11px]">{data.sources.filter(s=>allSources || s.id === source).map(s=><button key={s.id} onClick={()=>{setSource(s.id);setT(s.anchor);}} style={{color:SOURCE_COLOR[data.sources.indexOf(s)]}}>{s.problem_id} / {s.mode}</button>)}<span className="text-slate-500">虚线：原始 · 实线：{ARM_LABEL[arm]}</span></div>
            <p className="px-5 pb-5 pt-3 text-xs leading-5 text-slate-500">前三维覆盖 {(coverage.reduce((a,b)=>a+b,0)*100).toFixed(1)}% 方差（PC1 / 2 / 3：{coverage.map(v=>(v*100).toFixed(1)).join(" / ")}%）。同层所有条件共用由原始状态拟合的坐标，局部写入图仅放大显示。</p>
          </section>

          {/* ---- 逐层写入账本：32 site 聚合 ---- */}
          {ledger.length > 0 && (
            <section className={`${panel} p-5`} data-testid="ledger-panel" data-ledger-n-sites={String(ledger[0].n_sites)}>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="font-medium text-white">逐层写入账本（{ledger[0].n_sites} 个 site 聚合）</h2>
                <span className="text-[10px] text-slate-500">范数空间：{data.ledger?.space === "true-2048" ? "2048 维真值" : "3 维投影"}</span>
              </div>
              <p className="mt-1 text-[11px] leading-5 text-slate-500">{data.ledger?.note}</p>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-left text-[11px]" data-ledger-table="true">
                  <thead><tr className="border-b border-slate-800 text-slate-500">
                    {["block","attention 写","MLP 写","attention 占比","Δattention","ΔMLP","ΔMLP / MLP 写"].map(v=>
                      <th key={v} className="px-2 py-1.5 font-medium">{v}</th>)}</tr></thead>
                  <tbody>{ledger.map(r=><tr key={r.layer} className="border-b border-slate-800/50 font-mono text-slate-300"
                      data-ledger-row={r.layer} data-ledger-dmlp-ratio={String(r.dmlp_over_mlp)}>
                    <td className="px-2 py-1.5">{r.layer}</td>
                    <td className="px-2 py-1.5">{r.attn_mean.toFixed(1)}</td>
                    <td className="px-2 py-1.5">{r.mlp_mean.toFixed(1)}</td>
                    <td className="px-2 py-1.5">{(r.attn_share*100).toFixed(1)}%</td>
                    <td className="px-2 py-1.5">{r.dattn_mean.toFixed(3)}</td>
                    <td className="px-2 py-1.5">{r.dmlp_mean.toFixed(3)}</td>
                    <td className="px-2 py-1.5 text-amber-300">{(r.dmlp_over_mlp*100).toFixed(2)}%</td>
                  </tr>)}</tbody>
                </table>
              </div>
            </section>
          )}

          <section className={`${panel} p-5`}>
            <div className="flex items-center justify-between"><h2 className="font-medium text-white">当前前缀与下一步</h2><span className="font-mono text-xs text-slate-400">t={t} · {site.n_prefix_tokens} prefix tokens</span></div>
            <div className="mt-4 flex gap-2">{sites.map(s=><button key={s.t} onClick={()=>choose(s)} aria-pressed={s.t === t} className={`flex-1 rounded-lg border py-2 text-xs ${s.t === t ? "border-teal-500 bg-teal-500/10 text-teal-300" : "border-slate-800 text-slate-500"}`}>{s.t}{s.anchor && <span className="block text-[9px]">marker</span>}</button>)}</div>
            <div className="mt-4 whitespace-pre-wrap rounded-xl bg-slate-950 p-4 font-mono text-xs leading-6 text-slate-300" data-testid="prefix-context">{site.context_before}<mark className="rounded bg-teal-400/20 px-1 text-teal-200">{site.next_token}</mark><span className="text-slate-600">{site.context_after.slice(site.next_token.length)}</span></div>
            <p className="mt-2 text-[11px] leading-5 text-slate-500">高亮是原记录的下一个 token；所有实验读取高亮之前的同一前缀。每点都独立在最后一个输入 token 的 block 20 注入，α={fmt(site.alpha)}（= 0.1·‖h‖，相对剂量；与旧 B 路的 rel 0.1 不是同一物理剂量）。条件连线展示局部响应序列。</p>
            <details className="mt-4 text-xs text-slate-400"><summary className="cursor-pointer">查看完整问题与模式提示</summary><pre className="mt-3 max-h-56 overflow-auto whitespace-pre-wrap rounded bg-slate-950 p-3 leading-5">{currentSource.prompt_text}</pre></details>
          </section>
          <section className={`${panel} overflow-hidden`}>
            <div className="flex items-center justify-between gap-3 p-5"><div><h2 className="font-medium text-white">此刻写入最大的原生单元（按构造选出的展示集合）</h2><p className="mt-1 text-[11px] leading-5 text-slate-500">展示集合 = 原始写入最大的 6 个 ∪ +v 响应最大的 6 个；共 {row.units.length} / {row.total_native_units}。<b>「响应排序」是按定义构造出来的，不是重要性证据。</b></p></div><select aria-label="单元排序" className={`${select} max-w-[130px]`} value={sort} onChange={e=>setSort(e.target.value as typeof sort)}><option value="response">按响应排序</option><option value="activation">按写入排序</option></select></div>
            <p className="px-5 pb-3 text-[10px] leading-5 text-slate-600">每层 32 个冻结载体候选中，平均只有约 1.2 个会落进这张表 —— 这张表<b>不是</b>载体的视图。</p>
            <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead className="bg-slate-950/70 text-[10px] uppercase text-slate-500"><tr>{["原生单元","符号路径","实际 a","Δa","‖写入‖(2048)","3D 投影","‖Δ写入‖(2048)","3D 投影 Δ"].map(v=><th key={v} className="px-4 py-3 font-medium">{v}</th>)}</tr></thead><tbody>{units.map(u=><tr key={u.id} tabIndex={0} aria-selected={u.id === unit.id} onClick={()=>setUnitId(u.id)} onKeyDown={e=>{if(e.key === "Enter")setUnitId(u.id);}} className={`cursor-pointer border-t border-slate-800/70 font-mono hover:bg-slate-800/60 ${u.id === unit.id ? "bg-teal-500/10" : ""}`} data-unit-row={u.id} data-unit-selected={String(u.id === unit.id)}><td className="px-4 py-3 text-slate-200">L{layer}:{u.id}{u.patched && <span className="ml-2 text-amber-400">已替换</span>}</td><td className="px-4 py-3 text-slate-400">{u.regime}</td><td className="px-4 py-3">{fmt(u.product)}</td><td className="px-4 py-3 text-amber-300">{signed(u.product-u.baseline_product)}</td><td className="px-4 py-3 text-slate-400">{fmt(u.write_norm)}</td><td className="px-4 py-3 text-slate-500" data-unit-proj-norm={String(norm(u.write))}>{fmt(norm(u.write))}</td><td className="px-4 py-3 text-teal-300">{fmt(u.response_norm)}</td><td className="px-4 py-3 text-teal-300/70">{projDeltaOf(u) === null ? "—" : fmt(projDeltaOf(u)!)}</td></tr>)}</tbody></table></div>
          </section>
        </div>
        <aside className="min-w-0 space-y-5">
          <section className={panel}>
            <div className="flex items-center justify-between px-5 pt-5"><h2 className="font-medium text-white">状态为什么移动</h2><label className="flex items-center gap-2 text-xs text-slate-400"><input type="checkbox" checked={delta} onChange={e=>setDelta(e.target.checked)} />查看 Δ写入</label></div>
            <Plot paths={[{sites:localPoints.map(()=>site),points:localPoints,color:"#f8fafc"}]} selected={site} arrows={localArrows} local extentPoints={localExtent} />
            <div className="grid grid-cols-2 gap-x-3 gap-y-2 px-5 text-[11px]"><span className="text-sky-300">↗ attention 写入</span><span className="text-teal-300">↗ MLP 合计</span><span className="text-amber-300">↗ 当前单元写入</span><span className="text-violet-300">⇢ 其余展示单元</span><span className="text-slate-400">⇢ 未展示单元</span><span className="text-slate-600">三条相加 = MLP 合计</span></div>
            <p className="px-5 pb-5 pt-3 text-[11px] leading-5 text-slate-500">{delta ? "此图以零点展示 Δattention + ΔMLP；它是本层更新的差，不包含入层状态差。" : "白点依次为真实入层、attention 后、出层状态。黄色 / 紫色 / 灰色箭头是 MLP 的三部分，相加得到绿色合计。"} 所有箭头使用主图同一个线性投影；箭头长度是 <b>3 维投影</b>，与单元表里的 2048 维真值范数不是同一个量。</p>
          </section>
          <section className={`${panel} p-5`} data-testid="unit-detail">
            <div className="flex items-center justify-between"><h2 className="font-medium text-white">L{layer} · unit {unit.id}</h2><span className="rounded bg-slate-800 px-2 py-1 text-[10px] text-slate-400">原生坐标</span></div>
            <div className="mt-4 rounded-xl bg-slate-950 p-4 font-mono text-sm"><div className="text-slate-500">SiLU(g) × u = a</div><div className="mt-2 text-slate-200">{fmt(unit.gate)} × {fmt(unit.value)}</div><div className="mt-1 text-xl text-teal-300">= {fmt(unit.natural_product)}</div>{unit.patched && <div className="mt-3 text-xs text-amber-300">干预后实际使用 a = {fmt(unit.product)}</div>}</div>
            <dl className="mt-4 space-y-3 text-xs"><div className="flex justify-between"><dt className="text-slate-500">原始 product</dt><dd className="font-mono">{fmt(unit.baseline_product)}</dd></div><div className="flex justify-between"><dt className="text-slate-500">+v 自然 Δproduct</dt><dd className="font-mono text-amber-300">{signed(naturalChange)}</dd></div><div className="flex justify-between"><dt className="text-slate-500">所属干预组</dt><dd>{unit.in_frozen_group ? "冻结的 256 单元组" : "当前未做单元级因果验证"}</dd></div><div className="flex justify-between"><dt className="text-slate-500">‖写入‖（2048 维真值）</dt><dd className="font-mono">{fmt(unit.write_norm)}</dd></div><div className="flex justify-between"><dt className="text-slate-500">当前 3 维投影写入长度</dt><dd className="font-mono">{fmt(projWrite)}</dd></div></dl>
            <p className="mt-4 text-[11px] leading-5 text-slate-500">当前证据解释了这个单元的实际计算与写入。概念名称需进一步结合跨上下文预测和反例验证。</p>
          </section>
          <section className={`${panel} p-5`} data-testid="causal-readout" data-readout-regime={site.regime}>
            <h2 className="font-medium text-white">同步因果读数</h2><p className="mt-2 text-[11px] leading-5 text-slate-500">完整 softmax 的 marker 集合 ΔlogP（Wait / Let / maybe / Hmm）。表示下一步 token 倾向。</p>
              {isFloor && (
              <p className="mt-3 rounded-lg bg-amber-950/40 px-3 py-2 text-[11px] leading-5 text-amber-300"
                 data-readout-warning="floor">
                当前位点 baseline p = {pBase.toExponential(2)}，落在<b>底噪带</b>：
                这里的 ΔlogP 是尾概率的统计量，<b>不得作为行为主张</b>，也不得与其它位点聚合。
              </p>
            )}
            <div className="mt-4 space-y-3">{data.arms.map(a=>{const value=site.arms[a].readout.marker_logprob-baseLP;const bound=Math.max(...data.arms.map(v=>Math.abs(site.arms[v].readout.marker_logprob-baseLP)),.001);return <div key={a} className="grid grid-cols-[80px_1fr_58px] items-center gap-2 text-xs" data-readout-row={a} data-readout-value={String(value)}><span style={{color:ARM_COLOR[a]}}>{ARM_LABEL[a]}</span><div className="relative h-3 rounded bg-slate-950"><div className="absolute bottom-0 left-1/2 top-0 w-px bg-slate-700"/><div className="absolute top-1 h-1 rounded" style={{background:ARM_COLOR[a],width:`${Math.abs(value)/bound*49}%`,left:value >= 0 ? "50%" : `${50-Math.abs(value)/bound*49}%`}} /></div><span className="text-right font-mono text-slate-300">{signed(value)}</span></div>;})}</div>
            <div className="mt-5 grid grid-cols-2 gap-3 border-t border-slate-800 pt-4 text-xs"><div><span className="text-slate-500">阻断效果：+v − block</span><div className="mt-1 font-mono text-amber-300">{signed(blockEffect,5)}</div></div><div><span className="text-slate-500">恢复效果：restore − 原始</span><div className="mt-1 font-mono text-blue-300">{signed(restoreEffect,5)}</div></div></div>
            {decision && (
              <div className="mt-4 border-t border-slate-800 pt-4 text-[11px] leading-5" data-readout-summary="decision">
                <p className="text-slate-500">决策带（{decision.n_sites} 个可读位点）汇总：</p>
                <p className="mt-1 font-mono text-slate-300">+v {signed(decision.arms.plus.mean,4)} nats · −v {signed(decision.arms.minus.mean,4)} · random {signed(decision.arms.random.mean,4)}</p>
                <p className="mt-1 text-slate-500">信噪比中位数 {decision.snr_median ?? "—"}；这是本轮唯一可作行为主张的口径。</p>
                {floorBand && <p className="mt-1 text-amber-400/80">底噪带（{floorBand.n_sites} 个）均值 {signed(floorBand.arms.plus.mean,4)} nats —— 数字大但不可用。</p>}
              </div>
            )}
            <p className="mt-3 text-[11px] leading-5 text-slate-500">阻断／恢复针对跨 block 20–27 的冻结 256 单元组。该读数属于整个组，尚不能归给当前选中的单个单元。</p>
            <details className="mt-4 text-xs text-slate-400"><summary className="cursor-pointer">当前条件预测的下一步 token</summary><div className="mt-2 space-y-2">{site.arms[arm].readout.top_tokens.map(token=><div key={token.id} className="flex justify-between font-mono"><span>{JSON.stringify(token.text)}</span><span>{(token.probability*100).toFixed(2)}%</span></div>)}</div></details>
          </section>
        </aside>
      </div>

      {/* ---- 进度图面板 ---- */}
      <section className="mt-5">
        <SteeringProgressMap />
      </section>

      <footer className={`${panel} mt-5 p-5 text-[11px] leading-6 text-slate-500`}>
        <div className="flex flex-wrap gap-x-7 gap-y-1"><span className="text-teal-400">● 残差更新已闭合</span><span>当前相对误差 {row.closure_relative.toExponential(2)}</span><span>全部测量最大误差 {data.guards.max_residual_closure_relative.toExponential(2)}</span><span>重复 baseline / 恒等替换：{data.guards.baseline_repeat_exact && data.guards.identity_patch_exact ? "通过" : "未通过"}</span></div>
        <p className="mt-2">h_out = h_input + attention + Σ aᵢdᵢ（浮点误差内）。当前是实际执行的局部计算子图，attention 展示合计写入；跨 token 的完整因果连边还需路径干预验证。向量 SHA256：<span className="break-all font-mono">{data.vector_sha256}</span></p>
        <p className="mt-2">研究思路：<a className="text-slate-400 underline" href="https://already-clean.goodfire.com" target="_blank" rel="noreferrer">Goodfire 原生单元分析</a> · <a className="text-slate-400 underline" href="https://arxiv.org/abs/2503.22165" target="_blank" rel="noreferrer">Landscape of Thoughts 轨迹组织</a>。此处以真实 hidden states 作为展示坐标。</p>
      </footer>
    </div>
  </main>;
}

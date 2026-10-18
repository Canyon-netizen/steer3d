#!/usr/bin/env python3
"""Build the presentable reasoning-path / vector-intervention landscape.

Inputs:
  * remote capture: experiments/reasoning_path_v1/remote/reasoning_path.json
    + reasoning_path_states.npz (6 sources x 5 arms x layers 10/20/27)
  * local dataset per-token hidden states for the full baseline route.

Outputs:
  * reasoning_path.json  (PCA-coordinates, arrows, behaviour)
  * reasoning_path.png   (3D route + behaviour panel)
  * reasoning_path.html  (self-contained interactive page)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
REMOTE = ROOT / "experiments/reasoning_path_v1/remote_l21"
DATA_ROOT = ROOT / "datasets/aime_qwen3_1p7b_32k_fp32/aime"
OUT = ROOT / "experiments/reasoning_path_v1/reasoning_path.json"
PNG = ROOT / "experiments/reasoning_path_v1/reasoning_path.png"
BEHAVIOUR_PNG = ROOT / "experiments/reasoning_path_v1/reasoning_path_behaviour.png"
HTML = ROOT / "experiments/reasoning_path_v1/reasoning_path.html"
PUBLIC = ROOT / "frontend/public/reasoning-path.html"
LAYER = 21
MAX_ROUTE_POINTS = 240


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def downsample_indices(length: int, limit: int, keep: list) -> list:
    if length <= limit:
        return list(range(length))
    chosen = set(np.linspace(0, length - 1, limit).astype(int).tolist())
    chosen.update(index for index in keep if 0 <= index < length)
    return sorted(chosen)


def fit_pca(points: np.ndarray, k: int = 3):
    mean = points.mean(axis=0)
    centered = points - mean
    _u, _s, vt = np.linalg.svd(centered, full_matrices=False)
    components = vt[:k]
    explained = (_s[:k] ** 2) / max(float((_s ** 2).sum()), 1e-12)
    return mean, components, explained.tolist()


def project(points: np.ndarray, mean: np.ndarray, components: np.ndarray):
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        return (np.asarray(points) - mean) @ components.T


def main() -> int:
    capture = load_json(REMOTE / "reasoning_path.json")
    states = np.load(REMOTE / "reasoning_path_states.npz")
    layer = int(LAYER)
    arms = capture["arms"]
    source_rows = []
    pca_points = []
    for source in capture["sources"]:
        source_id = source["id"]
        path = DATA_ROOT / (source_id + ".npz")
        with np.load(path) as data:
            prompt = data["prompt_token_ids"].astype(np.int64)
            hidden = data["hidden_states"][:, layer, :].astype(np.float64)
        prompt_len = int(len(prompt))
        start = int(source["start"])
        end = int(source["end"])
        gen_start = start - prompt_len
        gen_end = end - prompt_len
        if gen_start < 0 or gen_end > len(hidden):
            raise SystemExit("window does not align for " + source_id)
        anchor_t = int(source["anchor_t"])
        keep = list(range(max(0, gen_start - 8), min(len(hidden), gen_end + 8))) + [anchor_t]
        route_indices = downsample_indices(len(hidden), MAX_ROUTE_POINTS, keep)
        route = hidden[route_indices]
        window_base = states["%s__baseline__L%d" % (source_id, layer)].astype(np.float64)
        pca_points.append(route)
        pca_points.append(window_base)
        source_rows.append({
            "id": source_id, "marker": int(source["marker"]), "anchor_t": anchor_t,
            "prompt_len": prompt_len, "start": start, "end": end,
            "route_indices": route_indices, "route": route,
            "window_base": window_base, "window_start": start, "window_end": end,
        })
    all_points = np.concatenate(pca_points, axis=0)
    mean, components, explained = fit_pca(all_points, k=3)
    records = []
    for row in source_rows:
        route_pc = project(row["route"], mean, components)
        window_pc = {}
        behavior = {}
        deltas = {}
        for arm in ["baseline"] + arms:
            key = "%s__%s__L%d" % (row["id"], arm, layer)
            pc = project(states[key].astype(np.float64), mean, components)
            window_pc[arm] = pc
            behavior[arm] = {
                "entropy": [float(item) for item in capture["sources"][len(records)]["behavior"][arm]["entropy"]],
                "next_logp": [float(item) for item in capture["sources"][len(records)]["behavior"][arm]["next_logp"]],
            }
            deltas[arm] = pc - window_pc["baseline"]
        anchor_index = int(row["anchor_t"] - (row["window_start"] - row["prompt_len"]))
        summary = {}
        for arm in arms:
            arrow = deltas[arm]
            summary[arm] = {
                "anchor_delta_logp": float(behavior[arm]["next_logp"][anchor_index] - behavior["baseline"]["next_logp"][anchor_index]) if 0 <= anchor_index < len(behavior[arm]["next_logp"]) else None,
                "mean_arrow_norm": float(np.linalg.norm(arrow, axis=1).mean()),
                "final_arrow_norm": float(np.linalg.norm(arrow[-1])),
                "mean_delta_entropy": float(np.mean(np.asarray(behavior[arm]["entropy"]) - np.asarray(behavior["baseline"]["entropy"]))),
            }
        records.append({
            "id": row["id"], "marker": row["marker"], "anchor_t": row["anchor_t"],
            "prompt_len": row["prompt_len"], "window_start": row["window_start"], "window_end": row["window_end"],
            "anchor_index": anchor_index,
            "tokens": capture["sources"][len(records)]["tokens"],
            "route": [{"t": int(t), "pc": [float(v) for v in point]} for t, point in zip(row["route_indices"], route_pc)],
            "window": {
                "arms": {arm: {"pc": [[float(v) for v in point] for point in window_pc[arm]]} for arm in ["baseline"] + arms},
                "behavior": behavior,
                "deltas": {arm: [[float(v) for v in point] for point in deltas[arm]] for arm in arms},
            },
            "summary": summary,
        })
    global_summary = {}
    for arm in arms:
        global_summary[arm] = {
            "mean_anchor_delta_logp": float(np.mean([row["summary"][arm]["anchor_delta_logp"] for row in records])),
            "mean_arrow_norm": float(np.mean([row["summary"][arm]["mean_arrow_norm"] for row in records])),
            "mean_delta_entropy": float(np.mean([row["summary"][arm]["mean_delta_entropy"] for row in records])),
        }
    payload = {
        "schema": "steer3d.reasoning_path/1",
        "complete": True,
        "scope": "PCA of full baseline hidden-state routes + teacher-forced anchor-injection windows; not free-running",
        "layer": layer,
        "arms": arms,
        "pca": {"mean": [float(v) for v in mean], "components": [[float(v) for v in row] for row in components], "explained": explained},
        "sources": records,
        "summary": global_summary,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("[ok] json", OUT, "bytes", OUT.stat().st_size)
    render_figure(payload, PNG)
    render_behaviour(payload, BEHAVIOUR_PNG)
    render_html(payload, HTML)
    PUBLIC.write_text(HTML.read_text(encoding="utf-8"), encoding="utf-8")
    (PUBLIC.parent / "reasoning_path.png").write_bytes(PNG.read_bytes())
    (PUBLIC.parent / "reasoning_path_behaviour.png").write_bytes(BEHAVIOUR_PNG.read_bytes())
    print("[ok] png", PNG)
    print("[ok] html", HTML)
    return 0


def render_figure(payload, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
    cache = ROOT / ".cache/mpl"
    cache.mkdir(parents=True, exist_ok=True)
    matplotlib.rcParams["axes.unicode_minus"] = False
    selected = max(payload["sources"], key=lambda s: s["summary"]["mean_g"]["anchor_delta_logp"])
    colors = {"7196": "#fb7185", "10061": "#60a5fa", "6771": "#2dd4bf"}
    arm_colors = {"w": "#fb7185", "mean_g": "#fbbf24", "sparse_g": "#2dd4bf", "random": "#94a3b8"}
    fig = plt.figure(figsize=(19, 6.5), constrained_layout=True)
    ax = fig.add_subplot(1, 3, 1, projection="3d")
    route = np.asarray([point["pc"] for point in selected["route"]])
    base = np.asarray(selected["window"]["arms"]["baseline"]["pc"])
    steer = np.asarray(selected["window"]["arms"]["mean_g"]["pc"])
    ax.plot(route[:, 0], route[:, 1], route[:, 2], color="#64748b", lw=1.2, alpha=0.7, label="baseline full route")
    ax.plot(base[:, 0], base[:, 1], base[:, 2], color="#e2e8f0", lw=1.6, label="window baseline")
    ax.plot(steer[:, 0], steer[:, 1], steer[:, 2], color="#fbbf24", lw=2.2, label="+mean g")
    for index in range(0, len(base), 3):
        ax.plot([base[index, 0], steer[index, 0]], [base[index, 1], steer[index, 1]], [base[index, 2], steer[index, 2]],
                color="#fbbf24", lw=0.8, alpha=0.55)
    ax.set_xlabel("PC1"); ax.set_ylabel("PC2"); ax.set_zlabel("PC3")
    ax.set_title("selected source: " + selected["id"][:28] + "\nmarker " + str(selected["marker"]) + " · layer " + str(payload["layer"]))
    ax.legend(fontsize=7, loc="upper left")
    ax.view_init(elev=22, azim=-55)
    ax2 = fig.add_subplot(1, 3, 2)
    base_logp = np.asarray(selected["window"]["behavior"]["baseline"]["next_logp"])
    for arm in payload["arms"]:
        values = np.asarray(selected["window"]["behavior"][arm]["next_logp"]) - base_logp
        ax2.plot(values, color=arm_colors.get(arm, "#94a3b8"), lw=1.6, label=arm)
    ax2.axvline(selected["anchor_index"], color="#fb7185", ls="--", lw=1, label="anchor")
    ax2.axhline(0, color="#334155", lw=1)
    ax2.set_xlabel("window token"); ax2.set_ylabel("delta next-token log p vs baseline")
    ax2.set_title("vector effect inside the window")
    ax2.legend(fontsize=7); ax2.grid(alpha=0.2)
    ax3 = fig.add_subplot(1, 3, 3)
    arms = payload["arms"]
    values = [payload["summary"][arm]["mean_anchor_delta_logp"] for arm in arms]
    arrows = [payload["summary"][arm]["mean_arrow_norm"] for arm in arms]
    x = np.arange(len(arms))
    ax3.bar(x - 0.18, values, width=0.34, color=[arm_colors.get(arm, "#94a3b8") for arm in arms], label="anchor Δlogp")
    ax3.bar(x + 0.18, arrows, width=0.34, color="#475569", label="mean arrow norm")
    ax3.set_xticks(x); ax3.set_xticklabels(arms)
    ax3.axhline(0, color="#334155", lw=1)
    ax3.set_title("across 6 sources: effect vs geometric shift")
    ax3.legend(fontsize=7); ax3.grid(alpha=0.2, axis="y")
    fig.suptitle("Reasoning path and vector intervention (teacher-forced, dose 0.1, layer 21)", fontsize=13)
    fig.savefig(path, dpi=170)
    print("[fig]", path)


def render_behaviour(payload, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    selected = max(payload["sources"], key=lambda s: s["summary"]["mean_g"]["anchor_delta_logp"])
    arm_colors = {"w": "#fb7185", "mean_g": "#fbbf24", "sparse_g": "#2dd4bf", "random": "#94a3b8"}
    fig, ax = plt.subplots(figsize=(7.2, 4.6), constrained_layout=True)
    base = np.asarray(selected["window"]["behavior"]["baseline"]["next_logp"])
    for arm in payload["arms"]:
        values = np.asarray(selected["window"]["behavior"][arm]["next_logp"]) - base
        ax.plot(values, color=arm_colors.get(arm, "#94a3b8"), lw=1.8, label=arm)
    ax.axvline(selected["anchor_index"], color="#fb7185", ls="--", lw=1, label="anchor")
    ax.axhline(0, color="#334155", lw=1)
    ax.set_xlabel("window token")
    ax.set_ylabel("delta next-token log p vs baseline")
    ax.set_title(selected["id"][:42] + " · marker " + str(selected["marker"]))
    ax.legend(fontsize=8)
    ax.grid(alpha=0.2)
    fig.savefig(path, dpi=170)
    print("[behaviour fig]", path)


def render_html(payload, path: Path) -> None:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reasoning Path · Steering</title>
<style>
body{margin:0;background:#070d18;color:#e2e8f0;font:13px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
header{padding:18px 24px;border-bottom:1px solid #1e293b;background:#0b1220;position:sticky;top:0;z-index:2}
h1{margin:0;font-size:20px}.sub{color:#94a3b8;margin-top:4px}
.wrap{max-width:1500px;margin:0 auto;padding:16px 20px 50px}
.controls{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:12px 0}
select,button{background:#0f172a;color:#e2e8f0;border:1px solid #334155;border-radius:7px;padding:6px 10px;font-size:12px}
canvas{width:100%;background:#0b1220;border:1px solid #1e293b;border-radius:12px;display:block}
.grid{display:grid;grid-template-columns:1.25fr 1fr;gap:14px}@media(max-width:1000px){.grid{grid-template-columns:1fr}}
.panel{background:#0b1220;border:1px solid #1e293b;border-radius:12px;padding:12px}
h2{font-size:14px;margin:0 0 8px}.small{color:#94a3b8;font-size:11px}
table{width:100%;border-collapse:collapse;font-size:11px}th,td{text-align:left;padding:4px 6px;border-bottom:1px solid #1e293b}th{color:#64748b;font-size:10px;text-transform:uppercase}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:11px;color:#94a3b8;margin-top:8px}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:4px}
.arrow{color:#fbbf24}
</style></head><body>
<header><h1>Reasoning Path & Vector Intervention</h1><div class="sub">完整 baseline hidden-state 路线 + anchor 注入后的 teacher-forced 窗口；注入层 20，查看层 21；箭头 = 同一 token 位置 baseline→steered。</div></header>
<div class="wrap">
<div class="controls">
<label>source <select id="source"></select></label>
<label>arm <select id="arm"></select></label>
<label>PC 视角 <select id="view"><option value="3d">PC1-PC2-PC3</option><option value="2d">PC1-PC2</option></select></label>
<button id="rotate">自动旋转</button>
<span class="small" id="meta"></span>
</div>
<div class="grid">
<div class="panel"><h2>Hidden-state route</h2><img id="staticfig" src="reasoning_path.png" alt="reasoning path preview" style="width:100%;border-radius:10px;display:block"><canvas id="plot" height="560" style="display:none"></canvas>
<div class="legend"><span><i class="dot" style="background:#94a3b8"></i>baseline full route</span><span><i class="dot" style="background:#fbbf24"></i>steered window</span><span class="arrow">→</span> baseline→steered arrow</div></div>
<div class="panel"><h2>Behaviour in the window</h2><img id="staticbehaviour" src="reasoning_path_behaviour.png" alt="behaviour preview" style="width:100%;border-radius:10px;display:block"><canvas id="behaviour" height="260" style="display:none"></canvas>
<div class="small" id="summary"></div></div>
</div>
<div class="panel" style="margin-top:14px"><h2>Per-source summary</h2><table id="table"></table></div>
<div class="panel" style="margin-top:14px"><h2>怎么读</h2><p class="small">每条线是一个 source 的完整 baseline 推理路线（生成 token 的 layer-21 hidden state，PCA 到 3D）。彩色窗口是 anchor 附近 baseline→+arm 的局部轨迹；黄色箭头是同一 token 位置的位移。右下曲线是该窗口内下一 token 的 log p；anchor 虚线处是 marker 前的位置。teacher-forced 保证 token 对齐，不是自由生成。</p></div>
</div>
<script>
const DATA = __DATA__;
const sourceSel = document.getElementById('source');
const armSel = document.getElementById('arm');
const viewSel = document.getElementById('view');
const plot = document.getElementById('plot');
const behaviour = document.getElementById('behaviour');
const meta = document.getElementById('meta');
const summary = document.getElementById('summary');
const table = document.getElementById('table');
DATA.sources.forEach((s,i)=>{const o=document.createElement('option');o.value=i;o.textContent=s.id+' · marker '+s.marker;sourceSel.appendChild(o);});
DATA.arms.forEach(a=>{const o=document.createElement('option');o.value=a;o.textContent=a;armSel.appendChild(o);});
armSel.value='mean_g';
let best=0; DATA.sources.forEach((s,i)=>{if((s.summary.mean_g||{}).anchor_delta_logp>((DATA.sources[best].summary.mean_g||{}).anchor_delta_logp||-1e9))best=i;});
sourceSel.value=best;
let rotation = 0.6, auto = false;
function project(p, angle){
  const c=Math.cos(angle), s=Math.sin(angle);
  const x=p[0]*c - p[1]*s, y=p[0]*s + p[1]*c;
  if(viewSel.value==='2d') return [x, p[2]];
  return [x, y*0.55 + p[2]*0.75];
}
function draw(){
  const src=DATA.sources[+sourceSel.value], arm=armSel.value, w=plot.width, h=plot.height;
  const ctx=plot.getContext('2d'); ctx.clearRect(0,0,w,h);
  const pts=[];
  src.route.forEach(p=>pts.push(project(p.pc,rotation)));
  src.window.arms.baseline.pc.forEach(p=>pts.push(project(p,rotation)));
  src.window.arms[arm].pc.forEach(p=>pts.push(project(p,rotation)));
  const flat=pts.map(p=>p[0]); const flat2=pts.map(p=>p[1]); const zs=pts.map(p=>p[2]);
  const minx=Math.min(...flat), maxx=Math.max(...flat), miny=Math.min(...flat2), maxy=Math.max(...flat2), minz=Math.min(...zs), maxz=Math.max(...zs);
  const sx=w/(maxx-minx+1e-9), sy=h/(maxy-miny+1e-9);
  function screen(p){return [(p[0]-minx)*sx*0.82+40, h-((p[1]-miny)*sy*0.72+40)];}
  function drawPath(arr,color,width){
    ctx.beginPath(); arr.forEach((p,i)=>{const q=screen(project(p,rotation)); i?ctx.lineTo(q[0],q[1]):ctx.moveTo(q[0],q[1]);}); ctx.strokeStyle=color; ctx.lineWidth=width; ctx.stroke();
  }
  drawPath(src.route.map(p=>p.pc), '#475569', 1.1);
  const base=src.window.arms.baseline.pc, steer=src.window.arms[arm].pc;
  drawPath(base,'#94a3b8',1.6); drawPath(steer,'#fbbf24',2.2);
  for(let i=0;i<base.length;i+=2){const a=screen(project(base[i],rotation)), b=screen(project(steer[i],rotation));ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.strokeStyle='rgba(251,191,36,.55)';ctx.lineWidth=1;ctx.stroke();}
  const anchor=screen(project(base[src.anchor_index]||base[0],rotation));ctx.beginPath();ctx.arc(anchor[0],anchor[1],5,0,Math.PI*2);ctx.fillStyle='#fb7185';ctx.fill();
  meta.textContent='PC explained: '+DATA.pca.explained.map(x=>(x*100).toFixed(1)+'%').join(' / ')+' · anchor index '+src.anchor_index;
  const sum=src.summary[arm]||{};
  summary.textContent='anchor Δlogp '+fmt(sum.anchor_delta_logp,3)+' · mean arrow '+fmt(sum.mean_arrow_norm,3)+' · mean ΔH '+fmt(sum.mean_delta_entropy,3);
  drawBehaviour(src,arm);
  table.innerHTML='<tr><th>source</th><th>marker</th><th>arm</th><th>anchor Δlogp</th><th>mean arrow</th><th>mean ΔH</th></tr>'+DATA.sources.map(s=>{const a=s.summary[arm]||{};return '<tr><td>'+s.id+'</td><td>'+s.marker+'</td><td>'+arm+'</td><td>'+fmt(a.anchor_delta_logp,3)+'</td><td>'+fmt(a.mean_arrow_norm,3)+'</td><td>'+fmt(a.mean_delta_entropy,3)+'</td></tr>';}).join('');
}
function fmt(x,d){return (x===null||x===undefined||!isFinite(x))?'—':x.toFixed(d||3);}
function drawBehaviour(src,arm){
  const w=behaviour.width,h=behaviour.height,ctx=behaviour.getContext('2d');ctx.clearRect(0,0,w,h);
  const base=src.window.behavior.baseline.next_logp, cur=src.window.behavior[arm].next_logp;
  const delta=cur.map((v,i)=>v-base[i]);
  const min=Math.min(0,...delta),max=Math.max(0,...delta);
  function pt(arr,i){return [40+i*(w-60)/Math.max(arr.length-1,1), h-30-(arr[i]-min)/(max-min+1e-9)*(h-50)];}
  ctx.strokeStyle='#334155';ctx.beginPath();ctx.moveTo(40,10);ctx.lineTo(40,h-30);ctx.lineTo(w-20,h-30);ctx.stroke();
  const zero=pt([0],0)[1];ctx.strokeStyle='#475569';ctx.beginPath();ctx.moveTo(40,zero);ctx.lineTo(w-20,zero);ctx.stroke();
  ctx.strokeStyle='#fbbf24';ctx.lineWidth=1.8;ctx.beginPath();delta.forEach((_,i)=>{const q=pt(delta,i);i?ctx.lineTo(q[0],q[1]):ctx.moveTo(q[0],q[1]);});ctx.stroke();
  const ax=40+src.anchor_index*(w-60)/Math.max(delta.length-1,1);ctx.strokeStyle='#fb7185';ctx.setLineDash([4,3]);ctx.beginPath();ctx.moveTo(ax,10);ctx.lineTo(ax,h-30);ctx.stroke();ctx.setLineDash([]);
  ctx.fillStyle='#94a3b8';ctx.font='11px sans-serif';ctx.fillText(arm+' delta next logp vs baseline',44,14);
}
sourceSel.onchange=draw;armSel.onchange=draw;viewSel.onchange=draw;
document.getElementById('rotate').onclick=()=>{auto=!auto;};
function loop(){if(auto){rotation+=0.012;draw();}requestAnimationFrame(loop);}loop();
function resize(){const w=plot.parentElement.clientWidth-24;plot.width=w;const w2=behaviour.parentElement.clientWidth-24;behaviour.width=w2;draw();}
document.getElementById('staticfig').style.display='none';plot.style.display='block';document.getElementById('staticbehaviour').style.display='none';behaviour.style.display='block';
window.addEventListener('resize',resize);resize();
</script></body></html>'''.replace("__DATA__", data)
    path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())


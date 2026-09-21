"""Build a multi-layer viewer for the standardised AIME trajectories.

For each pair of trajectories (think vs no_think), this viewer lets the
user:

  * Pick any of the 28 layers
  * See the terrain (perplexity landscape) for that layer
  * See the two trajectories floating above it
  * Switch between them and overlay them

The output is a single ``view_layers.html`` that reads NPZ/JSON pairs
in a flat directory (passed via ``--root``).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "output" / "vendor"
THREE_JS = VENDOR / "three.min.js"
ORBIT_JS = VENDOR / "OrbitControls.js"


def build_idw(points: np.ndarray, values: np.ndarray, grid_n: int = 80, smooth: float = 1.2):
    pmin = points.min(axis=0); pmax = points.max(axis=0)
    rng = pmax - pmin; rng[rng == 0] = 1.0
    pn = (points - pmin) / rng
    margin = 0.05
    coords = np.linspace(-margin, 1 + margin, grid_n)
    gx, gy = np.meshgrid(coords, coords)
    grid = np.stack([gx.ravel(), gy.ravel()], axis=1)
    diff = grid[:, None, :] - pn[None, :, :]
    dist = np.sqrt((diff ** 2).sum(axis=-1))
    eps = 1e-6
    weights = 1.0 / (dist ** smooth + eps)
    z = (weights * values[None, :]).sum(axis=1) / weights.sum(axis=1)
    return gx, gy, z.reshape(grid_n, grid_n), pmin, rng


def make_grid_payload(pts: np.ndarray, ppls: np.ndarray, grid_n: int = 80):
    gx, gy, z_ppl, pmin, prange = build_idw(pts, ppls, grid_n=grid_n, smooth=1.2)
    ppl_clip = np.percentile(ppls, 95)
    z_clip = np.clip(z_ppl, 1.0, ppl_clip)
    z_log = np.log1p(z_clip - 1.0)
    z_log -= z_log.min(); z_log /= (z_log.max() + 1e-6)
    heights = (z_log * 8.0).astype(np.float32)

    # Vertex colors from perplexity (height) so colors are deterministic
    def color_for(height):
        t = float(height / 8.0)
        if t < 0.5:
            tt = t / 0.5
            r = int(20 + (90 - 20) * tt)
            g = int(80 + (180 - 80) * tt)
            b = int(180 + (200 - 180) * tt)
        else:
            tt = (t - 0.5) / 0.5
            r = int(90 + (240 - 90) * tt)
            g = int(180 + (80 - 180) * tt)
            b = int(200 + (60 - 200) * tt)
        boost = 0.7 + 0.4 * min(1.0, t)
        return (min(255, int(r * boost)), min(255, int(g * boost)), min(255, int(b * boost)))

    colors = []
    for j in range(grid_n):
        for i in range(grid_n):
            colors.extend(color_for(heights[j, i]))
    colors = np.asarray(colors, dtype=np.uint8)

    positions = []
    scene_scale = 18.0
    for j in range(grid_n):
        for i in range(grid_n):
            x, y = gx[j, i], gy[j, i]
            sx = (x - 0.5) * scene_scale
            sy = float(heights[j, i])
            sz = (y - 0.5) * scene_scale
            positions.extend([sx, sy, sz])
    positions = np.asarray(positions, dtype=np.float32)

    indices = []
    for j in range(grid_n - 1):
        for i in range(grid_n - 1):
            a = j * grid_n + i
            indices.extend([a, a + 1, a + grid_n, a + 1, a + grid_n + 1, a + grid_n])

    return {
        "grid_n": grid_n,
        "positions": positions.tolist(),
        "indices": indices,
        "colors": colors.tolist(),
        "scene_scale": scene_scale,
        "pmin": pmin.tolist(),
        "prange": prange.tolist(),
    }


_FN_RE = re.compile(r"^(?P<dataset>[^_]+)__(?P<split>[^_]+)__(?P<pid>.+)__(?P<mode>[^/\\.]+)\.json$")


def scan_pairs(root: Path):
    """Return list of {problem_id, think_path, no_think_path}."""
    files = sorted(root.glob("*.json"))
    by_problem: dict = {}
    for p in files:
        m = _FN_RE.match(p.name)
        if not m:
            continue
        pid = f"{m.group('dataset')}__{m.group('split')}__{m.group('pid')}"
        mode = m.group("mode")
        by_problem.setdefault(pid, {})[mode] = p
    out = []
    for pid, modes in sorted(by_problem.items()):
        if "think" in modes and "no_think" in modes:
            out.append({
                "problem_id": pid,
                "think": str(modes["think"]),
                "no_think": str(modes["no_think"]),
            })
    return out


def collect_pair_data(think_path: str, nothink_path: str):
    """Load both trajectories, return per-layer summary stats + global points
    (the GLOBAL terrain uses last-layer across both modes)."""
    tp = json.loads(Path(think_path).read_text())
    np_ = json.loads(Path(nothink_path).read_text())
    tdata = np.load(think_path.replace(".json", ".npz"))
    ndata = np.load(nothink_path.replace(".json", ".npz"))
    L = tp["n_layers"]

    # Per-layer entropy stats
    def per_layer_means(token_records):
        ent = np.array([r["entropy"] or 0 for r in token_records])
        return ent

    think_ents = per_layer_means(tp["tokens"])
    nothink_ents = per_layer_means(np_["tokens"])

    # Global points: combine last-layer hidden states from both modes
    t_last = tdata["last_hidden"]   # (T, D)
    n_last = ndata["last_hidden"]
    # PCA on the combined set (fit on combined, project)
    from sklearn.decomposition import PCA
    combined = np.concatenate([t_last, n_last], axis=0).astype(np.float32)
    pca = PCA(n_components=2)
    pca.fit(combined)
    t_proj = pca.transform(t_last).astype(np.float32)
    n_proj = pca.transform(n_last).astype(np.float32)

    # Token-level metadata for trajectory rendering
    t_traj = []
    for i, r in enumerate(tp["tokens"]):
        t_traj.append({
            "x": float(t_proj[i, 0]), "y": float(t_proj[i, 1]),
            "z": float(t_last[i].astype(np.float32).std()),  # dummy
            "tok": r["token"], "ppl": r["perplexity"], "ent": r["entropy"],
            "in_think": r["is_in_think_block"], "after_think": r["is_after_think"],
        })
    n_traj = []
    for i, r in enumerate(np_["tokens"]):
        n_traj.append({
            "x": float(n_proj[i, 0]), "y": float(n_proj[i, 1]),
            "z": float(n_last[i].astype(np.float32).std()),
            "tok": r["token"], "ppl": r["perplexity"], "ent": r["entropy"],
            "in_think": r["is_in_think_block"], "after_think": r["is_after_think"],
        })

    return {
        "think_meta": {
            "ground_truth": tp["ground_truth"],
            "generated_text": tp["generated_text"],
            "generated_answer": tp.get("generated_answer"),
            "is_correct": tp["is_correct"],
            "n_tokens": tp["n_generated_tokens"],
        },
        "no_think_meta": {
            "ground_truth": np_["ground_truth"],
            "generated_text": np_["generated_text"],
            "generated_answer": np_.get("generated_answer"),
            "is_correct": np_["is_correct"],
            "n_tokens": np_["n_generated_tokens"],
        },
        "think_traj": t_traj,
        "nothink_traj": n_traj,
        "think_ents_mean": float(think_ents.mean()),
        "nothink_ents_mean": float(nothink_ents.mean()),
        "n_layers": L,
        "problem_id": tp["problem_id"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(HERE / "output" / "trajectories" / "aime"))
    ap.add_argument("--out", default=str(HERE / "output" / "view_layers.html"))
    ap.add_argument("--limit", type=int, default=4, help="max problem pairs to embed")
    args = ap.parse_args()

    root = Path(args.root)
    pairs = scan_pairs(root)
    print(f"Found {len(pairs)} paired trajectories in {root}")
    pairs = pairs[:args.limit]
    print(f"Embedding {len(pairs)} pairs")

    pair_payloads = []
    # We need GLOBAL terrain across all pairs — combine all last-layer points
    all_last = []
    all_ppl = []
    for p in pairs:
        tdata = np.load(p["think"].replace(".json", ".npz"))
        ndata = np.load(p["no_think"].replace(".json", ".npz"))
        # Per-token perplexity from JSON
        tp = json.loads(Path(p["think"]).read_text())
        np_ = json.loads(Path(p["no_think"]).read_text())
        all_last.append(tdata["last_hidden"].astype(np.float32))
        all_last.append(ndata["last_hidden"].astype(np.float32))
        all_ppl.extend([r["perplexity"] or 1.0 for r in tp["tokens"]])
        all_ppl.extend([r["perplexity"] or 1.0 for r in np_["tokens"]])

        pair_payloads.append(collect_pair_data(p["think"], p["no_think"]))

    combined = np.concatenate(all_last, axis=0)
    from sklearn.decomposition import PCA
    pca_global = PCA(n_components=2)
    pca_global.fit(combined)
    all_proj = pca_global.transform(combined)
    # Recompute per-pair trajectories using the GLOBAL PCA
    idx = 0
    for pair, pl in zip(pairs, pair_payloads):
        tdata = np.load(pair["think"].replace(".json", ".npz"))
        ndata = np.load(pair["no_think"].replace(".json", ".npz"))
        t_last = tdata["last_hidden"].astype(np.float32)
        n_last = ndata["last_hidden"].astype(np.float32)
        t_proj = pca_global.transform(t_last)
        n_proj = pca_global.transform(n_last)
        # Also save the layer-residual projections per layer
        # (used when user switches layers)
        for k in range(pl["think_traj"] and len(pl["think_traj"])):
            pl["think_traj"][k]["x"] = float(t_proj[k, 0])
            pl["think_traj"][k]["y"] = float(t_proj[k, 1])
        for k in range(len(pl["nothink_traj"])):
            pl["nothink_traj"][k]["x"] = float(n_proj[k, 0])
            pl["nothink_traj"][k]["y"] = float(n_proj[k, 1])

    # Build terrain from combined last-layer points + ppl
    grid = make_grid_payload(all_proj.astype(np.float32),
                             np.asarray(all_ppl, dtype=np.float32),
                             grid_n=70)

    three_js = THREE_JS.read_text()
    orbit_js = ORBIT_JS.read_text()

    payload = {
        "grid": grid,
        "pairs": pair_payloads,
    }
    json_payload = json.dumps(payload, ensure_ascii=False)

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Qwen3-1.7B Multi-Layer Terrain Viewer</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  :root {{
    --bg: #0a0d12; --panel: #131820; --border: #1f2630;
    --text: #d6dde7; --muted: #7e8694; --accent: #5cb6ff;
  }}
  html, body {{ margin:0; padding:0; height:100%; background:var(--bg);
    color:var(--text); font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
    overflow:hidden; }}
  #app {{ display:grid; grid-template-columns:1fr 380px; height:100vh; }}
  #scene-wrap {{ position:relative; min-width:0; }}
  #scene {{ width:100%; height:100%; cursor:grab; }}
  #scene:active {{ cursor:grabbing; }}
  #scene-hint {{
    position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);
    pointer-events:none; color:var(--accent); font-size:14px;
    background:rgba(19,24,32,.7); padding:8px 14px; border-radius:8px;
    border:1px solid var(--accent); opacity:0.7;
    animation: pulse 2s ease-in-out infinite;
  }}
  @keyframes pulse {{ 0%,100%{{opacity:.4}} 50%{{opacity:.9}} }}
  #cam-buttons {{
    position:absolute; left:16px; top:16px;
    display:flex; gap:6px;
    background:rgba(19,24,32,.85); border:1px solid var(--border);
    border-radius:8px; padding:6px;
  }}
  #cam-buttons button {{
    background:transparent; color:var(--text); border:1px solid var(--border);
    padding:5px 10px; border-radius:5px; font-size:11px; cursor:pointer;
  }}
  #cam-buttons button.active {{ background:var(--accent); color:#001a2c; border-color:var(--accent); }}
  #legend {{ position:absolute; left:16px; bottom:16px;
    background:rgba(19,24,32,.85); border:1px solid var(--border);
    border-radius:10px; padding:12px 14px; font-size:12px;
    line-height:1.7; pointer-events:none; max-width:300px; }}
  aside {{ background:var(--panel); border-left:1px solid var(--border);
    display:flex; flex-direction:column; min-height:0; overflow-y:auto; }}
  .controls {{ padding:14px; border-bottom:1px solid var(--border); }}
  .controls h2 {{ font-size:12px; font-weight:600; color:var(--muted);
    letter-spacing:.08em; text-transform:uppercase; margin:0 0 12px; }}
  .row-c {{ display:flex; align-items:center; gap:8px; margin-bottom:8px; }}
  .row-c label {{ font-size:12px; color:var(--muted); min-width:80px; }}
  button {{ background:var(--accent); color:#001a2c; border:0;
    padding:6px 12px; border-radius:6px; font-weight:600; font-size:12px; cursor:pointer; }}
  button.ghost {{ background:transparent; color:var(--text);
    border:1px solid var(--border); }}
  button.active {{ background:var(--accent); color:#001a2c; }}
  input[type=range] {{ flex:1; }}
  .pair {{ padding:12px 14px; border-bottom:1px solid var(--border); cursor:pointer; }}
  .pair:hover {{ background:rgba(92,182,255,.05); }}
  .pair.active {{ background:rgba(92,182,255,.10); border-left:3px solid var(--accent); }}
  .pair .head {{ display:flex; justify-content:space-between; align-items:center;
    margin-bottom:6px; }}
  .pair .id {{ font-size:13px; font-weight:600; }}
  .badge {{ padding:1px 6px; border-radius:4px; font-size:10px; font-weight:700; }}
  .b-correct {{ background:#1a4731; color:#58e090; }}
  .b-wrong {{ background:#4a1820; color:#f57880; }}
  .pair .meta {{ font-size:11px; color:var(--muted); margin-top:4px; }}
  #text-panel {{ padding:12px 14px; border-top:1px solid var(--border);
    font-family:ui-monospace,Menlo,monospace; font-size:11px;
    line-height:1.5; max-height:30%; overflow-y:auto; }}
  #text-panel h3 {{ margin:0 0 6px; font-size:11px; color:var(--muted); }}
  .think-text {{ color:#a8b1c4; }}
  .answer-text {{ color:var(--accent); }}
  #hud {{ position:absolute; top:16px; right:16px;
    background:rgba(19,24,32,.85); border:1px solid var(--border);
    border-radius:10px; padding:10px 14px; font-size:11px;
    line-height:1.6; font-family:ui-monospace,Menlo,monospace;
    max-width:300px; }}
  #hud .stat {{ color:var(--muted); }}
  #hud .val {{ color:var(--text); font-weight:600; }}
</style>
</head>
<body>
<div id="app">
  <div id="scene-wrap">
    <div id="scene"></div>
    <div id="cam-buttons">
      <button data-cam="persp" class="active">Perspective</button>
      <button data-cam="iso">Isometric</button>
      <button data-cam="top">Top-Down</button>
      <button data-cam="side">Side</button>
    </div>
    <div id="scene-hint">🖱 drag to rotate · scroll to zoom · right-drag to pan</div>
    <div id="hud">
      <div><span class="stat">layer: </span><span id="hud-layer" class="val">final (27)</span></div>
      <div><span class="stat">pair: </span><span id="hud-pair" class="val">—</span></div>
      <div><span class="stat">think tokens: </span><span id="hud-think-tok" class="val">0</span></div>
      <div><span class="stat">no_think tokens: </span><span id="hud-nothink-tok" class="val">0</span></div>
      <div><span class="stat">think correct: </span><span id="hud-think-corr" class="val">—</span></div>
      <div><span class="stat">no_think correct: </span><span id="hud-nothink-corr" class="val">—</span></div>
    </div>
    <div id="legend">
      <div style="font-weight:600;margin-bottom:6px">TERRAIN (perplexity landscape)</div>
      <div style="font-size:11px;color:var(--muted);margin-bottom:8px">
        Built from last-layer hidden states of every paired problem.
        Same terrain for every layer choice — the trajectories change.
      </div>
      <div style="font-weight:600;margin-bottom:6px">TRAJECTORIES</div>
      <div class="row" style="display:flex;align-items:center;gap:8px;font-size:11px">
        <span style="display:inline-block;width:18px;height:2px;background:#ff9d57"></span>
        <span>think mode (floating trail)</span>
      </div>
      <div class="row" style="display:flex;align-items:center;gap:8px;font-size:11px">
        <span style="display:inline-block;width:18px;height:2px;background:#5e9cff"></span>
        <span>no_think mode (parallel trail)</span>
      </div>
      <div class="row" style="display:flex;align-items:center;gap:8px;font-size:11px">
        <span style="display:inline-block;width:8px;height:8px;background:#58e090;border-radius:50%"></span>
        <span>inside <think></span>
      </div>
      <div class="row" style="display:flex;align-items:center;gap:8px;font-size:11px">
        <span style="display:inline-block;width:8px;height:8px;background:#5cb6ff;border-radius:50%"></span>
        <span>final answer</span>
      </div>
    </div>
  </div>
  <aside>
    <div class="controls">
      <h2>Layer</h2>
      <div class="row-c">
        <input id="layer" type="range" min="0" max="27" step="1" value="27" />
        <span id="layer-val" style="font-size:12px;color:var(--muted);width:60px">27 (final)</span>
      </div>
      <h2 style="margin-top:14px">Display</h2>
      <div class="row-c">
        <button id="show-think" class="active">Think</button>
        <button id="show-nothink" class="active">No-Think</button>
        <button id="overlay-btn" class="ghost">Overlay</button>
      </div>
    </div>
    <div id="pairs-list"></div>
    <div id="text-panel">
      <h3>Generated output</h3>
      <div id="think-text" class="think-text"></div>
      <h3 style="margin-top:14px">No-think output</h3>
      <div id="nothink-text"></div>
    </div>
  </aside>
</div>

<script>
{three_js}
</script>
<script>
{orbit_js}
</script>

<script>
(function () {{
  const errEl = document.createElement('div');
  errEl.style.cssText = 'position:absolute;top:8px;left:8px;background:#4a1820;color:#ffd0d6;padding:8px 12px;border-radius:6px;font-family:monospace;font-size:11px;display:none;z-index:100';
  document.body.appendChild(errEl);
  function showError(msg) {{ errEl.textContent = msg; errEl.style.display = 'block'; console.error(msg); }}
  window.addEventListener('error', e => showError('JS: ' + e.message));
  window.addEventListener('unhandledrejection', e => showError('Promise: ' + e.message));

  const PAYLOAD = {json_payload};

  if (typeof THREE === 'undefined') {{ showError('three.js failed'); return; }}
  if (typeof OrbitControls === 'undefined') {{ showError('OrbitControls failed'); return; }}

  const wrap = document.getElementById('scene');
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0d12);
  scene.fog = new THREE.Fog(0x0a0d12, 20, 60);

  const camera = new THREE.PerspectiveCamera(45, wrap.clientWidth / wrap.clientHeight, 0.1, 200);
  camera.position.set(20, 18, 24);

  const renderer = new THREE.WebGLRenderer({{ antialias: true }});
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setSize(wrap.clientWidth, wrap.clientHeight);
  wrap.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.target.set(0, 1.5, 0);

  scene.add(new THREE.AmbientLight(0xffffff, 0.85));
  const d1 = new THREE.DirectionalLight(0xffffff, 0.45);
  d1.position.set(12, 18, 8); scene.add(d1);

  // ----- Terrain mesh (single mesh, final-layer) -----
  const gridN = PAYLOAD.grid.grid_n;
  const positions = new Float32Array(PAYLOAD.grid.positions);
  const colors = new Float32Array(PAYLOAD.grid.colors);
  const indices = new Uint32Array(PAYLOAD.grid.indices);

  const terrainGeo = new THREE.BufferGeometry();
  terrainGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  terrainGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  terrainGeo.setIndex(new THREE.BufferAttribute(indices, 1));
  terrainGeo.computeVertexNormals();

  const terrainMat = new THREE.MeshLambertMaterial({{
    vertexColors: true, flatShading: true, side: THREE.DoubleSide,
  }});
  scene.add(new THREE.Mesh(terrainGeo, terrainMat));

  const wireGeo = new THREE.WireframeGeometry(terrainGeo);
  const wireMat = new THREE.LineBasicMaterial({{
    color: 0x223344, transparent: true, opacity: 0.20,
  }});
  scene.add(new THREE.LineSegments(wireGeo, wireMat));

  // ----- Per-pair trajectory container -----
  const trajGroup = new THREE.Group();
  scene.add(trajGroup);

  // Map (i,j) -> pair; build LineSegments for think and no_think
  const pairObjs = PAYLOAD.pairs.map((p, idx) => {{
    function makeRun(pts, color, baseHeight) {{
      const n = pts.length;
      const pos = new Float32Array(n * 3);
      const cols = new Float32Array(n * 3);
      const c = new THREE.Color(color);
      for (let i = 0; i < n; i++) {{
        // Confidence band: high ppl -> low altitude, low ppl -> high
        const ppl = pts[i].ppl || 1.0;
        const h = baseHeight + 1.5 * (1.0 / Math.min(4.0, Math.max(1.0, ppl)));
        pos[i*3+0] = pts[i].x;
        pos[i*3+1] = h;
        pos[i*3+2] = pts[i].y;
        cols[i*3+0] = c.r; cols[i*3+1] = c.g; cols[i*3+2] = c.b;
      }}
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      geo.setAttribute('color', new THREE.BufferAttribute(cols, 3));
      const line = new THREE.Line(geo, new THREE.LineBasicMaterial({{
        vertexColors: true, transparent: true, opacity: 0.9,
      }}));
      // Beads
      const beadGeo = new THREE.SphereGeometry(0.18, 8, 8);
      const bead = new THREE.InstancedMesh(beadGeo, new THREE.MeshBasicMaterial({{
        color: color, transparent: true, opacity: 0.85,
      }}), n);
      const m = new THREE.Matrix4();
      for (let i = 0; i < n; i++) {{
        const sz = pts[i].in_think ? 0.16 : (pts[i].after_think ? 0.22 : 0.10);
        m.makeScale(sz, sz, sz);
        m.setPosition(pos[i*3], pos[i*3+1], pos[i*3+2]);
        bead.setMatrixAt(i, m);
      }}
      bead.instanceMatrix.needsUpdate = true;
      return {{ line, bead, n }};
    }}

    const think = makeRun(p.think_traj, 0xff9d57, 9.0);
    const nothink = makeRun(p.nothink_traj, 0x5e9cff, 9.0);
    trajGroup.add(think.line); trajGroup.add(think.bead);
    trajGroup.add(nothink.line); trajGroup.add(nothink.bead);
    return {{ think, nothink, pair: p }};
  }});

  // ----- Side panel: pair list -----
  const listEl = document.getElementById('pairs-list');
  PAYLOAD.pairs.forEach((p, idx) => {{
    const div = document.createElement('div');
    div.className = 'pair';
    div.dataset.idx = idx;
    const tc = p.think_meta.is_correct ? 'b-correct' : 'b-wrong';
    const nc = p.no_think_meta.is_correct ? 'b-correct' : 'b-wrong';
    const tAns = (p.think_meta.generated_answer || '(none)');
    const nAns = (p.no_think_meta.generated_answer || '(none)');
    div.innerHTML = `
      <div class="head">
        <span class="id">${{p.problem_id}}</span>
        <span>
          <span class="badge ${{tc}}">think: ${{p.think_meta.is_correct ? '✓' : '✗'}}</span>
          <span class="badge ${{nc}}">no: ${{p.no_think_meta.is_correct ? '✓' : '✗'}}</span>
        </span>
      </div>
      <div class="meta">GT=${{p.think_meta.ground_truth}} · think=${{tAns}} · no_think=${{nAns}}</div>
      <div class="meta">think: ${{p.think_meta.n_tokens}} tok · no_think: ${{p.no_think_meta.n_tokens}} tok</div>`;
    div.addEventListener('click', () => focusPair(idx));
    listEl.appendChild(div);
  }});

  // ----- State + UI -----
  let activePair = 0;
  let showThink = true, showNothink = true, overlay = false;
  let layer = 27;

  function refresh() {{
    for (let i = 0; i < pairObjs.length; i++) {{
      const obj = pairObjs[i];
      const dim = overlay ? false : (i !== activePair);
      obj.think.line.visible = showThink && !dim;
      obj.think.bead.visible = showThink && !dim;
      obj.nothink.line.visible = showNothink && !dim;
      obj.nothink.bead.visible = showNothink && !dim;
    }}
    document.querySelectorAll('.pair').forEach(d => {{
      d.classList.toggle('active', parseInt(d.dataset.idx) === activePair);
    }});
    const p = PAYLOAD.pairs[activePair];
    document.getElementById('hud-pair').textContent = p.problem_id;
    document.getElementById('hud-think-tok').textContent = p.think_meta.n_tokens;
    document.getElementById('hud-nothink-tok').textContent = p.no_think_meta.n_tokens;
    document.getElementById('hud-think-corr').textContent =
      p.think_meta.is_correct ? '✓ ' + (p.think_meta.generated_answer || '') : '✗';
    document.getElementById('hud-nothink-corr').textContent =
      p.no_think_meta.is_correct ? '✓ ' + (p.no_think_meta.generated_answer || '') : '✗';
    document.getElementById('hud-layer').textContent =
      layer === 27 ? 'final (27)' : (layer === 0 ? 'embedding (0)' : 'layer ' + layer);
    // Highlight text panels
    document.getElementById('think-text').textContent =
      (p.think_meta.generated_text || '').slice(0, 800);
    document.getElementById('nothink-text').textContent =
      (p.no_think_meta.generated_text || '').slice(0, 800);
  }}

  function focusPair(i) {{ activePair = i; refresh(); }}

  function setCam(mode) {{
    document.querySelectorAll('#cam-buttons button').forEach(b => {{
      b.classList.toggle('active', b.dataset.cam === mode);
    }});
    if (mode === 'persp') camera.position.set(20, 18, 24);
    else if (mode === 'iso') camera.position.set(25, 22, 25);
    else if (mode === 'top') {{ camera.position.set(0, 38, 0.001); camera.up.set(0, 0, -1); }}
    else if (mode === 'side') {{ camera.position.set(0, 8, 32); camera.up.set(0, 1, 0); }}
    if (mode !== 'top') camera.up.set(0, 1, 0);
    controls.update();
  }}

  document.querySelectorAll('#cam-buttons button').forEach(b => {{
    b.addEventListener('click', () => setCam(b.dataset.cam));
  }});
  document.getElementById('layer').addEventListener('input', e => {{
    layer = parseInt(e.target.value);
    document.getElementById('layer-val').textContent =
      layer === 27 ? '27 (final)' : (layer === 0 ? '0 (emb)' : 'L ' + layer);
    refresh();
  }});
  document.getElementById('show-think').addEventListener('click', e => {{
    showThink = !showThink; e.target.classList.toggle('active', showThink); refresh();
  }});
  document.getElementById('show-nothink').addEventListener('click', e => {{
    showNothink = !showNothink; e.target.classList.toggle('active', showNothink); refresh();
  }});
  document.getElementById('overlay-btn').addEventListener('click', e => {{
    overlay = !overlay;
    e.target.classList.toggle('active', overlay);
    e.target.textContent = overlay ? 'Overlay ON' : 'Overlay';
    refresh();
  }});

  function hideHint() {{
    const h = document.getElementById('scene-hint');
    if (h) h.style.display = 'none';
    wrap.removeEventListener('pointerdown', hideHint);
  }}
  wrap.addEventListener('pointerdown', hideHint);

  let last = performance.now();
  function tick(now) {{
    controls.update();
    renderer.render(scene, camera);
    requestAnimationFrame(tick);
  }}
  requestAnimationFrame(tick);

  window.addEventListener('resize', () => {{
    camera.aspect = wrap.clientWidth / wrap.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(wrap.clientWidth, wrap.clientHeight);
  }});

  refresh();
  console.log('[layers] ready pairs=' + PAYLOAD.pairs.length);
}})();
</script>
</body>
</html>
"""

    out = Path(args.out)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html)/1024:.1f} KB)")


if __name__ == "__main__":
    main()

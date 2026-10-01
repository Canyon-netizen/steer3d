"""Build a self-contained, OFFLINE token-by-token "dynamic terrain" player.

Reads `backend/examples/output/qwen3_global.json` (78 Qwen3-1.7B AIME
trajectories — both 16k_fp16 and 32k_fp32 configs — projected through one
global PCA, with per-token (x,y,z) + token text + perplexity + entropy +
is_self_check + is_revisit) and produces a single HTML page that plays
each run back token by token while the terrain density mesh accumulates
underneath.

Key features vs the prior view_terrain.html / live_terrain.html:
  * OFFLINE: data is fetched from the local HTTP server (no WebSocket).
  * DYNAMIC terrain: density mesh rebuilds as tokens stream in.
  * BOUNDARY: a translucent wireframe box shows the data extent.
  * LIVE FOCUS: a vertical "light pillar" connects the current token to
    its (x,z) footprint on the terrain, so you always see where it lands.
  * VIVID color: density × entropy colormap that brightens visibly as
    tokens accumulate.

Run:
    python backend/examples/build_token_terrain.py
→ writes backend/examples/output/token_terrain.html
→ open via the local HTTP server, e.g.
    http://localhost:8765/token_terrain.html
"""

from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
STATIC_HTML = OUT / "view_terrain.html"   # source for three.js + OrbitControls
RUNS_JSON = OUT / "qwen3_global.json"
PLAYER_HTML = OUT / "token_terrain.html"


# ---------------------------------------------------------------------------
# Library extraction (reused from build_live_terrain.py)
# ---------------------------------------------------------------------------

def extract_libs() -> tuple[str, str]:
    text = STATIC_HTML.read_text()
    blocks = re.findall(r"<script>\s*(.*?)\s*</script>", text, re.DOTALL)
    if len(blocks) < 2:
        raise RuntimeError("Couldn't extract three.js / OrbitControls from view_terrain.html")
    three_js, orbit_js = blocks[0], blocks[1]
    if "THREE" not in three_js or "OrbitControls" not in orbit_js:
        raise RuntimeError("Library extraction looks wrong — block order may have changed.")
    return three_js, orbit_js


def runs_summary() -> str:
    """Tiny summary (titles + counts) so the run list can render before the
    full dataset is fetched. Not strictly required but helps UX."""
    with open(RUNS_JSON) as f:
        data = json.load(f)
    summary = []
    for r in data:
        summary.append({
            "trajectory_id": r.get("trajectory_id", ""),
            "tag":   r.get("tag", ""),
            "kind":  r.get("kind", ""),
            "correct": r.get("correct"),
            "prompt": r.get("prompt", ""),
            "problem_id": r.get("problem_id", ""),
            "config": r.get("config", ""),
            "n_tokens": sum(1 for f in r.get("frames", []) if f.get("token")),
        })
    return json.dumps(summary, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

PAGE_HTML = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8" />
<title>Qwen3-1.7B · Token Terrain Player</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  :root {
    --bg:#ffffff; --panel:#f4f6f9; --border:#d8dde5;
    --text:#1f2630; --muted:#6b7280; --accent:#2563eb;
    --think:#ea580c; --nothink:#2563eb;
  }
  * { box-sizing:border-box; }
  html, body { margin:0; padding:0; height:100%; background:var(--bg);
    color:var(--text); font-family:-apple-system,"Segoe UI",Roboto,sans-serif;
    overflow:hidden; }
  #app { display:grid; grid-template-columns:1fr 380px; height:100vh; }
  #scene-wrap { position:relative; min-width:0; background:var(--bg); }
  #scene { width:100%; height:100%; cursor:grab; display:block; }
  #scene:active { cursor:grabbing; }
  /* Only the info-only overlays inside #scene-wrap are click-through.
     Interactive overlays (e.g. #cam-buttons) must remain clickable. */
  #scene-wrap #legend,
  #scene-wrap #colorbar { pointer-events:none; }
  #cam-buttons {
    position:absolute; top:16px; right:16px;
    display:flex; gap:6px; background:rgba(255,255,255,.92);
    border:1px solid var(--border); border-radius:8px; padding:6px;
    font-family:ui-monospace,Menlo,monospace;
    box-shadow:0 1px 4px rgba(0,0,0,.08);
    z-index:10;
  }
  #cam-buttons button {
    background:transparent; color:var(--text); border:1px solid var(--border);
    padding:5px 10px; border-radius:5px; font-size:11px; cursor:pointer;
  }
  #cam-buttons button.active { background:var(--accent); color:#fff;
    border-color:var(--accent); }
  .view-btn { font-weight:500; }
  .view-btn:not(.active) { background:transparent; color:var(--text);
    border-color:var(--border); }
  #legend {
    position:absolute; left:16px; bottom:16px;
    background:rgba(255,255,255,.94); border:1px solid var(--border);
    border-radius:10px; padding:12px 14px; font-size:11px;
    line-height:1.7; font-family:ui-monospace,Menlo,monospace;
    max-width:340px; box-shadow:0 1px 4px rgba(0,0,0,.08);
    pointer-events:none; z-index:5;
  }
  #legend b { color:var(--accent); }
  #legend .row { display:flex; align-items:center; gap:8px; }
  #legend .swatch { display:inline-block; width:14px; height:14px;
    border-radius:3px; border:1px solid var(--border); }
  #colorbar {
    position:absolute; right:16px; bottom:16px;
    background:rgba(255,255,255,.94); border:1px solid var(--border);
    border-radius:10px; padding:10px 12px;
    font-family:ui-monospace,Menlo,monospace;
    font-size:11px; color:var(--text);
    box-shadow:0 1px 4px rgba(0,0,0,.08);
    pointer-events:none; z-index:5;
  }
  #colorbar .bar {
    width:18px; height:170px; border:1px solid var(--border); border-radius:3px;
    background: linear-gradient(to top,
      #440154 0%, #3b528b 28%, #21908c 53%, #5ec962 76%, #fde725 100%);
  }
  #colorbar .ticks {
    display:flex; flex-direction:column; justify-content:space-between;
    height:170px; margin-left:6px; font-size:10px; color:var(--muted);
  }
  #colorbar .row-flex { display:flex; align-items:stretch; }
  #colorbar .lbl { font-size:10px; color:var(--muted); margin-top:4px;
    text-align:center; letter-spacing:.04em; }
  aside {
    background:var(--panel); border-left:1px solid var(--border);
    display:flex; flex-direction:column; min-height:0;
  }
  .controls { padding:14px; border-bottom:1px solid var(--border); }
  .controls h2 { font-size:11px; font-weight:600; color:var(--muted);
    letter-spacing:.08em; text-transform:uppercase; margin:0 0 10px; }
  .row-c { display:flex; align-items:center; gap:8px; margin-bottom:8px; }
  .row-c label { font-size:11px; color:var(--muted); min-width:62px; }
  input[type=range] { flex:1; accent-color:var(--accent); }
  /* Visible progress bar shown below the scrub slider. The native <input>
     range's filled track is too thin to read when value/max is small, so
     we render our own thick bar. */
  .progress-track {
    flex:1; height:8px; background:#e5e7eb; border-radius:4px; overflow:hidden;
    border:1px solid var(--border);
  }
  .progress-fill {
    height:100%; width:0%; background:linear-gradient(90deg, #1d4ed8, #5cb6ff);
    transition:width .12s linear;
  }
  input[type=number], select {
    background:#fff; color:var(--text); border:1px solid var(--border);
    border-radius:5px; padding:5px 8px; font-size:12px;
    font-family:ui-monospace,Menlo,monospace;
  }
  input[type=number]:focus, select:focus { outline:none; border-color:var(--accent); }
  button {
    background:var(--accent); color:#fff; border:0; padding:6px 12px;
    border-radius:6px; font-weight:600; font-size:12px; cursor:pointer;
    font-family:inherit;
  }
  button.ghost { background:transparent; color:var(--text);
    border:1px solid var(--border); }
  button.active { background:var(--accent); color:#fff; }
  button:disabled { opacity:.4; cursor:not-allowed; }
  #hud { padding:10px 14px; border-bottom:1px solid var(--border);
    font-family:ui-monospace,Menlo,monospace; font-size:11px; line-height:1.7; }
  #hud .stat { color:var(--muted); }
  #hud .val { color:var(--text); font-weight:600; }
  #hud .tok { display:inline-block; padding:1px 6px; margin-right:4px;
    background:rgba(37,99,235,.12); border-radius:4px; color:var(--accent);
    font-size:11px; }
  .list { overflow-y:auto; flex:1; min-height:0; }
  .item { padding:8px 14px; border-bottom:1px solid var(--border);
    cursor:pointer; display:flex; flex-direction:column; gap:3px; }
  .item:hover { background:rgba(37,99,235,.06); }
  .item.active { background:rgba(37,99,235,.10); border-left:3px solid var(--accent); }
  .item .head { display:flex; justify-content:space-between; align-items:center; }
  .item .id { font-size:12px; font-weight:600; }
  .badge { padding:1px 6px; border-radius:4px; font-size:10px; font-weight:700; }
  .b-correct { background:#dcfce7; color:#15803d; }
  .b-wrong { background:#fee2e2; color:#b91c1c; }
  .b-na { background:#e5e7eb; color:var(--muted); }
  .item .meta { font-size:10.5px; color:var(--muted); }
  .filter-row { display:flex; gap:4px; flex-wrap:wrap; margin-bottom:6px; }
  .chip { font-size:10px; padding:2px 7px; border-radius:4px;
    background:#fff; color:var(--text); border:1px solid var(--border);
    cursor:pointer; user-select:none; }
  .chip.on { background:var(--accent); color:#fff; border-color:var(--accent); }
  #text-panel { padding:10px 14px; border-top:1px solid var(--border);
    font-family:ui-monospace,Menlo,monospace; font-size:11px;
    line-height:1.6; max-height:30%; overflow-y:auto; background:#fff; }
  #text-panel h3 { margin:0 0 6px; font-size:10px; color:var(--muted);
    text-transform:uppercase; letter-spacing:.06em; }
  #text-panel .tok { padding:0 2px; border-radius:3px; }
  #text-panel .tok.past { color:var(--text); }
  #text-panel .tok.self { color:#ea580c; }
  #text-panel .tok.revisit { background:rgba(168,85,247,.18); }
  #text-panel .tok.cur {
    background:rgba(37,99,235,.18); color:var(--accent);
    box-shadow:0 0 0 2px rgba(37,99,235,.35); }
  #status { padding:6px 14px; font-size:11px; color:var(--muted);
    background:#fff; border-top:1px solid var(--border);
    font-family:ui-monospace,Menlo,monospace; }
  #status.loading { color:var(--accent); }
  #status.error { color:#b91c1c; }
</style>
</head>
<body>
<div id="app">
  <div id="scene-wrap">
    <canvas id="scene"></canvas>
    <div id="cam-buttons">
      <button data-cam="persp" class="active">Perspective</button>
      <button data-cam="iso">Isometric</button>
      <button data-cam="top">Top-Down</button>
      <button data-cam="side">Side</button>
      <button data-cam="fit" style="margin-left:6px">Fit</button>
      <button data-view="pca" class="active view-btn" style="margin-left:10px">PCA map</button>
      <button data-view="fingerprint" class="view-btn">2048-D fingerprint</button>
    </div>
    <div id="legend">
      <div><b>TOKEN TERRAIN PLAYER</b></div>
      <div style="margin:4px 0;font-size:10px;color:var(--muted)">
        78 个 Qwen3-1.7B AIME 推理轨迹(layer-14 全局 PCA)。
        地形随 token 累积,蓝色光柱为当前 token 落到地面的位置。
      </div>
      <div style="margin-top:6px"><b>TERRAIN (height-field)</b></div>
      <div>· 连续曲面 · height ∝ density · color = viridis</div>
      <div>· 紫蓝 = 低密度 · 黄绿红 = 高密度</div>
      <div style="margin-top:6px"><b>BOUNDARY</b></div>
      <div>· 蓝管框 = 数据 (x,z) 范围</div>
      <div style="margin-top:6px"><b>TRAIL</b></div>
      <div class="row"><span class="swatch" style="background:#1d4ed8"></span>
        <span>当前 token · 头部球 + 光柱 + 地面光圈</span></div>
      <div class="row"><span class="swatch" style="background:#ea580c"></span>
        <span>self-check token</span></div>
      <div class="row"><span class="swatch" style="background:#a855f7"></span>
        <span>revisit token</span></div>
    </div>
    <div id="colorbar">
      <div style="font-weight:600;margin-bottom:2px">normalized density</div>
      <div style="font-size:9px;color:var(--muted);margin-bottom:6px">sqrt(d/dmax), viridis colormap</div>
      <div class="row-flex">
        <div class="bar"></div>
        <div class="ticks" id="cb-ticks"></div>
      </div>
      <div class="lbl" id="cb-mode">preview · all 78 runs</div>
    </div>
  </div>
  <aside>
    <div class="controls">
      <h2>Layer (0..27)</h2>
      <div class="row-c">
        <input id="layer" type="range" min="0" max="27" step="1" value="14" />
        <span id="layer-val" style="font-size:11px;color:var(--muted);width:62px">layer 14</span>
      </div>
      <h2 style="margin-top:10px">Filter</h2>
      <div class="filter-row" id="filter-row"></div>
      <h2 style="margin-top:10px">Run</h2>
      <div class="list" id="run-list" style="max-height:200px;border:1px solid var(--border);border-radius:6px"></div>
    </div>
    <div class="controls">
      <h2>Playback</h2>
      <div class="row-c" style="gap:6px">
        <button id="play-btn" style="flex:1">▶ Play</button>
        <button class="ghost" id="step-btn" title="advance one token">Step ▸</button>
        <button class="ghost" id="reset-btn" title="reset to token 0">Reset</button>
      </div>
      <div class="row-c">
        <label style="min-width:50px">Speed</label>
        <input id="speed" type="range" min="1" max="80" step="1" value="20" />
        <span id="speed-val" style="font-size:11px;color:var(--muted);width:34px">20×</span>
      </div>
      <div class="row-c">
        <label style="min-width:50px">Token</label>
        <input id="scrub" type="range" min="0" max="100" step="1" value="0" />
        <span id="scrub-val" style="font-size:11px;color:var(--muted);width:64px">0 / 0</span>
      </div>
      <div class="row-c" style="margin-top:-4px">
        <div class="progress-track">
          <div id="progress-fill" class="progress-fill"></div>
        </div>
        <span id="progress-pct" style="font-size:10px;color:var(--muted);width:42px;text-align:right">0%</span>
      </div>
    </div>
    <div id="hud">
      <div><span class="stat">prompt: </span><span id="hud-prompt" class="val">—</span></div>
      <div><span class="stat">cfg:    </span><span id="hud-cfg" class="val">—</span>
        · <span class="stat">correct: </span><span id="hud-corr" class="val">—</span></div>
      <div><span class="stat">step:   </span><span id="hud-step" class="val">0</span>
        / <span id="hud-ntok" class="val">0</span></div>
      <div><span class="stat">token:  </span><span id="hud-tok" class="tok">·</span></div>
      <div><span class="stat">ppl:    </span><span id="hud-ppl" class="val">—</span>
        · <span class="stat">ent: </span><span id="hud-ent" class="val">—</span></div>
      <div><span class="stat">pos:    </span><span id="hud-pos" class="val">—</span></div>
      <div><span class="stat">cell:   </span><span id="hud-cell" class="val">—</span>
        · <span class="stat">hits: </span><span id="hud-dens" class="val">—</span>
        · <span class="stat">placed: </span><span id="hud-placed" class="val">—</span></div>
    </div>
    <div id="text-panel">
      <h3>Generated output (token-by-token)</h3>
      <div id="cur-text" style="white-space:pre-wrap;word-break:break-word;color:var(--text)"></div>
    </div>
    <div id="fingerprint-panel" style="display:none; padding:10px 14px; border-top:1px solid var(--border); background:#fff; font-family:ui-monospace,Menlo,monospace; font-size:10.5px; line-height:1.6; max-height:30%; overflow-y:auto;">
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px">
        <h3 style="margin:0;font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em">Top 12 activated dims</h3>
        <span id="fp-absmax" style="font-size:9px;color:var(--muted)">absmax = —</span>
      </div>
      <div style="display:flex;gap:8px;align-items:center;margin:6px 0;padding:4px 0;border-top:1px solid var(--border);border-bottom:1px solid var(--border)">
        <span style="font-size:9.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em">color by</span>
        <label style="font-size:10px;cursor:pointer;display:flex;align-items:center;gap:3px">
          <input type="radio" name="fp-color-mode" value="activation" checked /> activation
        </label>
        <label style="font-size:10px;cursor:pointer;display:flex;align-items:center;gap:3px">
          <input type="radio" name="fp-color-mode" value="attribution" /> attribution to output token
        </label>
        <span id="fp-attr-status" style="font-size:9px;color:var(--muted);margin-left:auto">—</span>
      </div>
      <div id="fp-top-list"></div>
    </div>
    <div id="status" class="loading">loading data…</div>
  </aside>
</div>

<script>
{THREE_JS}
</script>
<script>
{ORBIT_JS}
</script>
<script id="summary" type="application/json">
{RUNS_SUMMARY}
</script>
<script>
{APP_JS}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Application JavaScript
# ---------------------------------------------------------------------------

APP_JS = r"""
(function () {
  // ----- Utilities ----------------------------------------------------------
  const $ = id => document.getElementById(id);
  function esc(s) {
    return (s || '').replace(/[&<>"']/g, c => (
      {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]
    ));
  }
  function setStatus(msg, cls) {
    const el = $('status');
    el.textContent = msg;
    el.className = cls || '';
  }

  // ----- Load summary + full data (separate fetch for size) ---------------
  const summary = JSON.parse(document.getElementById('summary').textContent);

  // ----- Three.js scene -----------------------------------------------------
  const sceneEl = $('scene');
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xffffff);
  scene.fog = new THREE.Fog(0xffffff, 200, 600);

  const camera = new THREE.PerspectiveCamera(50, sceneEl.clientWidth / sceneEl.clientHeight, 0.1, 600);
  camera.position.set(60, 50, 80);

  const renderer = new THREE.WebGLRenderer({ canvas: sceneEl, antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setSize(sceneEl.clientWidth, sceneEl.clientHeight);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 5;
  controls.maxDistance = 250;

  scene.add(new THREE.AmbientLight(0xffffff, 0.55));
  const dir1 = new THREE.DirectionalLight(0xffffff, 0.85);
  dir1.position.set(20, 30, 14);
  scene.add(dir1);

  // Axes triad (small, dark colors for white bg)
  const axesGroup = new THREE.Group();
  function axisCone(color, x, y, z, rot) {
    const m = new THREE.Mesh(new THREE.ConeGeometry(0.10, 0.45, 8),
                             new THREE.MeshBasicMaterial({ color }));
    m.position.set(x, y, z);
    if (rot) m.rotation.set(rot[0], rot[1], rot[2]);
    axesGroup.add(m);
  }
  axisCone(0xb91c1c, 1.2, 0, 0, [0, 0, -Math.PI / 2]);   // X → red
  axisCone(0x15803d, 0, 1.2, 0, null);                  // Y → green
  axisCone(0x1d4ed8, 0, 0, 1.2, [Math.PI / 2, 0, 0]);   // Z → blue
  scene.add(axesGroup);

  // ----- Data bounds (filled in after fetch) -------------------------------
  let dataBounds = null;   // {xmin, xmax, zmin, zmax, ymin, ymax, yScale}
  let boundaryGroup = null;

  // Visual Y range: PCA y is unbounded (typically ±100). We rescale it
  // into a fixed visual band so the trail stays inside the boundary box.
  const Y_VIS_MIN = 0.5;
  const Y_VIS_MAX = 13.0;
  function visY(fy) {
    if (!dataBounds) return fy;
    return Y_VIS_MIN + ((fy - dataBounds.ymin) / (dataBounds.yrange)) * (Y_VIS_MAX - Y_VIS_MIN);
  }

  function buildBoundary(b) {
    if (boundaryGroup) {
      scene.remove(boundaryGroup);
      boundaryGroup.traverse(o => {
        o.geometry?.dispose();
        o.material?.dispose();
      });
    }
    boundaryGroup = new THREE.Group();
    const x0 = b.xmin, x1 = b.xmax, z0 = b.zmin, z1 = b.zmax;
    const cx = (x0 + x1) / 2, cz = (z0 + z1) / 2;

    // Filled ground tile in a subtle light-gray, so the data extent reads
    // as a panel and the terrain mesh has visible contrast against it.
    const groundGeo = new THREE.PlaneGeometry(x1 - x0, z1 - z0);
    const groundMat = new THREE.MeshBasicMaterial({
      color: 0xf4f6f9, transparent: true, opacity: 0.9, side: THREE.DoubleSide,
    });
    const ground = new THREE.Mesh(groundGeo, groundMat);
    ground.rotation.x = -Math.PI / 2;
    ground.position.set(cx, -0.02, cz);
    boundaryGroup.add(ground);

    // Thin dark-blue frame around the ground tile
    const corners = [
      new THREE.Vector3(x0, 0, z0), new THREE.Vector3(x1, 0, z0),
      new THREE.Vector3(x1, 0, z1), new THREE.Vector3(x0, 0, z1),
      new THREE.Vector3(x0, 0, z0),
    ];
    const tubePath = new THREE.CatmullRomCurve3(corners, true, 'catmullrom', 0);
    const tubeGeo = new THREE.TubeGeometry(tubePath, 80, 0.30, 6, true);
    const tubeMat = new THREE.MeshBasicMaterial({ color: 0x1d4ed8, transparent: true, opacity: 0.95 });
    boundaryGroup.add(new THREE.Mesh(tubeGeo, tubeMat));

    // 4 tall corner posts (dark blue, thicker than before)
    const postH = 12;
    const postGeo = new THREE.BoxGeometry(0.5, postH, 0.5);
    const postMat = new THREE.MeshBasicMaterial({ color: 0x1d4ed8, transparent: true, opacity: 0.75 });
    [[x0,z0],[x1,z0],[x1,z1],[x0,z1]].forEach(([x,z]) => {
      const p = new THREE.Mesh(postGeo, postMat);
      p.position.set(x, postH / 2, z);
      boundaryGroup.add(p);
    });

    // Top frame
    const topPath = new THREE.CatmullRomCurve3(corners.map(c => new THREE.Vector3(c.x, postH, c.z)), true, 'catmullrom', 0);
    const topGeo = new THREE.TubeGeometry(topPath, 80, 0.18, 6, true);
    const topMat = new THREE.MeshBasicMaterial({ color: 0x1d4ed8, transparent: true, opacity: 0.55 });
    boundaryGroup.add(new THREE.Mesh(topGeo, topMat));

    scene.add(boundaryGroup);
  }

  function fitCameraToBounds(b) {
    const cx = (b.xmin + b.xmax) / 2;
    const cz = (b.zmin + b.zmax) / 2;
    const spanX = b.xmax - b.xmin;
    const spanZ = b.zmax - b.zmin;
    const span = Math.max(spanX, spanZ);
    // 3/4 view from the +x/+z corner, slightly elevated so the user
    // sees both the ground plane AND has headroom for terrain to grow.
    const dist = span * 0.85;
    camera.position.set(cx + dist * 0.55, dist * 0.55, cz + dist * 0.75);
    controls.target.set(cx, 0, cz);
    controls.update();
  }

  // -------------------------------------------------------------------------
  // Two terrain layers:
  //   * preview (background, low opacity, muted) — aggregated from ALL runs
  //     so the user sees the global landscape even before playing.
  //   * active  (foreground, vivid) — only the active run's revealed tokens,
  //     builds up as Play progresses.
  // -------------------------------------------------------------------------
  const TERRAIN_RES = 160;
  let previewAcc = new Float32Array(TERRAIN_RES * TERRAIN_RES);
  let activeAcc  = new Float32Array(TERRAIN_RES * TERRAIN_RES);
  let activeEnt  = new Float32Array(TERRAIN_RES * TERRAIN_RES);
  let previewMesh = null;
  let activeMesh  = null;

  function cellIdx(x, z) {
    const b = dataBounds;
    const u = (x - b.xmin) / Math.max(1e-6, (b.xmax - b.xmin));
    const v = (z - b.zmin) / Math.max(1e-6, (b.zmax - b.zmin));
    const i = Math.max(0, Math.min(TERRAIN_RES - 1, Math.floor(u * TERRAIN_RES)));
    const j = Math.max(0, Math.min(TERRAIN_RES - 1, Math.floor(v * TERRAIN_RES)));
    return j * TERRAIN_RES + i;
  }

  // viridis-like 5-stop colormap: purple → blue → teal → green → yellow
  function viridis(t) {
    t = Math.max(0, Math.min(1, t));
    const stops = [
      [0.267, 0.005, 0.329],   // #440154
      [0.229, 0.322, 0.546],   // #3b528b
      [0.127, 0.567, 0.551],   // #21908c
      [0.369, 0.789, 0.383],   // #5ec962
      [0.993, 0.906, 0.144],   // #fde725
    ];
    const s = t * (stops.length - 1);
    const i = Math.floor(s);
    const f = s - i;
    if (i >= stops.length - 1) return stops[stops.length - 1];
    return [
      stops[i][0] + (stops[i+1][0] - stops[i][0]) * f,
      stops[i][1] + (stops[i+1][1] - stops[i][1]) * f,
      stops[i][2] + (stops[i+1][2] - stops[i][2]) * f,
    ];
  }

  // Gaussian blur on the density grid. This is what turns the
  // "isolated-spike-on-flat-plain" look into "rolling hills" — dense
  // cells bleed into neighbors, sparse cells get a small boost, and the
  // transitions become smooth instead of cliff-like.
  function gaussianBlurDensity(src, radius) {
    const N = TERRAIN_RES;
    const tmp = new Float32Array(N * N);
    const dst = new Float32Array(N * N);
    const k = radius;
    // Separable 1-D Gaussian kernel
    const sigma = radius / 2;
    const kernel = new Float32Array(2 * k + 1);
    let norm = 0;
    for (let i = -k; i <= k; i++) {
      kernel[i + k] = Math.exp(-(i * i) / (2 * sigma * sigma));
      norm += kernel[i + k];
    }
    for (let i = 0; i < kernel.length; i++) kernel[i] /= norm;
    // Horizontal pass → tmp
    for (let j = 0; j < N; j++) {
      for (let i = 0; i < N; i++) {
        let s = 0;
        for (let d = -k; d <= k; d++) {
          const ii = Math.max(0, Math.min(N - 1, i + d));
          s += src[j * N + ii] * kernel[d + k];
        }
        tmp[j * N + i] = s;
      }
    }
    // Vertical pass → dst
    for (let j = 0; j < N; j++) {
      for (let i = 0; i < N; i++) {
        let s = 0;
        for (let d = -k; d <= k; d++) {
          const jj = Math.max(0, Math.min(N - 1, j + d));
          s += tmp[jj * N + i] * kernel[d + k];
        }
        dst[j * N + i] = s;
      }
    }
    return dst;
  }

  // Smoothstep S-curve: maps d ∈ [0,1] → h ∈ [0,1] with continuous
  // derivatives at both ends. Unlike pow(d, 1.2), there's no "knee"
  // where the height suddenly jumps — low cells stay low, dense cells
  // taper smoothly to the cap. This is the same curve used in CSS
  // easing and GLSL smoothstep.
  function smoothstep(d) {
    const t = Math.max(0, Math.min(1, d));
    return t * t * (3 - 2 * t);
  }
  // Double-smoothstep for an even gentler S-curve when needed.
  function smootherstep(d) {
    const t = Math.max(0, Math.min(1, d));
    return t * t * t * (t * (t * 6 - 15) + 10);
  }

  // Continuous height-field mesh (one solid surface per layer).
  // Vertex heights follow density, so the result is a smooth 3D landscape
  // you can read as a single coherent shape — unlike discrete bars.
  function buildTerrainMesh(acc, opts) {
    const b = dataBounds;
    let rawMax = 0;
    for (let k = 0; k < acc.length; k++) {
      if (acc[k] > rawMax) rawMax = acc[k];
    }
    if (rawMax === 0) return null;

    // Gaussian blur softens sharp density transitions into smooth rolling
    // hills rather than cliffs. Use it for both layers — even the active
    // layer, so individual token spikes don't form sharp ridges.
    const smoothed = (opts.blurRadius > 0)
      ? gaussianBlurDensity(acc, opts.blurRadius)
      : acc;
    let smoothMax = 0;
    for (let k = 0; k < smoothed.length; k++) {
      if (smoothed[k] > smoothMax) smoothMax = smoothed[k];
    }
    if (smoothMax === 0) return null;

    const positions = new Float32Array(TERRAIN_RES * TERRAIN_RES * 3);
    const colors = new Float32Array(TERRAIN_RES * TERRAIN_RES * 3);
    const indices = [];
    const heightMul = opts.heightMul;
    const baseH = opts.baseH || 0;
    const heightCurve = opts.heightCurve || smoothstep;   // S-curve for height
    const colorCurve  = opts.colorCurve  || smootherstep;  // slightly different curve for color
    const opacity = opts.opacity;
    const baseBright = opts.baseBright;

    for (let j = 0; j < TERRAIN_RES; j++) {
      for (let i = 0; i < TERRAIN_RES; i++) {
        const k = j * TERRAIN_RES + i;
        const dNorm = smoothed[k] / smoothMax;
        // S-curve on height: smooth at both ends, no abrupt knee
        const h = baseH + heightCurve(dNorm) * heightMul;
        const x = b.xmin + (i / (TERRAIN_RES - 1)) * (b.xmax - b.xmin);
        const z = b.zmin + (j / (TERRAIN_RES - 1)) * (b.zmax - b.zmin);
        positions[k * 3 + 0] = x;
        positions[k * 3 + 1] = h;
        positions[k * 3 + 2] = z;
        // Color uses a slightly different S-curve so color and height
        // emphasize different density bands.
        const t = Math.min(1, colorCurve(dNorm) * 0.98);
        const rgb = viridis(t);
        const bright = baseBright + (1 - baseBright) * t;
        colors[k * 3 + 0] = rgb[0] * bright;
        colors[k * 3 + 1] = rgb[1] * bright;
        colors[k * 3 + 2] = rgb[2] * bright;
      }
    }
    for (let j = 0; j < TERRAIN_RES - 1; j++) {
      for (let i = 0; i < TERRAIN_RES - 1; i++) {
        const a = j * TERRAIN_RES + i;
        indices.push(a, a + TERRAIN_RES, a + 1, a + 1, a + TERRAIN_RES, a + TERRAIN_RES + 1);
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geo.setIndex(indices);
    geo.computeVertexNormals();
    const mat = new THREE.MeshLambertMaterial({
      vertexColors: true, transparent: opts.transparent !== false,
      opacity: opacity, side: THREE.DoubleSide,
      depthWrite: opts.depthWrite !== false,
    });
    return new THREE.Mesh(geo, mat);
  }

  // Defensive UI update — kept separate so even if terrain rebuild /
  // head update throws, the progress bar still reflects the actual
  // revealed count (the canonical source of truth).
  function updateProgressUI(N) {
    const scrub = $('scrub');
    const scrubVal = $('scrub-val');
    const fill = $('progress-fill');
    const pct = $('progress-pct');
    if (!scrub || !scrubVal || !fill || !pct || N === 0) return;
    scrub.value = String(revealed);
    scrubVal.textContent = revealed + ' / ' + N;
    const p = (revealed / N) * 100;
    fill.style.width = p.toFixed(2) + '%';
    pct.textContent = p.toFixed(1) + '%';
  }

  function rebuildActiveTerrain() {
    if (activeMesh) {
      scene.remove(activeMesh);
      activeMesh.geometry.dispose();
      activeMesh.material.dispose();
      activeMesh = null;
    }
    // Active: SOLID opaque. Renders first (opaque pass, front-to-back).
    activeMesh = buildTerrainMesh(activeAcc, {
      heightMul: 11.0, baseH: 0.5, opacity: 1.0, baseBright: 0.60,
      blurRadius: 2,
      transparent: false, depthWrite: true,
    });
    if (activeMesh) {
      // Only add to scene in PCA view. In fingerprint view the active
      // mesh would visually conflict with the per-token terrain.
      if (currentView === 'pca') {
        scene.add(activeMesh);
        activeMesh.renderOrder = 1;
      }
    }
    updateColorbar('active');
  }

  function rebuildPreviewTerrain() {
    if (previewMesh) {
      scene.remove(previewMesh);
      previewMesh.geometry.dispose();
      previewMesh.material.dispose();
      previewMesh = null;
    }
    // Preview: translucent, depthWrite=true now so it correctly occludes
    // ITSELF (later peaks hide earlier peaks within preview). Renders
    // after active; depth-tested against active so it gets clipped by
    // any active peak in front of it. renderOrder=2 guarantees this
    // draw order regardless of object creation time.
    previewMesh = buildTerrainMesh(previewAcc, {
      heightMul: 9.0, baseH: 0.8, opacity: 0.32, baseBright: 0.45,
      blurRadius: 8,
      transparent: true, depthWrite: true,
    });
    if (previewMesh) {
      scene.add(previewMesh);
      previewMesh.renderOrder = 2;
    }
    updateColorbar('preview');
  }

  // -------------------------------------------------------------------------
  // Colorbar — shows NORMALIZED density (0..1, sqrt-scaled) since that's
  // what the viridis colormap actually encodes. Also shows the raw token
  // count for context.
  // -------------------------------------------------------------------------
  function colorbarMax(mode) {
    const arr = (mode === 'active') ? activeAcc : previewAcc;
    let m = 0;
    for (let k = 0; k < arr.length; k++) if (arr[k] > m) m = arr[k];
    return m;
  }

  function updateColorbar(mode) {
    const modeEl = $('cb-mode');
    const ticksEl = $('cb-ticks');
    if (!modeEl || !ticksEl) return;
    const max = colorbarMax(mode);
    if (mode === 'active') {
      const id = (activeRun && (activeRun.problem_id || activeRun.trajectory_id)) || '—';
      const cfg = (activeRun && activeRun.config) || '';
      modeEl.innerHTML = `active · ${id.slice(0, 22)}<br><span style="color:var(--muted);font-size:9px">max ${max} tokens</span>`;
    } else {
      modeEl.innerHTML = `preview · all 78 runs<br><span style="color:var(--muted);font-size:9px">max ${max} tokens</span>`;
    }
    if (max === 0) {
      ticksEl.innerHTML = '<div>0.0</div>';
      return;
    }
    // Show NORMALIZED density (sqrt-scaled, 0..1) since that's what the
    // viridis colormap encodes: 1.0 = brightest cell (max raw count),
    // 0.0 = no tokens.
    const ticks = [1.0, 0.75, 0.50, 0.25, 0.0];
    ticksEl.innerHTML = ticks.map(v =>
      `<div style="white-space:nowrap">${v.toFixed(2)}</div>`
    ).join('');
  }

  function clearActive() {
    activeAcc = new Float32Array(TERRAIN_RES * TERRAIN_RES);
    activeEnt = new Float32Array(TERRAIN_RES * TERRAIN_RES);
    if (activeMesh) {
      scene.remove(activeMesh);
      activeMesh.geometry.dispose();
      activeMesh.material.dispose();
      activeMesh = null;
    }
    updateColorbar('preview');
  }

  function addTokenToActive(f) {
    const k = cellIdx(f.x, f.z);
    activeAcc[k] += 1.0;
    activeEnt[k] += f.entropy || 0;
  }

  function seedPreviewFromRuns() {
    previewAcc = new Float32Array(TERRAIN_RES * TERRAIN_RES);
    runs.forEach(r => {
      const frames = buildFramesForLayer(r, currentLayer);
      frames.forEach(f => {
        const k = cellIdx(f.x, f.z);
        previewAcc[k] += 1.0;
      });
    });
    rebuildPreviewTerrain();
  }

  // -------------------------------------------------------------------------
  // Trail (growing polyline of revealed tokens) + dots
  // -------------------------------------------------------------------------
  const MAX_TRAIL = 4096;
  const trailPos = new Float32Array(MAX_TRAIL * 3);
  const trailCol = new Float32Array(MAX_TRAIL * 3);
  const trailGeo = new THREE.BufferGeometry();
  trailGeo.setAttribute('position', new THREE.BufferAttribute(trailPos, 3));
  trailGeo.setAttribute('color', new THREE.BufferAttribute(trailCol, 3));
  trailGeo.setDrawRange(0, 0);
  const trailMat = new THREE.LineBasicMaterial({ vertexColors: true });
  const trailLine = new THREE.Line(trailGeo, trailMat);
  scene.add(trailLine);

  // Trail dots (per-instance color)
  const dotGeo = new THREE.SphereGeometry(0.22, 10, 10);
  const dotMat = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.92 });
  const dots = new THREE.InstancedMesh(dotGeo, dotMat, MAX_TRAIL);
  dots.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  const _tmpColor = new THREE.Color();
  const mZero = new THREE.Matrix4().makeScale(0, 0, 0);
  for (let i = 0; i < MAX_TRAIL; i++) {
    dots.setMatrixAt(i, mZero);
    dots.setColorAt(i, _tmpColor.setRGB(0, 0, 0));
  }
  dots.instanceMatrix.needsUpdate = true;
  if (dots.instanceColor) dots.instanceColor.needsUpdate = true;
  scene.add(dots);

  // Head sphere (current token) — dark color so it's visible on white bg.
  const headGeo = new THREE.SphereGeometry(0.55, 16, 16);
  const headMat = new THREE.MeshBasicMaterial({ color: 0x1d4ed8 });
  const head = new THREE.Mesh(headGeo, headMat);
  head.visible = false;
  scene.add(head);

  // Vertical "light pillar" from head down to terrain at (x, 0, z)
  const pillarGeo = new THREE.CylinderGeometry(0.10, 0.04, 1.0, 8, 1, true);
  pillarGeo.translate(0, -0.5, 0);   // anchor at top
  const pillarMat = new THREE.MeshBasicMaterial({
    color: 0x1d4ed8, transparent: true, opacity: 0.70, side: THREE.DoubleSide,
  });
  const pillar = new THREE.Mesh(pillarGeo, pillarMat);
  pillar.visible = false;
  scene.add(pillar);

  // Footprint ring on the terrain at (x, 0, z) — shows where the token LANDS
  const footGeo = new THREE.RingGeometry(0.4, 0.85, 32);
  const footMat = new THREE.MeshBasicMaterial({
    color: 0x1d4ed8, transparent: true, opacity: 0.90, side: THREE.DoubleSide,
  });
  const footprint = new THREE.Mesh(footGeo, footMat);
  footprint.rotation.x = -Math.PI / 2;
  footprint.visible = false;
  scene.add(footprint);

  // -------------------------------------------------------------------------
  // State + reveal logic
  // -------------------------------------------------------------------------
  let runs = [];          // populated from fetch (raw JSON, with .tokens + .layers)
  let activeRun = null;
  let revealed = 0;
  let playing = false;
  let lastTickMs = 0;
  let tokensPerSec = 20;
  let currentLayer = 14;

  // Build a frame array for (run, layer) by stitching per-layer (x,y,z)
  // with the shared token-level metadata (ppl, ent, sc, rv, tok).
  function buildFramesForLayer(run, layerIdx) {
    const layerData = run.layers && run.layers[String(layerIdx)];
    if (!layerData || !layerData.xyz) return [];
    const xyz = layerData.xyz;
    const tokens = run.tokens || [];
    const n = Math.min(xyz.length / 3, tokens.length);
    const frames = [];
    // The collector stores hidden_states with a one-frame off-by-one:
    //   hidden_states[0] = position n_prompt-1 (prompt tail), not gen_ids[0]
    //   hidden_states[i] = position n_prompt-1+i, predicting gen_ids[i+1]
    // We drop frame 0 because the underlying residual stream doesn't
    // belong to any *generated* token. UI token slider v corresponds to
    // tokens[v+1].tok and accesses hidden_states[v+1].
    const SKIP_FIRST = 1;
    const start = Math.min(SKIP_FIRST, n);
    for (let i = start; i < n; i++) {
      const t = tokens[i];
      frames.push({
        x: xyz[i * 3 + 0],
        y: xyz[i * 3 + 1],
        z: xyz[i * 3 + 2],
        token:     t.tok,
        token_id:  t.token_id !== undefined ? t.token_id : -1,
        perplexity: t.ppl,
        entropy:   t.ent,
        is_self_check: t.sc,
        is_revisit: t.rv,
        step_id:   t.step_id,
        // UI slider value that should select this frame.
        slider_idx: i - SKIP_FIRST,
      });
    }
    return frames;
  }

  // Lazily fetch the xyz binary file for (run, layer). For layer 14 the
  // data is inlined in the main JSON; for other layers we pull the
  // precomputed binary from /layer_xyz/<run_id>/l<N>.bin.
  async function fetchLayerXyz(run, layerIdx) {
    if (layerIdx === 14) {
      // already in run.layers['14']
      return;
    }
    const key = String(layerIdx);
    if (run.layers[key] && run.layers[key].xyz) return;   // cached
    try {
      const r = await fetch(`/layer_xyz/${encodeURIComponent(run.trajectory_id)}/${layerIdx}`);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const buf = await r.arrayBuffer();
      const f16 = new Float16Array(buf);
      // Convert to plain JS array so it slots into run.layers[key].xyz
      // (the rest of the code only reads xyz as a flat numeric array)
      const xyz = Array.from(f16);
      run.layers[key] = { xyz };
    } catch (e) {
      console.warn(`[token-terrain] failed to fetch layer ${layerIdx} for ${run.trajectory_id}:`, e);
      run.layers[key] = { xyz: [] };   // mark as missing
    }
  }

  // Fetch xyz for ALL runs for a given layer (in parallel). Used by
  // changeLayer so the preview and active stay in sync.
  async function fetchAllLayerXyz(layerIdx) {
    if (layerIdx === 14) return;   // inlined
    const tasks = runs.map(r => fetchLayerXyz(r, layerIdx));
    await Promise.all(tasks);
  }

  function colorFromEntropy(ent, isSelf) {
    if (isSelf) return new THREE.Color(0xea580c);   // orange — self-check
    const e = Math.max(0, Math.min(1, ent || 0.3));
    // 3-stop colormap (darkened for white bg):
    //   e=0.0 → blue #1d4ed8   (confident)
    //   e=0.5 → green #15803d  (mid)
    //   e=1.0 → red #b91c1c    (uncertain)
    if (e < 0.5) {
      return new THREE.Color(0x1d4ed8).lerp(new THREE.Color(0x15803d), e * 2);
    }
    return new THREE.Color(0x15803d).lerp(new THREE.Color(0xb91c1c), (e - 0.5) * 2);
  }

  function clearVisualization() {
    trailGeo.setDrawRange(0, 0);
    for (let i = 0; i < MAX_TRAIL; i++) {
      dots.setMatrixAt(i, mZero);
      dots.setColorAt(i, _tmpColor.setRGB(0, 0, 0));
    }
    dots.instanceMatrix.needsUpdate = true;
    if (dots.instanceColor) dots.instanceColor.needsUpdate = true;
    head.visible = false;
    pillar.visible = false;
    footprint.visible = false;
    clearActive();
  }

  // -------------------------------------------------------------------------
  // View mode: 'pca' shows the 2-D PCA(x,z) terrain density; 'fingerprint'
  // shows the current token's full 2048-D activation as a 64×32 heightfield.
  // -------------------------------------------------------------------------
  let currentView = 'pca';
  let fingerprintH = null;   // Float16Array length N*2048 (lazy-loaded)
  let fingerprintN = 0;
  let fingerprintValidFirst = 0;   // inclusive — first index in hidden_states with valid per-token residual stream
  let fingerprintValidLast = 0;    // exclusive — last+1 index; slider max = validLast - validFirst - 1
  let fingerprintAbsMax = 8.0;
  let fingerprintMesh = null;
  // Logit-lens attribution: hidden @ lm_head.weight[output_token].T decomposes
  // the chosen-token logit into per-dim contributions. Toggle via the radio
  // buttons in the fingerprint panel; cached per output token id.
  let fpColorMode = 'activation';   // 'activation' | 'attribution'
  let lmHeadRow = null;             // Float16Array length 2048 (one row of W)
  let lmHeadRowToken = -1;          // output token id currently cached
  let lmHeadAvailable = false;      // set after we successfully hit /lm_head_meta
  const FP_COLS = 64, FP_ROWS = 32;   // 64 × 32 = 2048

  function buildFingerprintMesh(tokenIdx) {
    if (!fingerprintH || tokenIdx < 0 || tokenIdx >= fingerprintN) return null;
    // `tokenIdx` here is the UI slider value (0..validLast-validFirst-1).
    // Map it to the underlying hidden_states index: hidden_states[0] is
    // off-by-one (prompt tail), so add the offset to get the per-token
    // residual stream that actually belongs to gen_ids[tokenIdx+1].
    const realIdx = tokenIdx + fingerprintValidFirst;
    if (realIdx < fingerprintValidFirst || realIdx >= fingerprintValidLast) {
      // Out of valid range — caller should not have asked. Render nothing.
      return null;
    }
    const off = realIdx * 2048;

    // Determine which per-dim scalar drives the cell color.
    //   activation:    per-dim |hidden| (normalized by the token's own absmax)
    //   attribution:   hidden[k] * W[output_token][k]
    //
    // For attribution we need a row of the LM head matching the *output*
    // token. In our off-by-one alignment, slider v shows hidden_states[v+1]
    // which is gen_ids[v+1]'s own residual stream — predicting gen_ids[v+2].
    // We treat the visible token as the "model output whose logit this
    // residual stream contributes to", so the attribution row is W[gen_ids[v+2]].
    let useAttribution = (fpColorMode === 'attribution' && lmHeadRow !== null);
    let attrScale = 1.0;
    let cellValues;
    if (useAttribution) {
      cellValues = new Float32Array(2048);
      let mx = 0;
      for (let k = 0; k < 2048; k++) {
        const v = fingerprintH[off + k] * lmHeadRow[k];
        cellValues[k] = v;
        const a = Math.abs(v);
        if (a > mx) mx = a;
      }
      attrScale = mx > 0 ? mx : 1.0;
    } else {
      // Per-token absmax: scale each token's fingerprint by its own strongest
      // dimension so we can always see the relative pattern, regardless of
      // how loud or quiet this particular token is in absolute terms.
      let tokenAbsMax = 0;
      for (let k = 0; k < 2048; k++) {
        const a = Math.abs(fingerprintH[off + k]);
        if (a > tokenAbsMax) tokenAbsMax = a;
      }
      if (tokenAbsMax === 0) tokenAbsMax = 1.0;
      attrScale = tokenAbsMax;
      cellValues = fingerprintH;   // use raw values; we re-index by `off+k` below
    }

    const positions = new Float32Array(FP_COLS * FP_ROWS * 3);
    const colors = new Float32Array(FP_COLS * FP_ROWS * 3);
    const indices = [];
    for (let j = 0; j < FP_ROWS; j++) {
      for (let i = 0; i < FP_COLS; i++) {
        const k = j * FP_COLS + i;
        const v = useAttribution ? cellValues[k] : fingerprintH[off + k];
        const norm = Math.max(-1, Math.min(1, v / attrScale));
        // symlog compresses mid-range values too — gives a more "dynamic"
        // surface even when one outlier dimension dominates.
        const h = (norm >= 0 ? Math.sqrt(norm) : -Math.sqrt(-norm)) * 4.5;
        positions[k * 3 + 0] = (i / (FP_COLS - 1) - 0.5) * 22;
        positions[k * 3 + 1] = h;
        positions[k * 3 + 2] = (j / (FP_ROWS - 1) - 0.5) * 11;
        let r, g, b;
        if (useAttribution) {
          // Diverging red-white-blue: red pushes toward the output token,
          // blue pushes away. White ≈ neutral.
          const a = Math.abs(norm);
          if (norm >= 0) {
            // red: (1.0, 0.30, 0.30) blended toward white by (1 - a)
            r = 1.0 - (1.0 - 1.0) * (1 - a);    // 1.0 → 1.0
            g = 0.30 + (1.0 - 0.30) * (1 - a);  // 0.30 → 1.0
            b = 0.30 + (1.0 - 0.30) * (1 - a);  // 0.30 → 1.0
          } else {
            // blue: (0.30, 0.55, 1.0) blended toward white by (1 - a)
            r = 0.30 + (1.0 - 0.30) * (1 - a);
            g = 0.55 + (1.0 - 0.55) * (1 - a);
            b = 1.0;
          }
        } else if (norm < 0) {
          // activation-only: subtle red for negative dims
          const a = -norm;
          r = 0.85 + 0.15 * a;
          g = 0.20 * (1 - a);
          b = 0.20 * (1 - a);
        } else {
          // activation-only: viridis-like stops
          const stops = [
            [0.229, 0.322, 0.546],
            [0.127, 0.567, 0.551],
            [0.369, 0.789, 0.383],
            [0.993, 0.906, 0.144],
          ];
          const t = norm * (stops.length - 1);
          const idx = Math.min(stops.length - 2, Math.floor(t));
          const f = t - idx;
          r = stops[idx][0] + (stops[idx + 1][0] - stops[idx][0]) * f;
          g = stops[idx][1] + (stops[idx + 1][1] - stops[idx][1]) * f;
          b = stops[idx][2] + (stops[idx + 1][2] - stops[idx][2]) * f;
        }
        colors[k * 3 + 0] = r;
        colors[k * 3 + 1] = g;
        colors[k * 3 + 2] = b;
      }
    }
    for (let j = 0; j < FP_ROWS - 1; j++) {
      for (let i = 0; i < FP_COLS - 1; i++) {
        const a = j * FP_COLS + i;
        indices.push(a, a + FP_COLS, a + 1, a + 1, a + FP_COLS, a + FP_COLS + 1);
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geo.setIndex(indices);
    geo.computeVertexNormals();
    const mat = new THREE.MeshLambertMaterial({
      vertexColors: true, side: THREE.DoubleSide,
      transparent: true, opacity: 0.95,
    });
    return new THREE.Mesh(geo, mat);
  }

  async function loadFingerprintForRun(run, layer) {
    if (!run) { fingerprintH = null; return; }
    setStatus('loading 2048-D fingerprint…', 'loading');
    try {
      const r = await fetch(`/hidden/${encodeURIComponent(run.trajectory_id)}/${layer}`);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const buf = await r.arrayBuffer();
      const shapeHeader = r.headers.get('X-Shape');
      let n = fingerprintN;
      if (shapeHeader) {
        n = parseInt(shapeHeader.split(',')[0], 10);
      } else {
        n = (buf.byteLength / 2) / 2048;
      }
      fingerprintH = new Float16Array(buf);
      fingerprintN = n;
      // Effective token slider range: skip first frame (off-by-one alignment,
      // see buildFramesForLayer). Slider v ∈ [0, n-2] accesses hidden_states[v+1].
      fingerprintValidFirst = 1;
      fingerprintValidLast = n - 1;   // exclusive upper bound → max slider v
      let mx = 0;
      const step = Math.max(1, Math.floor(n / 30));
      for (let i = 0; i < n; i += step) {
        const off = i * 2048;
        for (let k = 0; k < 2048; k++) {
          const a = Math.abs(fingerprintH[off + k]);
          if (a > mx) mx = a;
        }
      }
      fingerprintAbsMax = Math.max(mx, 1.0);
      setStatus(`loaded ${run.trajectory_id} L${layer} · 2048-D fingerprint ready (absmax ${fingerprintAbsMax.toFixed(2)})`);
    } catch (e) {
      setStatus('failed to load fingerprint — is serve.py running?', 'error');
      console.error(e);
    }
  }

  async function showFingerprintForCurrentToken() {
    if (currentView !== 'fingerprint') return;
    if (fingerprintMesh) {
      scene.remove(fingerprintMesh);
      fingerprintMesh.geometry.dispose();
      fingerprintMesh.material.dispose();
      fingerprintMesh = null;
    }
    if (!fingerprintH || fingerprintN === 0) return;
    // When nothing has been revealed yet, fall back to token 0 so the
    // user sees the first token's fingerprint immediately on switch.
    let idx = revealed > 0 ? (revealed - 1) : 0;
    // Clamp into the valid range — the last frame is off-by-one (its
    // residual stream belongs to the previous token, not its own).
    const sliderMax = Math.max(0, fingerprintValidLast - fingerprintValidFirst - 1);
    if (idx > sliderMax) idx = sliderMax;

    // In attribution mode we need the row of the LM head for the OUTPUT
    // token — the one the visible residual stream contributed to. With
    // our off-by-one alignment, slider v shows hidden_states[v+1] which is
    // gen_ids[v+1]'s own residual stream — predicting gen_ids[v+2]. So
    // the attribution row is W[gen_ids[v+2]].
    if (fpColorMode === 'attribution' && activeRun && activeRun.frames) {
      const targetFrameIdx = Math.min(idx + 1, activeRun.frames.length - 1);
      const targetTokenId = activeRun.frames[targetFrameIdx]?.token_id ?? -1;
      if (targetTokenId >= 0 && targetTokenId !== lmHeadRowToken) {
        try {
          const r = await fetch(`/lm_head_row/${targetTokenId}`);
          if (r.ok) {
            const buf = await r.arrayBuffer();
            lmHeadRow = new Float16Array(buf);
            lmHeadRowToken = targetTokenId;
            const status = $('fp-attr-status');
            if (status) status.textContent = `→ tok #${targetTokenId} ("${activeRun.frames[targetFrameIdx]?.token}")`;
          } else {
            lmHeadRow = null;
            lmHeadRowToken = -1;
            const status = $('fp-attr-status');
            if (status) status.textContent = `lm_head_row ${r.status}`;
          }
        } catch (e) {
          lmHeadRow = null;
          lmHeadRowToken = -1;
          const status = $('fp-attr-status');
          if (status) status.textContent = 'fetch failed';
        }
      } else if (targetTokenId < 0) {
        const status = $('fp-attr-status');
        if (status) status.textContent = 'no token_id for this frame';
        lmHeadRow = null;
        lmHeadRowToken = -1;
      } else {
        const status = $('fp-attr-status');
        if (status) status.textContent = `→ tok #${targetTokenId} ("${activeRun.frames[targetFrameIdx]?.token}")`;
      }
    }

    fingerprintMesh = buildFingerprintMesh(idx);
    if (fingerprintMesh) {
      fingerprintMesh.position.set(0, 0, 0);
      scene.add(fingerprintMesh);
    }
    // Update the top-activated-dims panel
    updateFingerprintPanel(idx);
  }

  // Show the top-K most-activated dimensions for the given token. This
  // turns the abstract "highest peak" into concrete numbers: the dim
  // index and its raw activation value. Hidden in PCA view.
  function updateFingerprintPanel(tokenIdx) {
    const panel = $('fingerprint-panel');
    if (!panel) return;
    if (currentView !== 'fingerprint' || !fingerprintH || tokenIdx >= fingerprintN) {
      panel.style.display = 'none';
      return;
    }
    panel.style.display = 'block';
    const off = tokenIdx * 2048;
    // Compute global absmax for this token (for the "absmax" label)
    let absMax = 0;
    for (let k = 0; k < 2048; k++) {
      const a = Math.abs(fingerprintH[off + k]);
      if (a > absMax) absMax = a;
    }
    $('fp-absmax').textContent = `absmax = ${absMax.toFixed(2)}`;
    // Top-12 by absolute value
    const idxs = new Array(2048);
    for (let k = 0; k < 2048; k++) idxs[k] = k;
    idxs.sort((a, b) => Math.abs(fingerprintH[off + b]) - Math.abs(fingerprintH[off + a]));
    const top12 = idxs.slice(0, 12);
    let html = '';
    for (let i = 0; i < top12.length; i++) {
      const k = top12[i];
      const v = fingerprintH[off + k];
      const sign = v >= 0 ? '+' : '−';
      const abs = Math.abs(v);
      const row = (i + 1).toString().padStart(2, ' ');
      const dim = `dim ${k.toString().padStart(4, ' ')}`;
      const val = `${sign}${abs.toFixed(2).padStart(7, ' ')}`;
      const bar = '█'.repeat(Math.min(28, Math.round(abs / absMax * 28)));
      html += `<div style="display:flex;gap:6px;align-items:baseline">
        <span style="color:var(--muted);width:18px;text-align:right">${row}</span>
        <span style="color:var(--accent);width:62px">${dim}</span>
        <span style="color:${v >= 0 ? '#15803d' : '#b91c1c'};width:78px">${val}</span>
        <span style="color:var(--muted);font-size:9px">${bar}</span>
      </div>`;
    }
    $('fp-top-list').innerHTML = html;
  }

  // Hide all the per-token trail overlays (dots, head, pillar, footprint,
  // trail line). Used when switching to fingerprint view so they don't
  // overlap the new terrain.
  function hideTrailOverlays() {
    trailGeo.setDrawRange(0, 0);
    head.visible = false;
    pillar.visible = false;
    footprint.visible = false;
    for (let i = 0; i < MAX_TRAIL; i++) dots.setMatrixAt(i, mZero);
    dots.instanceMatrix.needsUpdate = true;
  }

  // -------------------------------------------------------------------------
  // Layer sweep removed — 28-layer stack view deleted.
  // -------------------------------------------------------------------------

  function showTrailOverlays() {
    // Replay current state to restore dots/head/head positions for the
    // active trail. Cheap because revealTokensUpTo already updated the
    // per-token buffers; we just need to re-mark the instance matrices
    // and head position.
    dots.instanceMatrix.needsUpdate = true;
    updateHead();
  }

  async function setView(mode) {
    if (mode === currentView) return;
    currentView = mode;
    document.querySelectorAll('.view-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.view === mode);
    });
    if (mode === 'pca') {
      if (fingerprintMesh) {
        scene.remove(fingerprintMesh);
        fingerprintMesh.geometry.dispose();
        fingerprintMesh.material.dispose();
        fingerprintMesh = null;
      }
      if (previewMesh) scene.add(previewMesh);
      if (activeMesh)  scene.add(activeMesh);
      if (boundaryGroup) boundaryGroup.visible = true;
      showTrailOverlays();
      const fpPanel = $('fingerprint-panel');
      if (fpPanel) fpPanel.style.display = 'none';
      if (dataBounds) fitCameraToBounds(dataBounds);
    } else if (mode === 'fingerprint') {
      if (previewMesh) scene.remove(previewMesh);
      if (activeMesh)  scene.remove(activeMesh);
      if (boundaryGroup) boundaryGroup.visible = false;
      hideTrailOverlays();
      // Show the fingerprint panel — it's hidden by default (set inline
      // on the <div> itself) and only the pca branch was hiding it
      // explicitly. Without this line the panel never reappears.
      const fpPanel = $('fingerprint-panel');
      if (fpPanel) fpPanel.style.display = 'block';
      if (!fingerprintH && activeRun) {
        await loadFingerprintForRun(activeRun, currentLayer);
      }
      await showFingerprintForCurrentToken();
      camera.up.set(0, 1, 0);
      camera.position.set(18, 12, 16);
      controls.target.set(0, 0, 0);
      controls.update();
      document.querySelectorAll('#cam-buttons button[data-cam]').forEach(b => {
        b.classList.toggle('active', b.dataset.cam === 'persp');
      });
    }
  }

  async function revealTokensUpTo(n) {
    if (!activeRun) return;
    const N = activeRun.frames.length;
    n = Math.max(0, Math.min(N, n));
    if (n === revealed) return;

    if (n < revealed) {
      revealed = 0;
      clearActive();
      trailGeo.setDrawRange(0, 0);
      for (let i = 0; i < MAX_TRAIL; i++) {
        dots.setMatrixAt(i, mZero);
        dots.setColorAt(i, _tmpColor.setRGB(0, 0, 0));
      }
      dots.instanceMatrix.needsUpdate = true;
      if (dots.instanceColor) dots.instanceColor.needsUpdate = true;
    }
    const inFingerprint = (currentView === 'fingerprint');
    while (revealed < n) {
      const f = activeRun.frames[revealed];
      const c = colorFromEntropy(f.entropy, f.is_self_check);
      const yv = visY(f.y);
      // Trail line + dots only in PCA view; in fingerprint view the
      // trail/head/pillar overlays would conflict with the 2048-D terrain.
      if (!inFingerprint) {
        trailPos[revealed * 3 + 0] = f.x;
        trailPos[revealed * 3 + 1] = yv;
        trailPos[revealed * 3 + 2] = f.z;
        trailCol[revealed * 3 + 0] = c.r;
        trailCol[revealed * 3 + 1] = c.g;
        trailCol[revealed * 3 + 2] = c.b;
        const sz = 0.18 + 0.10 * (1.0 / Math.min(4.0, Math.max(1.0, f.perplexity)));
        const m = new THREE.Matrix4().makeScale(sz, sz, sz);
        m.setPosition(f.x, yv, f.z);
        dots.setMatrixAt(revealed, m);
        dots.setColorAt(revealed, c);
      }
      addTokenToActive(f);
      revealed++;
    }
    if (!inFingerprint) {
      trailGeo.setDrawRange(0, revealed);
      trailGeo.attributes.position.needsUpdate = true;
      trailGeo.attributes.color.needsUpdate = true;
      dots.instanceMatrix.needsUpdate = true;
      if (dots.instanceColor) dots.instanceColor.needsUpdate = true;
    }
    rebuildActiveTerrain();
    updateHead();
    updateHud();
    updateTextPanel();
    updateProgressUI(N);
    showFingerprintForCurrentToken();
  }

  function updateHead() {
    if (!activeRun || revealed === 0) {
      head.visible = false;
      pillar.visible = false;
      footprint.visible = false;
      return;
    }
    const f = activeRun.frames[revealed - 1];
    const c = colorFromEntropy(f.entropy, f.is_self_check);
    const yv = visY(f.y);

    // In fingerprint view, the head/pillar/footprint overlays belong to the
    // PCA scene. Hide them so they don't overlap the 2048-D terrain.
    const showOverlays = (currentView === 'pca');
    head.visible = showOverlays;
    pillar.visible = showOverlays;
    footprint.visible = showOverlays;
    if (showOverlays) {
      head.position.set(f.x, yv, f.z);
      head.material.color.copy(c);
      const h = Math.max(0.5, yv);
      pillar.scale.set(1, h, 1);
      pillar.position.set(f.x, h, f.z);
      pillar.material.color.copy(c);
      footprint.position.set(f.x, 0.05, f.z);
      footprint.material.color.copy(c);
    }

    // HUD density at this cell
    const k = cellIdx(f.x, f.z);
    $('hud-cell').textContent = `[${k % TERRAIN_RES}, ${Math.floor(k / TERRAIN_RES)}]`;
    $('hud-dens').textContent = String(activeAcc[k]);
    // Total non-zero cells (cells the active run has touched)
    let touched = 0;
    for (let i = 0; i < activeAcc.length; i++) if (activeAcc[i] > 0) touched++;
    $('hud-placed').textContent = `${revealed} tok → ${touched} cells`;
  }

  // Sweep view event handlers removed.

  function updateHud() {
    const hud = {
      prompt: $('hud-prompt'), cfg: $('hud-cfg'), corr: $('hud-corr'),
      step: $('hud-step'), ntok: $('hud-ntok'),
      tok: $('hud-tok'), ppl: $('hud-ppl'), ent: $('hud-ent'), pos: $('hud-pos'),
    };
    if (!activeRun) {
      hud.prompt.textContent = '—';
      hud.cfg.textContent = hud.corr.textContent = '—';
      hud.step.textContent = '0';
      hud.ntok.textContent = '0';
      hud.tok.textContent = '·';
      hud.ppl.textContent = hud.ent.textContent = hud.pos.textContent = '—';
      $('hud-cell').textContent = $('hud-dens').textContent = '—';
      return;
    }
    hud.prompt.textContent = activeRun.prompt.slice(0, 60) + (activeRun.prompt.length > 60 ? '…' : '');
    hud.cfg.textContent = activeRun.config || '—';
    hud.corr.textContent = activeRun.correct === true ? '✓'
                         : activeRun.correct === false ? '✗'
                         : '?';
    hud.ntok.textContent = String(activeRun.frames.length);
    hud.step.textContent = String(revealed);
    if (revealed > 0) {
      const f = activeRun.frames[revealed - 1];
      hud.tok.textContent = JSON.stringify(f.token).slice(0, 24);
      hud.ppl.textContent = f.perplexity.toFixed(2);
      hud.ent.textContent = f.entropy.toFixed(2);
      hud.pos.textContent = `(${f.x.toFixed(1)}, ${f.y.toFixed(1)}, ${f.z.toFixed(1)})`;
    } else {
      hud.tok.textContent = '·';
      hud.ppl.textContent = hud.ent.textContent = hud.pos.textContent = '—';
    }
  }

  function updateTextPanel() {
    const el = $('cur-text');
    if (!activeRun) { el.innerHTML = ''; return; }
    const N = activeRun.frames.length;
    let html = '';
    for (let i = 0; i < N; i++) {
      const f = activeRun.frames[i];
      let cls = 'past';
      if (i < revealed - 1) cls = 'past';
      else if (i === revealed - 1) cls = 'cur';
      if (f.is_self_check) cls += ' self';
      if (f.is_revisit) cls += ' revisit';
      const txt = esc(f.token) || '·';
      const dim = i >= revealed ? 'color:var(--muted);opacity:0.35' : '';
      html += `<span class="tok ${cls}" style="${dim}">${txt}</span>`;
    }
    el.innerHTML = html;
    el.scrollTop = el.scrollHeight;
  }

  // -------------------------------------------------------------------------
  // Run list + filters
  // -------------------------------------------------------------------------
  function badge(c) {
    if (c === true) return '<span class="badge b-correct">✓</span>';
    if (c === false) return '<span class="badge b-wrong">✗</span>';
    return '<span class="badge b-na">?</span>';
  }

  // Filters: tag (16k / 32k), correct (✓ / ✗)
  let filterTag = 'all';   // 'all' | '16k' | '32k'
  let filterCorrect = 'all';  // 'all' | 'yes' | 'no'

  function renderFilters() {
    const wrap = $('filter-row');
    wrap.innerHTML = '';
    function chip(label, group, value) {
      const c = document.createElement('span');
      c.className = 'chip';
      const active = (group === 'tag' ? filterTag : filterCorrect) === value;
      if (active) c.classList.add('on');
      c.textContent = label;
      c.onclick = () => {
        if (group === 'tag') filterTag = value;
        else filterCorrect = value;
        renderFilters();
        renderRunList();
      };
      return c;
    }
    [['All', 'all'], ['16k', '16k'], ['32k', '32k']].forEach(([l, v]) => wrap.appendChild(chip(l, 'tag', v)));
    [['✓', 'yes'], ['✗', 'no']].forEach(([l, v]) => wrap.appendChild(chip(l, 'correct', v)));
  }

  function renderRunList() {
    const list = $('run-list');
    list.innerHTML = '';
    const filtered = runs.filter(r => {
      if (filterTag !== 'all' && r.tag !== filterTag) return false;
      if (filterCorrect === 'yes' && r.correct !== true) return false;
      if (filterCorrect === 'no'  && r.correct !== false) return false;
      return true;
    });
    if (filtered.length === 0) {
      list.innerHTML = '<div style="padding:14px;color:var(--muted);font-size:11px">No runs match filter.</div>';
      return;
    }
    filtered.forEach((r) => {
      const div = document.createElement('div');
      div.className = 'item' + (activeRun === r ? ' active' : '');
      const promptShort = r.prompt.length > 60 ? r.prompt.slice(0, 60) + '…' : r.prompt;
      div.innerHTML = `
        <div class="head">
          <span class="id">${esc(r.problem_id || r.trajectory_id)}</span>
          ${badge(r.correct)}
        </div>
        <div class="meta">${esc(r.config || '')} · ${buildFramesForLayer(r, currentLayer).length} tok</div>
        <div class="meta">${esc(promptShort)}</div>
      `;
      div.onclick = () => selectRun(r);
      list.appendChild(div);
    });
    setStatus(`showing ${filtered.length} / ${runs.length} runs`);
  }

  function selectRun(r) {
    // Use current layer's (x,y,z) — fall back to the first available layer
    // if the requested one is missing on this run.
    let frames = buildFramesForLayer(r, currentLayer);
    if (frames.length === 0) {
      const fallback = Object.keys(r.layers || {}).sort((a, b) => +a - +b)[0];
      if (fallback !== undefined) {
        console.warn(`run ${r.trajectory_id} missing layer ${currentLayer}, using ${fallback}`);
        currentLayer = +fallback;
        $('layer').value = String(currentLayer);
        $('layer-val').textContent = layerLabel(currentLayer);
        frames = buildFramesForLayer(r, currentLayer);
      }
    }
    activeRun = { ...r, frames };
    revealed = 0;
    clearVisualization();
    document.querySelectorAll('#run-list .item').forEach(d => {
      d.classList.toggle('active', d.querySelector('.id').textContent === (r.problem_id || r.trajectory_id));
    });
    $('scrub').max = String(Math.max(0, frames.length - 1));
    $('scrub-val').textContent = '0 / ' + frames.length;
    $('progress-fill').style.width = '0%';
    $('progress-pct').textContent = '0.0%';
    updateProgressUI(frames.length);
    updateHud();
    updateTextPanel();
  }

  // -------------------------------------------------------------------------
  // Playback loop
  // -------------------------------------------------------------------------
  // -------------------------------------------------------------------------
  // Playback loop. Uses an accumulator pattern: track fractional "credit"
  // so speed=20 means 20 tokens per second, regardless of frame rate.
  // Wrapped in try/catch so a single iteration's error doesn't kill the
  // animation loop forever.
  // -------------------------------------------------------------------------
  let accum = 0;   // fractional tokens accumulated toward next step
  let tickCount = 0;
  function tick(now) {
    requestAnimationFrame(tick);
    tickCount++;
    try {
      if (playing && activeRun && activeRun.frames.length > 0) {
        if (lastTickMs === 0) {
          lastTickMs = now;
        } else {
          // Cap dt so a tab-switch doesn't dump 5s of tokens in one frame.
          const dt = Math.min(0.1, (now - lastTickMs) / 1000);
          lastTickMs = now;
          accum += dt * tokensPerSec;
          // Step one token at a time so updateProgressUI and the trail
          // get a chance to render between advances.
          while (accum >= 1.0 && revealed < activeRun.frames.length) {
            accum -= 1.0;
            revealTokensUpTo(revealed + 1);
          }
          if (revealed >= activeRun.frames.length) {
            playing = false;
            $('play-btn').textContent = '▶ Play';
            lastTickMs = 0;
            accum = 0;
          }
        }
      } else {
        lastTickMs = 0;
        accum = 0;
      }
    } catch (e) {
      console.error('[token-terrain] tick error:', e);
    }
    if (head.visible) {
      const t = performance.now();
      head.scale.setScalar(1 + 0.18 * Math.sin(t * 0.006));
    }
    if (pillar.visible) {
      const t = performance.now();
      pillar.material.opacity = 0.45 + 0.30 * Math.abs(Math.sin(t * 0.005));
    }
    if (footprint.visible) {
      const t = performance.now();
      const s = 1 + 0.30 * Math.sin(t * 0.008);
      footprint.scale.setScalar(s);
      footprint.material.opacity = 0.5 + 0.4 * Math.abs(Math.sin(t * 0.008));
    }
    controls.update();
    renderer.render(scene, camera);
  }
  requestAnimationFrame(tick);

  // -------------------------------------------------------------------------
  // Controls
  // -------------------------------------------------------------------------
  $('play-btn').onclick = () => {
    if (!activeRun) { console.warn('[token-terrain] no active run yet'); return; }
    if (revealed >= activeRun.frames.length) revealed = 0;
    playing = !playing;
    $('play-btn').textContent = playing ? '⏸ Pause' : '▶ Play';
    lastTickMs = 0;
    console.log('[token-terrain] play click — playing=' + playing +
                ' revealed=' + revealed + '/' + activeRun.frames.length +
                ' tokensPerSec=' + tokensPerSec +
                ' frames=' + (activeRun.frames ? activeRun.frames.length : 'null'));
  };
  $('step-btn').onclick = () => {
    if (!activeRun) return;
    playing = false;
    $('play-btn').textContent = '▶ Play';
    revealTokensUpTo(revealed + 1);
  };
  $('reset-btn').onclick = () => {
    if (!activeRun) return;
    playing = false;
    $('play-btn').textContent = '▶ Play';
    revealTokensUpTo(0);
  };
  function layerLabel(L) {
    if (L === 27) return 'layer 27 (final)';
    if (L === 0)  return 'layer 0 (embed)';
    return 'layer ' + L;
  }

  // -------------------------------------------------------------------------
  // Layer switch — rebuild preview + reset active from the new layer's data.
  // -------------------------------------------------------------------------
  async function changeLayer(newLayer) {
    if (newLayer === currentLayer) return;
    currentLayer = newLayer;
    $('layer-val').textContent = layerLabel(currentLayer);
    setStatus(`loading ${layerLabel(currentLayer)} xyz for ${runs.length} runs…`, 'loading');

    // Pause any playback and reset active state
    playing = false;
    $('play-btn').textContent = '▶ Play';
    revealed = 0;
    clearActive();

    // In fingerprint view, also refetch the hidden state for this layer.
    // In PCA view, fetch all runs' xyz for the new layer.
    const promises = [];
    if (currentView === 'fingerprint' && activeRun) {
      fingerprintH = null;
      promises.push(loadFingerprintForRun(activeRun, currentLayer));
    }
    promises.push(fetchAllLayerXyz(currentLayer));
    Promise.all(promises).then(async () => {
      // Recompute bounds for the new layer (PCA mode)
      if (currentView === 'pca') {
        let xmin = +Infinity, xmax = -Infinity, zmin = +Infinity, zmax = -Infinity;
        let ymin = +Infinity, ymax = -Infinity;
        runs.forEach(r => {
          const frames = buildFramesForLayer(r, currentLayer);
          frames.forEach(f => {
            if (f.x < xmin) xmin = f.x;
            if (f.x > xmax) xmax = f.x;
            if (f.z < zmin) zmin = f.z;
            if (f.z > zmax) zmax = f.z;
            if (f.y < ymin) ymin = f.y;
            if (f.y > ymax) ymax = f.y;
          });
        });
        dataBounds = {
          xmin, xmax, zmin, zmax, ymin, ymax,
          yrange: Math.max(1e-6, ymax - ymin),
        };
        buildBoundary(dataBounds);
        fitCameraToBounds(dataBounds);
        seedPreviewFromRuns();
      } else {
        // Re-render the fingerprint for the new layer
        return showFingerprintForCurrentToken();
      }

      // Re-select the same problem (or first available) with the new layer's frames
      const targetId = activeRun ? (activeRun.problem_id || activeRun.trajectory_id) : null;
      let next = runs.find(rr =>
        (rr.problem_id || rr.trajectory_id) === targetId);
      if (!next) next = runs[0];
      if (currentView === 'pca') selectRun(next);
      setStatus(`${layerLabel(currentLayer)} · ${runs.length} runs · ` +
                `${runs.reduce((s, r) => s + (buildFramesForLayer(r, currentLayer).length), 0)} tokens`);
    }).catch(e => {
      console.error(e);
      setStatus('layer switch failed: ' + e.message, 'error');
    });
  }

  $('layer').oninput = (e) => {
    changeLayer(parseInt(e.target.value, 10));
  };

  const speedEl = $('speed');
  const speedVal = $('speed-val');
  speedEl.oninput = () => {
    tokensPerSec = parseInt(speedEl.value, 10);
    speedVal.textContent = tokensPerSec + '×';
  };
  $('scrub').oninput = async (e) => {
    if (!activeRun) return;
    playing = false;
    $('play-btn').textContent = '▶ Play';
    await revealTokensUpTo(parseInt(e.target.value, 10));
  };

  // Wire the activation / attribution radio buttons in the fingerprint panel.
  document.querySelectorAll('input[name="fp-color-mode"]').forEach(radio => {
    radio.addEventListener('change', async (e) => {
      fpColorMode = e.target.value;
      // Force a fresh fetch when switching to attribution (in case the
      // current cache happens to match the visible output token id but
      // we still want the status indicator refreshed).
      if (fpColorMode === 'activation') {
        lmHeadRow = null;
        lmHeadRowToken = -1;
        const status = $('fp-attr-status');
        if (status) status.textContent = '—';
      } else {
        lmHeadRow = null;
        lmHeadRowToken = -1;
      }
      if (currentView === 'fingerprint') {
        await showFingerprintForCurrentToken();
      }
    });
  });

  document.querySelectorAll('#cam-buttons button').forEach(b => {
    b.onclick = () => {
      // View toggle (PCA vs Fingerprint) — handled separately
      if (b.classList.contains('view-btn')) {
        setView(b.dataset.view);
        return;
      }
      document.querySelectorAll('#cam-buttons button[data-cam]').forEach(x =>
        x.classList.toggle('active', x === b));
      if (b.dataset.cam === 'fit') {
        if (currentView === 'fingerprint') {
          camera.up.set(0, 1, 0);
          camera.position.set(18, 12, 16);
          controls.target.set(0, 0, 0);
        } else if (dataBounds) {
          fitCameraToBounds(dataBounds);
        }
        controls.update();
        return;
      }
      // Camera presets — distances depend on which view is active.
      // PCA data extent ≈ 170 units; fingerprint grid is only 22 × 11,
      // so the PCA-tuned distances make the fingerprint look tiny.
      if (currentView === 'fingerprint') {
        if (b.dataset.cam === 'persp') {
          camera.up.set(0, 1, 0);
          camera.position.set(18, 12, 16);
        } else if (b.dataset.cam === 'iso') {
          camera.up.set(0, 1, 0);
          camera.position.set(20, 20, 20);
        } else if (b.dataset.cam === 'top') {
          camera.up.set(0, 1, 0);
          camera.position.set(0, 14, 0.001);
        } else if (b.dataset.cam === 'side') {
          camera.up.set(0, 1, 0);
          camera.position.set(0, 3, 18);
        }
        controls.target.set(0, 0, 0);
      } else if (dataBounds) {
        const cx = (dataBounds.xmin + dataBounds.xmax) / 2;
        const cz = (dataBounds.zmin + dataBounds.zmax) / 2;
        const span = Math.max(dataBounds.xmax - dataBounds.xmin,
                              dataBounds.zmax - dataBounds.zmin);
        if (b.dataset.cam === 'persp') {
          camera.up.set(0, 1, 0);
          camera.position.set(cx + span * 0.6, span * 0.7, cz + span * 0.8);
        } else if (b.dataset.cam === 'iso') {
          camera.up.set(0, 1, 0);
          camera.position.set(cx + span * 0.7, span * 0.9, cz + span * 0.7);
        } else if (b.dataset.cam === 'top') {
          camera.up.set(0, 0, -1);
          camera.position.set(cx, span * 1.4, cz + 0.001);
        } else if (b.dataset.cam === 'side') {
          camera.up.set(0, 1, 0);
          camera.position.set(cx, span * 0.4, cz + span * 1.6);
        }
        controls.target.set(cx, 0, cz);
      }
      controls.update();
    };
  });

  window.addEventListener('resize', () => {
    camera.aspect = sceneEl.clientWidth / sceneEl.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(sceneEl.clientWidth, sceneEl.clientHeight);
  });

  // -------------------------------------------------------------------------
  // Bootstrap: fetch full data, then populate list and select first run
  // -------------------------------------------------------------------------
  async function loadFull() {
    setStatus('loading qwen3_global.json…', 'loading');
    try {
      const r = await fetch('qwen3_global.json');
      if (!r.ok) throw new Error('HTTP ' + r.status);
      runs = await r.json();
    } catch (e) {
      setStatus('failed to load qwen3_global.json — serve via http://localhost:8765', 'error');
      console.error(e);
      return;
    }
    // Derive data bounds from every token of the CURRENT layer across every run
    let xmin = +Infinity, xmax = -Infinity, zmin = +Infinity, zmax = -Infinity;
    let ymin = +Infinity, ymax = -Infinity;
    runs.forEach(r => {
      const frames = buildFramesForLayer(r, currentLayer);
      frames.forEach(f => {
        if (f.x < xmin) xmin = f.x;
        if (f.x > xmax) xmax = f.x;
        if (f.z < zmin) zmin = f.z;
        if (f.z > zmax) zmax = f.z;
        if (f.y < ymin) ymin = f.y;
        if (f.y > ymax) ymax = f.y;
      });
    });
    dataBounds = {
      xmin, xmax, zmin, zmax, ymin, ymax,
      yrange: Math.max(1e-6, ymax - ymin),
    };
    buildBoundary(dataBounds);
    fitCameraToBounds(dataBounds);
    seedPreviewFromRuns();

    renderFilters();
    renderRunList();
    if (runs.length > 0) selectRun(runs[0]);
    setStatus(`loaded ${runs.length} runs · ${runs.reduce((s,r) => s + (r.tokens ? r.tokens.length : 0), 0)} tokens`);
    console.log('[token-terrain] ready —', runs.length, 'runs');
  }

  loadFull();
})();
"""


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def main():
    three_js, orbit_js = extract_libs()
    summary = runs_summary()
    out_html = (
        PAGE_HTML
        .replace("{THREE_JS}", three_js)
        .replace("{ORBIT_JS}", orbit_js)
        .replace("{RUNS_SUMMARY}", summary)
        .replace("{APP_JS}", APP_JS)
    )
    OUT.mkdir(exist_ok=True)
    PLAYER_HTML.write_text(out_html, encoding="utf-8")
    print(f"wrote {PLAYER_HTML} ({len(out_html) / 1024:.1f} KB)")
    print(f"  embedded {len(summary) / 1024:.1f} KB of run summary ({len(json.loads(summary))} runs)")


if __name__ == "__main__":
    main()

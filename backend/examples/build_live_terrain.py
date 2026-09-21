"""Generate a LIVE 3-D terrain viewer that streams hidden states from
the FastAPI WebSocket backend.

This is the *hybrid* version: on page load it shows 8 saved Qwen3-1.7B
runs as the static background context (so you see immediate visual
content), then connects to the WebSocket and renders any new live
trajectories as bright overlays on top of the saved ones. The terrain
density incorporates both saved and live data.

Why hybrid vs pure-live:
  * pure-live opened to an empty void and lost the visual richness
    of the original static replay
  * pure-static never updated during reasoning
  * hybrid gives immediate context AND live updates

The server is expected to be running locally (e.g. via
`backend/examples/demo_synthetic.py` or `run_global.py`).

Run:
    python build_live_terrain.py
→ writes backend/examples/output/live_terrain.html
"""

from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
STATIC_HTML = OUT / "view_terrain.html"
LIVE_HTML = OUT / "live_terrain.html"
SAVED_RUNS_JSON = OUT / "qwen3_global.json"


# ---------------------------------------------------------------------------
# Reuse three.js + OrbitControls from the existing static HTML
# ---------------------------------------------------------------------------

def extract_libs() -> tuple[str, str]:
    text = STATIC_HTML.read_text()
    blocks = re.findall(r"<script>\s*(.*?)\s*</script>", text, re.DOTALL)
    if len(blocks) < 2:
        raise RuntimeError("Couldn't extract three.js / OrbitControls from view_terrain.html")
    three_js = blocks[0]
    orbit_js = blocks[1]
    if "THREE" not in three_js or "OrbitControls" not in orbit_js:
        raise RuntimeError("Library extraction looks wrong — block order may have changed.")
    return three_js, orbit_js


def load_saved_runs() -> str:
    """Read qwen3_global.json and return it as a minified JSON string
    suitable for inlining into the page."""
    if not SAVED_RUNS_JSON.exists():
        print(f"  warning: {SAVED_RUNS_JSON} not found; live viewer will start empty")
        return "[]"
    with open(SAVED_RUNS_JSON) as f:
        data = json.load(f)
    # We only need (x, y, z, tag, correct, kind, prompt, tokens) for the
    # historical context. Strip out the heavy `frames` arrays to keep
    # the inline payload small.
    stripped = []
    for run in data:
        stripped.append({
            "tag": run.get("tag"),
            "correct": run.get("correct"),
            "kind": run.get("kind"),
            "prompt": run.get("prompt"),
            "expected": run.get("expected", ""),
            "generated_text": (run.get("generated_text") or "")[:200],
            "pts": [[f["x"], f["y"], f["z"]] for f in run.get("frames", []) if f.get("token")],
            "ppl": [f.get("perplexity") or 1.0 for f in run.get("frames", []) if f.get("token")],
            "ent": [f.get("entropy") or 0.0 for f in run.get("frames", []) if f.get("token")],
            "tok": [f["token"] for f in run.get("frames", []) if f.get("token")],
        })
    return json.dumps(stripped, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

PAGE_HTML = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8" />
<title>Qwen3-1.7B Reasoning3D · Live</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  :root {
    --bg:#0a0d12; --panel:#131820; --border:#1f2630;
    --text:#d6dde7; --muted:#7e8694; --accent:#5cb6ff;
    --ok:#22c55e; --warn:#f97316; --err:#ef4444;
  }
  * { box-sizing:border-box; }
  html, body {{ margin:0; padding:0; height:100%; background:var(--bg);
    color:var(--text); font-family:-apple-system,"Segoe UI",Roboto,sans-serif;
    overflow:hidden; }}
  #app {{ display:grid; grid-template-columns:1fr 380px; height:100vh; }}
  #scene-wrap {{ position:relative; min-width:0; }}
  #scene {{ width:100%; height:100%; cursor:grab; }}
  #scene:active {{ cursor:grabbing; }}
  #status {{
    position:absolute; top:16px; left:16px;
    background:rgba(19,24,32,.92); border:1px solid var(--border);
    border-radius:8px; padding:8px 14px; font-size:12px;
    font-family:ui-monospace,Menlo,monospace;
    display:flex; gap:10px; align-items:center;
  }}
  #status .dot {{ width:10px; height:10px; border-radius:50%;
    background:var(--muted); transition:background .2s; }}
  #status.connected .dot {{ background:var(--ok); box-shadow:0 0 8px var(--ok); }}
  #status.connecting .dot {{ background:var(--warn); animation:pulse 1s infinite; }}
  #status.error .dot {{ background:var(--err); }}
  @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:.3}} }}
  #cam-buttons {{
    position:absolute; top:16px; right:16px;
    display:flex; gap:6px; background:rgba(19,24,32,.85);
    border:1px solid var(--border); border-radius:8px; padding:6px;
    font-family:ui-monospace,Menlo,monospace;
  }}
  #cam-buttons button {{
    background:transparent; color:var(--text); border:1px solid var(--border);
    padding:5px 10px; border-radius:5px; font-size:11px; cursor:pointer;
  }}
  #cam-buttons button.active {{
    background:var(--accent); color:#001a2c; border-color:var(--accent);
  }}
  #legend {{
    position:absolute; left:16px; bottom:16px;
    background:rgba(19,24,32,.92); border:1px solid var(--border);
    border-radius:10px; padding:12px 14px; font-size:11px;
    line-height:1.7; font-family:ui-monospace,Menlo,monospace;
    pointer-events:none;
  }}
  #legend b {{ color:var(--accent); }}
  aside {{
    background:var(--panel); border-left:1px solid var(--border);
    display:flex; flex-direction:column; min-height:0;
  }}
  .controls {{ padding:14px; border-bottom:1px solid var(--border); }}
  .controls h2 {{ font-size:11px; font-weight:600; color:var(--muted);
    letter-spacing:.08em; text-transform:uppercase; margin:0 0 10px; }}
  .row-c {{ display:flex; align-items:center; gap:8px; margin-bottom:8px; }}
  .row-c label {{ font-size:11px; color:var(--muted); min-width:64px; }}
  input, textarea {{
    background:#0a0e15; color:var(--text); border:1px solid var(--border);
    border-radius:5px; padding:6px 10px; font-size:12px; font-family:inherit;
    width:100%;
  }}
  textarea {{ resize:vertical; min-height:54px; max-height:160px;
    font-family:ui-monospace,Menlo,monospace; }}
  input:focus, textarea:focus {{ outline:none; border-color:var(--accent); }}
  button {{
    background:var(--accent); color:#001a2c; border:0; padding:7px 14px;
    border-radius:6px; font-weight:600; font-size:12px; cursor:pointer;
    font-family:inherit;
  }}
  button.ghost {{ background:transparent; color:var(--text); border:1px solid var(--border); }}
  button:disabled {{ opacity:.5; cursor:not-allowed; }}
  #hud {{ padding:10px 14px; border-bottom:1px solid var(--border);
    font-family:ui-monospace,Menlo,monospace; font-size:11px; line-height:1.7; }}
  #hud .stat {{ color:var(--muted); }}
  #hud .val {{ color:var(--text); font-weight:600; }}
  #hud .tok {{ display:inline-block; padding:1px 6px; margin-right:4px;
    background:rgba(92,182,255,.12); border-radius:4px; color:var(--accent); }}
  #live-text {{
    flex:1; min-height:0; overflow-y:auto; padding:14px;
    font-family:ui-monospace,Menlo,monospace; font-size:12px;
    line-height:1.6;
  }}
  #live-text .t {{ color:var(--text); }}
  #live-text .self {{ color:#ff9d57; font-weight:600; }}
  #live-text .revisit {{ background:rgba(168,85,247,.18); border-radius:3px; padding:0 3px; }}
  #live-text .cur {{
    background:rgba(92,182,255,.18); border-radius:3px; padding:0 3px;
    box-shadow:0 0 0 2px rgba(92,182,255,.35);
  }}
  #live-text .muted {{ color:var(--muted); }}
  #err-banner {{
    position:absolute; top:60px; left:16px; max-width:60%;
    background:var(--err); color:#fff; padding:8px 14px; border-radius:6px;
    font-size:11px; font-family:ui-monospace,Menlo,monospace;
    display:none; z-index:100; cursor:pointer;
  }}
</style>
</head>
<body>
<div id="app">
  <div id="scene-wrap">
    <canvas id="scene"></canvas>
    <div id="status"><span class="dot"></span><span id="status-text">disconnected</span></div>
    <div id="cam-buttons">
      <button data-cam="persp" class="active">Perspective</button>
      <button data-cam="iso">Isometric</button>
      <button data-cam="top">Top-Down</button>
      <button data-cam="side">Side</button>
    </div>
    <div id="legend">
      <div><b>HYBRID VIEW</b></div>
      <div style="margin:4px 0;font-size:10px;color:var(--muted)">
        历史 8 个 run 作背景 · 实时推理作亮层
      </div>
      <div style="margin-top:6px"><b>HISTORICAL (淡色)</b></div>
      <div>· 绿色 = easy ✓</div>
      <div>· 橙色 = easy ✗</div>
      <div>· 红色 = hard ✗</div>
      <div>· 蓝色 = hard ✓ (rare)</div>
      <div style="margin-top:6px"><b>LIVE (明亮)</b></div>
      <div>· 暖色 ribbon = 实时推理路径</div>
      <div>· 蓝白脉冲球 + 蓝色光圈 = 当前 token</div>
      <div>· 橙色 = self-check · 紫色 = revisit</div>
      <div style="margin-top:6px"><b>TERRAIN</b></div>
      <div>累积密度 + entropy 着色</div>
    </div>
    <div id="err-banner" onclick="this.style.display='none'">click to dismiss</div>
  </div>
  <aside>
    <div class="controls">
      <h2>Connection</h2>
      <div class="row-c">
        <label>ws://</label>
        <input id="ws-url" value="localhost:8765" />
      </div>
      <div class="row-c" style="gap:6px">
        <button id="connect-btn" style="flex:1">Connect</button>
        <button class="ghost" id="disconnect-btn" style="flex:1" disabled>Disconnect</button>
      </div>
    </div>

    <div class="controls">
      <h2>Inference</h2>
      <div class="row-c" style="flex-direction:column; align-items:stretch; gap:4px">
        <label style="min-width:0">Prompt</label>
        <textarea id="prompt" placeholder="What is the capital of France?">What is the capital of France? Answer with one word.</textarea>
      </div>
      <div class="row-c">
        <label>Layer</label>
        <input id="layer" type="number" value="14" min="0" max="40" style="width:80px" />
      </div>
      <div class="row-c" style="gap:6px">
        <button id="run-btn" disabled style="flex:1">▶ Run</button>
        <button class="ghost" id="stop-btn" disabled style="flex:1">⏹ Stop</button>
      </div>
    </div>

    <div id="hud">
      <div><span class="stat">prompt: </span><span id="hud-prompt" class="val">—</span></div>
      <div><span class="stat">step:    </span><span id="hud-step" class="val">0</span></div>
      <div><span class="stat">token:   </span><span id="hud-tok" class="tok">·</span></div>
      <div><span class="stat">ppl:     </span><span id="hud-ppl" class="val">—</span>
        · <span class="stat">ent: </span><span id="hud-ent" class="val">—</span></div>
      <div><span class="stat">frames:  </span><span id="hud-frames" class="val">0</span>
        · <span class="stat">pos: </span><span id="hud-pos" class="val">—</span></div>
    </div>

    <div id="live-text">
      <span class="muted">Connect to backend, then ▶ Run to stream reasoning.</span>
    </div>
  </aside>
</div>

<script>
{THREE_JS}
</script>
<script>
{ORBIT_JS}
</script>
<script id="saved-runs" type="application/json">
{SAVED_RUNS_JSON}
</script>
<script>
{APP_JS}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Application JavaScript (lives in the generated HTML)
# ---------------------------------------------------------------------------

APP_JS = r"""
(function () {
  // ===========================================================================
  // 0. Utilities
  // ===========================================================================
  const $ = id => document.getElementById(id);
  const errBanner = $('err-banner');
  function showError(msg) {
    console.error(msg);
    errBanner.textContent = msg;
    errBanner.style.display = 'block';
    setTimeout(() => { errBanner.style.display = 'none'; }, 8000);
  }
  window.addEventListener('error', e => showError('JS error: ' + e.message));
  window.addEventListener('unhandledrejection', e => showError('Promise: ' + e.reason));

  function esc(s) {
    return (s || '').replace(/[&<>"']/g, c => (
      {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]
    ));
  }

  // ===========================================================================
  // 0.5. Saved runs (historical context) — read from <script id="saved-runs">
  // ===========================================================================
  const savedRuns = (() => {
    const el = document.getElementById('saved-runs');
    if (!el) return [];
    try { return JSON.parse(el.textContent); } catch (e) { return []; }
  })();

  // Color mapping matching the static view_terrain.html legend:
  //   easy + correct  → green
  //   easy + wrong    → orange
  //   hard + wrong    → red
  //   hard + correct  → blue (rare)
  function historicalColor(run) {
    if (run.tag === 'easy' && run.correct) return { line: 0x34c759, glow: 0x6dfaa3 };
    if (run.tag === 'easy' && !run.correct) return { line: 0xff9f0a, glow: 0xffc97a };
    if (run.tag === 'hard' && run.correct) return { line: 0x5e9cff, glow: 0x9cc4ff };
    return { line: 0xff453a, glow: 0xff7a72 };
  }

  // ===========================================================================
  // 1. Three.js scene
  // ===========================================================================
  const sceneEl = $('scene');
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0d12);
  scene.fog = new THREE.Fog(0x0a0d12, 25, 70);

  const camera = new THREE.PerspectiveCamera(50, sceneEl.clientWidth / sceneEl.clientHeight, 0.1, 200);
  camera.position.set(22, 18, 28);

  const renderer = new THREE.WebGLRenderer({ canvas: sceneEl, antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setSize(sceneEl.clientWidth, sceneEl.clientHeight);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 5;
  controls.maxDistance = 80;
  controls.target.set(0, 1.5, 0);

  // ----- Lighting -----------------------------------------------------------
  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const dir1 = new THREE.DirectionalLight(0xffffff, 0.5);
  dir1.position.set(12, 18, 8);
  scene.add(dir1);
  const dir2 = new THREE.DirectionalLight(0x6090ff, 0.25);
  dir2.position.set(-10, 6, -8);
  scene.add(dir2);

  // ----- Reference grid (always visible, gives spatial context) ------------
  const grid = new THREE.GridHelper(20, 20, 0x1f2630, 0x161a22);
  scene.add(grid);

  // Shadow disc
  const shadow = new THREE.Mesh(
    new THREE.CircleGeometry(18, 64),
    new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.4 })
  );
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.y = -0.05;
  scene.add(shadow);

  // Axes triad
  const axesGroup = new THREE.Group();
  function axisCone(color, x, y, z, rot) {
    const m = new THREE.Mesh(
      new THREE.ConeGeometry(0.05, 0.22, 8),
      new THREE.MeshBasicMaterial({ color })
    );
    m.position.set(x, y, z);
    if (rot) m.rotation.set(rot[0], rot[1], rot[2]);
    axesGroup.add(m);
  }
  axisCone(0xff5555, 0.6, 0, 0, [0, 0, -Math.PI / 2]);
  axisCone(0x55ff55, 0, 0.6, 0, null);
  axisCone(0x5555ff, 0, 0, 0.6, [Math.PI / 2, 0, 0]);
  scene.add(axesGroup);

  // ===========================================================================
  // 2. Dynamic terrain (built from accumulated points)
  // ===========================================================================
  // The terrain is a 2D density map in the (x, z) plane. Each cell counts how
  // many trajectory points have landed near it, weighted by entropy. As frames
  // stream in, the terrain emerges — exactly what they expected.
  const TERRAIN_RES = 60;        // grid resolution
  const TERRAIN_SIZE = 24;       // grid extends ±12 from origin
  let terrainAcc = new Float32Array(TERRAIN_RES * TERRAIN_RES);  // density
  let terrainEnt = new Float32Array(TERRAIN_RES * TERRAIN_RES);  // weighted entropy
  let terrainGeo = null;
  let terrainMesh = null;

  function cellIdx(x, z) {
    // Map x,z ∈ [-SIZE/2, SIZE/2] → grid indices
    const u = (x + TERRAIN_SIZE / 2) / TERRAIN_SIZE;
    const v = (z + TERRAIN_SIZE / 2) / TERRAIN_SIZE;
    const i = Math.max(0, Math.min(TERRAIN_RES - 1, Math.floor(u * TERRAIN_RES)));
    const j = Math.max(0, Math.min(TERRAIN_RES - 1, Math.floor(v * TERRAIN_RES)));
    return j * TERRAIN_RES + i;
  }

  function rebuildTerrainMesh() {
    if (terrainMesh) {
      scene.remove(terrainMesh);
      terrainMesh.geometry.dispose();
      terrainMesh.material.dispose();
    }
    const positions = new Float32Array(TERRAIN_RES * TERRAIN_RES * 3);
    const colors = new Float32Array(TERRAIN_RES * TERRAIN_RES * 3);
    const indices = [];

    let maxDensity = 0;
    for (let k = 0; k < TERRAIN_RES * TERRAIN_RES; k++) {
      if (terrainAcc[k] > maxDensity) maxDensity = terrainAcc[k];
    }
    if (maxDensity === 0) return;

    for (let j = 0; j < TERRAIN_RES; j++) {
      for (let i = 0; i < TERRAIN_RES; i++) {
        const k = j * TERRAIN_RES + i;
        const d = terrainAcc[k] / maxDensity;            // 0..1 density
        const e = terrainAcc[k] > 0 ? terrainEnt[k] / terrainAcc[k] : 0;  // avg entropy
        const h = Math.pow(d, 0.6) * 4.0;                 // height
        const x = (i / (TERRAIN_RES - 1) - 0.5) * TERRAIN_SIZE;
        const z = (j / (TERRAIN_RES - 1) - 0.5) * TERRAIN_SIZE;
        positions[k * 3 + 0] = x;
        positions[k * 3 + 1] = h;
        positions[k * 3 + 2] = z;
        // Color: blue (cool, low entropy) → red (hot, high entropy)
        const r2 = Math.min(1, e * 2);
        const g2 = Math.min(1, 1 - Math.abs(e - 0.5) * 2) * 0.7;
        const b2 = Math.min(1, (1 - e) * 2) * 0.7;
        // Darken low-density cells
        const dim = 0.2 + 0.8 * d;
        colors[k * 3 + 0] = r2 * dim;
        colors[k * 3 + 1] = g2 * dim;
        colors[k * 3 + 2] = b2 * dim;
      }
    }
    for (let j = 0; j < TERRAIN_RES - 1; j++) {
      for (let i = 0; i < TERRAIN_RES - 1; i++) {
        const a = j * TERRAIN_RES + i;
        const b = a + 1;
        const c = a + TERRAIN_RES;
        const d = c + 1;
        indices.push(a, c, b, b, c, d);
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geo.setIndex(indices);
    geo.computeVertexNormals();
    const mat = new THREE.MeshLambertMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.85,
      side: THREE.DoubleSide,
    });
    terrainGeo = geo;
    terrainMesh = new THREE.Mesh(geo, mat);
    scene.add(terrainMesh);
  }

  function addPointToTerrain(x, y, z, entropy) {
    const k = cellIdx(x, z);
    terrainAcc[k] += 1.0;
    terrainEnt[k] += entropy || 0;
  }

  function clearTerrain() {
    terrainAcc = new Float32Array(TERRAIN_RES * TERRAIN_RES);
    terrainEnt = new Float32Array(TERRAIN_RES * TERRAIN_RES);
    if (terrainMesh) {
      scene.remove(terrainMesh);
      terrainMesh.geometry.dispose();
      terrainMesh.material.dispose();
      terrainMesh = null;
    }
  }

  // ===========================================================================
  // 3. Live trajectory (growing path)
  // ===========================================================================
  const MAX_TRAIL = 1500;
  const trailPos = new Float32Array(MAX_TRAIL * 3);
  const trailCol = new Float32Array(MAX_TRAIL * 3);
  const trailGeo = new THREE.BufferGeometry();
  trailGeo.setAttribute('position', new THREE.BufferAttribute(trailPos, 3));
  trailGeo.setAttribute('color', new THREE.BufferAttribute(trailCol, 3));
  trailGeo.setDrawRange(0, 0);
  const trailMat = new THREE.LineBasicMaterial({ vertexColors: true, linewidth: 3 });
  const trailLine = new THREE.Line(trailGeo, trailMat);
  scene.add(trailLine);

  // Trail dots (small spheres at each token) — brighter and bigger than historical
  const dotGeo = new THREE.SphereGeometry(0.09, 10, 10);
  const dotMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.95 });
  const dots = new THREE.InstancedMesh(dotGeo, dotMat, MAX_TRAIL);
  dots.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  const mZero = new THREE.Matrix4().makeScale(0, 0, 0);
  for (let i = 0; i < MAX_TRAIL; i++) dots.setMatrixAt(i, mZero);
  dots.instanceMatrix.needsUpdate = true;
  scene.add(dots);

  // Head sphere (current token) — bright + glow ring
  const headGeo = new THREE.SphereGeometry(0.32, 16, 16);
  const headMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
  const head = new THREE.Mesh(headGeo, headMat);
  scene.add(head);
  head.visible = false;

  // Halo ring around the head for emphasis
  const haloGeo = new THREE.RingGeometry(0.4, 0.55, 24);
  const haloMat = new THREE.MeshBasicMaterial({
    color: 0x5cb6ff, transparent: true, opacity: 0.6, side: THREE.DoubleSide,
  });
  const halo = new THREE.Mesh(haloGeo, haloMat);
  halo.rotation.x = -Math.PI / 2;
  scene.add(halo);
  halo.visible = false;

  // ===========================================================================
  // 4. State
  // ===========================================================================
  let trail = [];   // [{x,y,z, color, token, is_self_check, ...}]
  let ws = null;
  let connected = false;
  let receivingRun = false;

  function colorFromEntropy(entropy, isSelfCheck) {
    if (isSelfCheck) return new THREE.Color(1.0, 0.6, 0.2);
    const e = Math.max(0, Math.min(1, entropy || 0.3));
    const r = Math.min(1, e * 2);
    const g = Math.min(1, 1 - Math.abs(e - 0.5) * 2);
    const b = Math.min(1, (1 - e) * 2);
    return new THREE.Color(r, g, b);
  }

  function appendTrailPoint(frame) {
    const p = frame.point;
    const color = colorFromEntropy(frame.entropy, frame.is_self_check);
    trail.push({
      x: p.x, y: p.y, z: p.z,
      r: color.r, g: color.g, b: color.b,
      token: frame.token || '',
      entropy: frame.entropy,
      perplexity: frame.perplexity,
      is_self_check: frame.is_self_check,
      is_revisit: frame.is_revisit,
    });
    // Update buffers
    const i = trail.length - 1;
    if (i >= MAX_TRAIL) return;
    trailPos[i * 3 + 0] = p.x;
    trailPos[i * 3 + 1] = p.y;
    trailPos[i * 3 + 2] = p.z;
    trailCol[i * 3 + 0] = color.r;
    trailCol[i * 3 + 1] = color.g;
    trailCol[i * 3 + 2] = color.b;
    trailGeo.attributes.position.needsUpdate = true;
    trailGeo.attributes.color.needsUpdate = true;
    trailGeo.setDrawRange(0, trail.length);

    // Dot
    const sz = 0.06 + 0.05 * (1.0 / Math.min(4.0, Math.max(1.0, frame.perplexity || 1.0)));
    const m = new THREE.Matrix4().makeScale(sz, sz, sz);
    m.setPosition(p.x, p.y, p.z);
    dots.setMatrixAt(i, m);
    dots.instanceMatrix.needsUpdate = true;

    // Head
    head.position.set(p.x, p.y, p.z);
    head.material.color.copy(color);
    head.visible = true;
    halo.position.set(p.x, 0.02, p.z);
    halo.visible = true;

    // Add to terrain accumulator
    addPointToTerrain(p.x, p.z, p.y, frame.entropy || 0);
  }

  function clearTrail() {
    trail = [];
    trailGeo.setDrawRange(0, 0);
    for (let i = 0; i < MAX_TRAIL; i++) {
      dots.setMatrixAt(i, mZero);
    }
    dots.instanceMatrix.needsUpdate = true;
    head.visible = false;
    halo.visible = false;
    // NOTE: do NOT clear the terrain — we want historical density to persist
    // as background context. Only the live trail is reset.
  }

  function rebuildTerrainDeferred() {
    // Throttle: only rebuild every 8 frames to avoid jank
    if (trail.length % 8 !== 0) return;
    rebuildTerrainMesh();
  }

  // ===========================================================================
  // 3.5. Historical runs — render once on load, fade them so live stands out
  // ===========================================================================
  const historicalGroup = new THREE.Group();
  scene.add(historicalGroup);

  function renderHistoricalRuns() {
    savedRuns.forEach((run) => {
      const n = run.pts.length;
      if (n < 2) return;
      const colors = historicalColor(run);

      // Line
      const pos = new Float32Array(n * 3);
      for (let i = 0; i < n; i++) {
        pos[i * 3 + 0] = run.pts[i][0];
        pos[i * 3 + 1] = run.pts[i][1];
        pos[i * 3 + 2] = run.pts[i][2];
      }
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      const mat = new THREE.LineBasicMaterial({
        color: colors.line, transparent: true, opacity: 0.45,
      });
      const line = new THREE.Line(geo, mat);
      historicalGroup.add(line);

      // Faded dots
      const dotGeo = new THREE.SphereGeometry(0.05, 6, 6);
      const dotMat = new THREE.MeshBasicMaterial({
        color: colors.line, transparent: true, opacity: 0.35,
      });
      const im = new THREE.InstancedMesh(dotGeo, dotMat, n);
      const m = new THREE.Matrix4();
      for (let i = 0; i < n; i++) {
        const sz = 0.04 + 0.05 * (1.0 / Math.min(4.0, Math.max(1.0, run.ppl[i] || 1.0)));
        m.makeScale(sz, sz, sz);
        m.setPosition(run.pts[i][0], run.pts[i][1], run.pts[i][2]);
        im.setMatrixAt(i, m);
      }
      im.instanceMatrix.needsUpdate = true;
      historicalGroup.add(im);

      // Seed the terrain accumulator with these historical points so the
      // dynamic terrain reflects both old + new data.
      for (let i = 0; i < n; i++) {
        addPointToTerrain(run.pts[i][0], run.pts[i][2], run.pts[i][1], run.ent[i] || 0);
      }
    });
    // Build the initial terrain from the historical seed.
    rebuildTerrainMesh();
  }
  renderHistoricalRuns();

  // ===========================================================================
  // 5. HUD + live text
  // ===========================================================================
  const hudPrompt = $('hud-prompt');
  const hudStep = $('hud-step');
  const hudTok = $('hud-tok');
  const hudPpl = $('hud-ppl');
  const hudEnt = $('hud-ent');
  const hudFrames = $('hud-frames');
  const hudPos = $('hud-pos');
  const liveText = $('live-text');
  let currentRunPrompt = '';

  function updateHudFromFrame(frame) {
    hudTok.textContent = frame.token || '·';
    hudPpl.textContent = frame.perplexity != null ? frame.perplexity.toFixed(2) : '—';
    hudEnt.textContent = frame.entropy != null ? frame.entropy.toFixed(2) : '—';
    hudStep.textContent = frame.step_id;
    hudPos.textContent = `(${frame.point.x.toFixed(1)}, ${frame.point.y.toFixed(1)}, ${frame.point.z.toFixed(1)})`;
  }

  function rerenderLiveText() {
    let html = '';
    for (let i = 0; i < trail.length; i++) {
      const t = trail[i];
      const cls = t.is_self_check ? 'self' : (t.is_revisit ? 'revisit' : 't');
      const isCur = (i === trail.length - 1);
      const finalCls = isCur ? `cur ${cls}` : cls;
      html += `<span class="${finalCls}">${esc(t.token || '·')}</span>`;
    }
    liveText.innerHTML = html;
    liveText.scrollTop = liveText.scrollHeight;
  }

  // ===========================================================================
  // 6. WebSocket
  // ===========================================================================
  const statusEl = $('status');
  const statusText = $('status-text');
  const connectBtn = $('connect-btn');
  const disconnectBtn = $('disconnect-btn');
  const runBtn = $('run-btn');
  const stopBtn = $('stop-btn');

  function setStatus(state, text) {
    statusEl.className = state;
    statusText.textContent = text;
  }

  function connect() {
    if (ws) return;
    const host = $('ws-url').value.trim() || 'localhost:8765';
    const url = host.startsWith('ws://') ? host : `ws://${host}`;
    setStatus('connecting', 'connecting…');
    try {
      ws = new WebSocket(url);
    } catch (e) {
      showError('WS ctor: ' + e.message);
      setStatus('error', 'failed');
      return;
    }
    ws.onopen = () => {
      connected = true;
      setStatus('connected', 'connected');
      connectBtn.disabled = true;
      disconnectBtn.disabled = false;
      runBtn.disabled = false;
      // Server will push a `ready` message; no need to send anything yet.
    };
    ws.onmessage = (evt) => {
      let msg;
      try { msg = JSON.parse(evt.data); } catch (e) { return; }
      if (msg.kind === 'ready') {
        // Server says it's ready to take a start command.
        return;
      }
      if (msg.kind === 'reset_ack' || msg.kind === 'error') {
        if (msg.kind === 'error') showError(msg.payload?.message || 'server error');
        receivingRun = false;
        runBtn.disabled = false;
        stopBtn.disabled = true;
        return;
      }
      // Assume it's a Frame payload (kind may be omitted in current protocol).
      const f = msg.payload || msg;
      if (f && typeof f.point === 'object' && typeof f.token === 'string') {
        appendTrailPoint(f);
        updateHudFromFrame(f);
        rerenderLiveText();
        rebuildTerrainDeferred();
        hudFrames.textContent = trail.length;
        return;
      }
    };
    ws.onerror = (e) => {
      showError('WS error');
      setStatus('error', 'error');
    };
    ws.onclose = (e) => {
      connected = false;
      ws = null;
      setStatus('', 'disconnected');
      connectBtn.disabled = false;
      disconnectBtn.disabled = true;
      runBtn.disabled = true;
      stopBtn.disabled = true;
      receivingRun = false;
    };
  }

  function disconnect() {
    if (ws) ws.close();
  }

  function startRun() {
    if (!connected || receivingRun) return;
    clearTrail();
    currentRunPrompt = $('prompt').value.trim();
    hudPrompt.textContent = currentRunPrompt.slice(0, 60) + (currentRunPrompt.length > 60 ? '…' : '');
    const layer = parseInt($('layer').value) || 14;
    ws.send(JSON.stringify({
      kind: 'start',
      payload: { prompt: currentRunPrompt, layer: layer },
    }));
    receivingRun = true;
    runBtn.disabled = true;
    stopBtn.disabled = false;
  }

  function stopRun() {
    if (!ws || !receivingRun) return;
    ws.send(JSON.stringify({ kind: 'cancel', payload: {} }));
  }

  connectBtn.addEventListener('click', connect);
  disconnectBtn.addEventListener('click', disconnect);
  runBtn.addEventListener('click', startRun);
  stopBtn.addEventListener('click', stopRun);
  $('prompt').addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') startRun();
  });

  // ===========================================================================
  // 7. Camera presets
  // ===========================================================================
  document.querySelectorAll('#cam-buttons button').forEach(b => {
    b.addEventListener('click', () => {
      document.querySelectorAll('#cam-buttons button').forEach(x =>
        x.classList.toggle('active', x === b));
      const t = controls.target;
      if (b.dataset.cam === 'persp') camera.position.set(22, 18, 28);
      else if (b.dataset.cam === 'iso') camera.position.set(25, 25, 25);
      else if (b.dataset.cam === 'top') {
        camera.position.set(0, 40, 0.001); camera.up.set(0, 0, -1);
      } else if (b.dataset.cam === 'side') {
        camera.position.set(0, 8, 35); camera.up.set(0, 1, 0);
      }
      if (b.dataset.cam === 'persp' || b.dataset.cam === 'iso' || b.dataset.cam === 'side') {
        camera.up.set(0, 1, 0);
      }
      controls.update();
    });
  });

  // ===========================================================================
  // 8. Render loop
  // ===========================================================================
  function tick(t) {
    requestAnimationFrame(tick);
    // Pulse the head dot + halo
    const s = 1 + 0.18 * Math.sin(t * 0.006);
    head.scale.setScalar(s);
    if (halo.visible) {
      const hs = 1 + 0.35 * Math.sin(t * 0.008);
      halo.scale.setScalar(hs);
      halo.material.opacity = 0.4 + 0.35 * Math.abs(Math.sin(t * 0.008));
    }
    controls.update();
    renderer.render(scene, camera);
  }
  requestAnimationFrame(tick);

  window.addEventListener('resize', () => {
    camera.aspect = sceneEl.clientWidth / sceneEl.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(sceneEl.clientWidth, sceneEl.clientHeight);
  });

  console.log('[live-terrain] ready');
})();
"""


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def main():
    three_js, orbit_js = extract_libs()
    saved_runs = load_saved_runs()
    out_html = (
        PAGE_HTML
        .replace("{THREE_JS}", three_js)
        .replace("{ORBIT_JS}", orbit_js)
        .replace("{SAVED_RUNS_JSON}", saved_runs)
        .replace("{APP_JS}", APP_JS)
    )
    OUT.mkdir(exist_ok=True)
    LIVE_HTML.write_text(out_html, encoding="utf-8")
    print(f"wrote {LIVE_HTML} ({len(out_html) / 1024:.1f} KB)")
    print(f"  embedded {len(saved_runs) / 1024:.1f} KB of saved runs")


if __name__ == "__main__":
    main()
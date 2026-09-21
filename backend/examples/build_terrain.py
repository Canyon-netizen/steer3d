"""Build a 3-D terrain visualization from the global hidden-state projection.

For every token across all prompts we have a 2-D point (PCA of the 2048-d
hidden state). We render those points as a height field where:

  height  = perplexity         (peaks = model uncertainty)
  color   = entropy            (hue)
  trajectories float at altitude 1 / perplexity  (so confident tokens
  ride high, uncertain tokens dip)

This is much easier to read than a tangled point cloud: the *landscape*
is the same for every prompt, and each run traces a path through it.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"

JSON_PATH = OUT / "qwen3_global.json"
VENDOR = OUT / "vendor"
THREE_JS = VENDOR / "three.min.js"
ORBIT_JS = VENDOR / "OrbitControls.js"


def build_height_field(points: np.ndarray, values: np.ndarray,
                       grid_n: int = 80, smooth: float = 1.5):
    """Inverse-distance-weighted interpolation of `values` onto a grid.

    points : (N, 2)  floats in PCA coords
    values : (N,)    floats (e.g. perplexity)
    grid_n : grid resolution
    smooth : smoothing radius (in grid units)
    """
    # Normalize points to a 0..1 box, then add a small margin
    pmin = points.min(axis=0)
    pmax = points.max(axis=0)
    rng = (pmax - pmin)
    rng[rng == 0] = 1.0
    pn = (points - pmin) / rng  # (N, 2) in [0,1]

    # Make the grid slightly larger than the data
    margin = 0.05
    coords = np.linspace(-margin, 1 + margin, grid_n)
    gx, gy = np.meshgrid(coords, coords)  # both (grid_n, grid_n)
    grid = np.stack([gx.ravel(), gy.ravel()], axis=1)  # (G, 2)

    # IDW: weight = 1 / (dist^smooth)
    diff = grid[:, None, :] - pn[None, :, :]            # (G, N, 2)
    dist = np.sqrt((diff ** 2).sum(axis=-1))            # (G, N)
    # Avoid div-by-zero on exact matches
    eps = 1e-6
    weights = 1.0 / (dist ** smooth + eps)              # (G, N)
    wsum = weights.sum(axis=1, keepdims=True)
    z = (weights * values[None, :]).sum(axis=1) / wsum.squeeze(-1)
    return gx, gy, z.reshape(grid_n, grid_n)


def main():
    with open(JSON_PATH) as f:
        data = json.load(f)

    # Collect every point and its perplexity
    pts, ppls, ents = [], [], []
    runs_data = []
    for r in data:
        run_pts, run_ppl, run_ent, run_tok, run_sc = [], [], [], [], []
        for fr in r["frames"]:
            if not fr.get("token"):
                continue
            pts.append([fr["x"], fr["y"]])
            ppls.append(fr.get("perplexity") or 1.0)
            ents.append(fr.get("entropy") or 0.0)
            run_pts.append([fr["x"], fr["y"]])
            run_ppl.append(fr.get("perplexity") or 1.0)
            run_ent.append(fr.get("entropy") or 0.0)
            run_tok.append(fr["token"])
            run_sc.append(fr.get("is_self_check", False))
        runs_data.append({
            "prompt": r["prompt"],
            "tag": r["tag"],
            "kind": r["kind"],
            "correct": r["correct"],
            "expected": r.get("expected", ""),
            "generated_text": r.get("generated_text", "")[:300],
            "n_tokens": len(run_tok),
            "pts": run_pts,
            "ppl": run_ppl,
            "ent": run_ent,
            "tok": run_tok,
            "sc": run_sc,
        })

    pts = np.asarray(pts, dtype=np.float64)
    ppls = np.asarray(ppls, dtype=np.float64)
    ents = np.asarray(ents, dtype=np.float64)

    # Fit a 2-D projection by re-using the existing 3-D coords: pick top-2
    # axes (x and y) and project onto a grid for the terrain. (We already
    # have a 3-D global PCA, but using x/y keeps the terrain in the plane
    # the user is already viewing in.)
    print(f"loaded {len(runs_data)} runs, {len(pts)} tokens total")
    print(f"  x range: [{pts[:, 0].min():.2f}, {pts[:, 0].max():.2f}]")
    print(f"  y range: [{pts[:, 1].min():.2f}, {pts[:, 1].max():.2f}]")
    print(f"  ppl range: [{ppls.min():.2f}, {ppls.max():.2f}]")
    print(f"  entropy range: [{ents.min():.2f}, {ents.max():.2f}]")

    grid_n = 100
    gx, gy, z_ppl = build_height_field(pts, ppls, grid_n=grid_n, smooth=1.2)
    _,  _, z_ent = build_height_field(pts, ents,  grid_n=grid_n, smooth=1.2)

    # Clip ppl to 95th percentile to avoid a few outliers dominating
    ppl_clip = np.percentile(ppls, 95)
    ppls_c = np.clip(ppls, 1.0, ppl_clip)
    _, _, z_ppl_c = build_height_field(pts, ppls_c, grid_n=grid_n, smooth=1.2)

    # Normalize entropy to [0,1]
    z_ent_n = (z_ent - z_ent.min()) / (z_ent.max() - z_ent.min() + 1e-6)

    # Heights: clip-normalized ppl log, then scale to ~8 units
    z_ppl_log = np.log1p(z_ppl_c - 1.0)
    z_ppl_log -= z_ppl_log.min()
    z_ppl_log /= (z_ppl_log.max() + 1e-6)
    heights = z_ppl_log * 10.0   # up to 10 units tall

    print(f"  terrain height range: [{heights.min():.2f}, {heights.max():.2f}]")
    print(f"  ppl 95th percentile : {ppl_clip:.2f}")

    # Build the per-vertex color: lerp from deep blue (calm) to red (hot)
    # based on the *normalized* entropy. Use saturated colors so they
    # show through lighting.
    def color_for(entropy, height):
        # Map entropy 0..1 to three-stop gradient (blue → cyan → yellow → red)
        e = max(0.0, min(1.0, entropy))
        if e < 0.33:
            t = e / 0.33
            r = int(20 + (40 - 20) * t)
            g = int(60 + (160 - 60) * t)
            b = int(180 + (220 - 180) * t)
        elif e < 0.66:
            t = (e - 0.33) / 0.33
            r = int(40 + (220 - 40) * t)
            g = int(160 + (200 - 160) * t)
            b = int(220 + (40 - 220) * t)
        else:
            t = (e - 0.66) / 0.34
            r = int(220 + (240 - 220) * t)
            g = int(200 + (80 - 200) * t)
            b = int(40 + (40 - 40) * t)
        # Height-based brightness boost (peaks glow)
        boost = 0.7 + 0.5 * min(1.0, height / 10.0)
        r = min(255, int(r * boost))
        g = min(255, int(g * boost))
        b = min(255, int(b * boost))
        return (r, g, b)

    colors_flat = []
    for j in range(grid_n):
        for i in range(grid_n):
            colors_flat.extend(color_for(z_ent_n[j, i], heights[j, i]))
    colors_flat = np.asarray(colors_flat, dtype=np.uint8)

    # Position the grid in scene coordinates. We translate so that the
    # original (x, y) PCA coords match grid coordinates 1:1.
    # First scale: original PCA range maps to 20 scene units.
    pmin = pts.min(axis=0); pmax = pts.max(axis=0)
    prange = (pmax - pmin); prange[prange == 0] = 1.0
    scene_scale = 20.0

    def to_scene(p):
        return ((p - pmin) / prange - 0.5) * scene_scale

    # ----- Build the embedded JS payload --------------------------------------
    # Grid vertex data
    positions = []
    for j in range(grid_n):
        for i in range(grid_n):
            x, y = gx[j, i], gy[j, i]
            # Map grid coord -> scene coord
            sx = (x - 0.5) * scene_scale
            sy = float(heights[j, i])
            sz = (y - 0.5) * scene_scale
            positions.extend([sx, sy, sz])

    # Triangle indices
    indices = []
    for j in range(grid_n - 1):
        for i in range(grid_n - 1):
            a = j * grid_n + i
            b = a + 1
            c = a + grid_n
            d = c + 1
            indices.extend([a, b, c, b, d, c])

    # Per-run trajectory data, with each token's height = 1/ppl mapped
    # to a sensible band above the terrain
    runs_payload = []
    for r in runs_data:
        run_pts_scene = []
        for k, (p, ppl) in enumerate(zip(r["pts"], r["ppl"])):
            sx, sz = to_scene(np.asarray(p, dtype=np.float64))
            # Height band: confident tokens ride higher (12-14 above sea level)
            # Uncertain tokens dip slightly lower
            confidence = 1.0 / max(1.05, min(ppl, 4.0))  # 0.25 .. ~1.0
            sy = 12.0 + 3.0 * confidence
            run_pts_scene.append([sx, sy, sz])
        runs_payload.append({
            "prompt": r["prompt"],
            "tag": r["tag"],
            "kind": r["kind"],
            "correct": r["correct"],
            "expected": r["expected"],
            "generated_text": r["generated_text"],
            "n_tokens": r["n_tokens"],
            "scene_pts": run_pts_scene,
            "ppl": r["ppl"],
            "ent": r["ent"],
            "tok": r["tok"],
            "sc": r["sc"],
        })

    payload = {
        "grid_n": grid_n,
        "positions": positions,
        "indices": indices,
        "colors": colors_flat.tolist(),
        "scene_scale": scene_scale,
        "ppl_min": float(ppls.min()),
        "ppl_max": float(ppls.max()),
        "ent_min": float(ents.min()),
        "ent_max": float(ents.max()),
        "runs": runs_payload,
    }

    # Read three.js + OrbitControls
    three_js = THREE_JS.read_text()
    orbit_js = ORBIT_JS.read_text()

    json_payload = json.dumps(payload, ensure_ascii=False)

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Qwen3-1.7B Reasoning Terrain 3D</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  :root {{
    --bg: #0a0d12; --panel: #131820; --border: #1f2630;
    --text: #d6dde7; --muted: #7e8694; --accent: #5cb6ff;
  }}
  html, body {{ margin:0; padding:0; height:100%; background:var(--bg);
    color:var(--text); font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
    overflow:hidden; }}
  #app {{ display:grid; grid-template-columns:1fr 360px; height:100vh; }}
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
    border-radius:8px; padding:6px; z-index:10;
  }}
  #cam-buttons button {{
    background:transparent; color:var(--text); border:1px solid var(--border);
    padding:5px 10px; border-radius:5px; font-size:11px; cursor:pointer;
  }}
  #cam-buttons button.active {{
    background:var(--accent); color:#001a2c; border-color:var(--accent);
  }}
  #legend {{ position:absolute; left:16px; bottom:16px;
    background:rgba(19,24,32,.85); border:1px solid var(--border);
    border-radius:10px; padding:12px 14px; font-size:12px;
    line-height:1.7; pointer-events:none; }}
  #legend .row {{ display:flex; align-items:center; gap:8px; }}
  #legend .dot {{ width:10px; height:10px; border-radius:50%; }}
  #legend .grad {{ width:120px; height:8px; border-radius:4px;
    background: linear-gradient(to right, rgb(30,80,180), rgb(80,200,60), rgb(220,90,60)); }}
  aside {{ background:var(--panel); border-left:1px solid var(--border);
    display:flex; flex-direction:column; min-height:0; }}
  .controls {{ padding:14px; border-bottom:1px solid var(--border); }}
  .controls h2 {{ font-size:12px; font-weight:600; color:var(--muted);
    letter-spacing:.08em; text-transform:uppercase; margin:0 0 12px; }}
  .row-c {{ display:flex; align-items:center; gap:8px; margin-bottom:8px; }}
  .row-c label {{ font-size:12px; color:var(--muted); min-width:60px; }}
  button {{ background:var(--accent); color:#001a2c; border:0;
    padding:7px 14px; border-radius:6px; font-weight:600;
    font-size:12px; cursor:pointer; }}
  button.ghost {{ background:transparent; color:var(--text);
    border:1px solid var(--border); }}
  input[type=range] {{ flex:1; }}
  input[type=checkbox] {{ accent-color:var(--accent); }}
  #runs {{ flex:1; min-height:0; overflow-y:auto; padding:12px 14px; }}
  .run {{ padding:10px 12px; border:1px solid var(--border);
    border-radius:8px; margin-bottom:8px; cursor:pointer;
    transition:.15s; }}
  .run:hover {{ border-color:var(--accent); }}
  .run.active {{ border-color:var(--accent); background:rgba(92,182,255,.07); }}
  .run .head {{ display:flex; align-items:center; gap:8px;
    font-size:12px; font-weight:600; }}
  .badge {{ padding:1px 6px; border-radius:4px; font-size:10px;
    font-weight:700; letter-spacing:.04em; }}
  .b-easy {{ background:#1a4731; color:#58e090; }}
  .b-hard {{ background:#4a1820; color:#f57880; }}
  .b-ok {{ background:#1a4731; color:#58e090; }}
  .b-no {{ background:#4a1820; color:#f57880; }}
  .run .prompt {{ margin-top:6px; font-size:11px; color:var(--muted);
    line-height:1.45; }}
  .run .gen {{ margin-top:6px; font-size:11px; color:#a8b1c4;
    font-family:ui-monospace,Menlo,monospace; line-height:1.4; }}
  #hud {{ position:absolute; top:16px; right:16px;
    background:rgba(19,24,32,.85); border:1px solid var(--border);
    border-radius:10px; padding:10px 14px; font-size:12px;
    line-height:1.6; font-family:ui-monospace,Menlo,monospace; }}
  #hud .stat {{ color:var(--muted); }}
  #hud .val {{ color:var(--text); font-weight:600; }}
  #hud .tok {{ display:inline-block; padding:1px 6px; margin-right:4px;
    background:rgba(92,182,255,.12); border-radius:4px; color:var(--accent); }}
  #text-panel {{ border-top:1px solid var(--border); padding:10px 14px;
    max-height:30%; overflow-y:auto;
    font-family:ui-monospace,Menlo,monospace; font-size:12px;
    line-height:1.5; }}
  #text-panel h3 {{ margin:0 0 6px; font-size:11px; color:var(--muted);
    font-weight:600; text-transform:uppercase; letter-spacing:.06em; }}
  #text-panel .t {{ color:var(--text); }}
  #text-panel .self {{ color:#ff9d57; font-weight:600; }}
  #err {{ position:absolute; top:8px; left:8px; max-width:50%;
    background:#4a1820; color:#ffd0d6; padding:8px 12px;
    border-radius:6px; font-family:monospace; font-size:11px;
    display:none; z-index:100; }}
</style>
</head>
<body>
<div id="app">
  <div id="scene-wrap">
    <div id="scene"></div>
    <div id="err"></div>
    <div id="cam-buttons">
      <button data-cam="persp" class="active">Perspective</button>
      <button data-cam="iso">Isometric</button>
      <button data-cam="top">Top-Down</button>
      <button data-cam="side">Side</button>
    </div>
    <div id="scene-hint">🖱 drag to rotate · scroll to zoom · right-drag to pan</div>
    <div id="hud">
      <div><span class="stat">prompt: </span><span id="hud-prompt" class="val">—</span></div>
      <div><span class="stat">step: </span><span id="hud-step" class="val">0</span> /
           <span id="hud-tot" class="val">0</span></div>
      <div><span class="stat">token: </span><span id="hud-tok" class="tok">·</span></div>
      <div><span class="stat">ppl: </span><span id="hud-ppl" class="val">—</span> ·
           <span class="stat">ent: </span><span id="hud-entropy" class="val">—</span></div>
      <div><span class="stat">elev: </span><span id="hud-elev" class="val">—</span></div>
    </div>
    <div id="legend">
      <div style="font-weight:600;margin-bottom:6px">TERRAIN</div>
      <div class="row"><div class="grad"></div>
        <span style="font-size:11px;color:var(--muted)">low → high entropy</span></div>
      <div style="font-weight:600;margin:8px 0 6px">PEAKS = UNCERTAINTY</div>
      <div style="font-size:11px;color:var(--muted)">
        height = log(perplexity)<br>
        colored by entropy
      </div>
      <div style="font-weight:600;margin:8px 0 6px">TRAJECTORIES</div>
      <div class="row"><span class="dot" style="background:#34c759"></span>easy ✓</div>
      <div class="row"><span class="dot" style="background:#ff9f0a"></span>easy ✗</div>
      <div class="row"><span class="dot" style="background:#ff453a"></span>hard ✗</div>
      <div class="row"><span class="dot" style="background:#5e9cff"></span>hard ✓ (rare)</div>
      <div class="row"><span class="dot" style="background:#fff"></span>current token</div>
    </div>
  </div>
  <aside>
    <div class="controls">
      <h2>Controls</h2>
      <div class="row-c">
        <button id="play-btn">▶ Play</button>
        <button class="ghost" id="reset-btn">⟲ Reset</button>
        <button class="ghost" id="single-btn">Single</button>
      </div>
      <div class="row-c">
        <label>Speed</label>
        <input id="speed" type="range" min="1" max="60" step="1" value="10" />
        <span id="speed-val" style="font-size:12px;color:var(--muted);width:34px">10×</span>
      </div>
      <div class="row-c">
        <label>Step</label>
        <input id="step" type="range" min="0" max="100" step="1" value="0" />
        <span id="step-val" style="font-size:12px;color:var(--muted);width:34px">0</span>
      </div>
      <div class="row-c" style="margin-top:4px">
        <label style="display:flex;align-items:center;gap:6px">
          <input id="follow" type="checkbox" /> follow token
        </label>
      </div>
    </div>
    <div id="runs">
      <h2 style="font-size:12px;color:var(--muted);font-weight:600;
                 letter-spacing:.08em;text-transform:uppercase;margin:0 0 10px">
        Prompts (8)
      </h2>
      <div id="run-list"></div>
    </div>
    <div id="text-panel">
      <h3>Live generated text</h3>
      <div id="live-text">Click ▶ Play or a run on the right to start.</div>
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
  const errEl = document.getElementById('err');
  function showError(msg) {{
    errEl.textContent = msg; errEl.style.display = 'block';
    console.error(msg);
  }}
  window.addEventListener('error', e => showError('JS error: ' + e.message));
  window.addEventListener('unhandledrejection', e => showError('Promise error: ' + e.message));

  const PAYLOAD = {json_payload};

  if (typeof THREE === 'undefined') {{ showError('three.js failed'); return; }}
  if (typeof OrbitControls === 'undefined') {{ showError('OrbitControls failed'); return; }}

  const wrap = document.getElementById('scene');
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0d12);
  scene.fog = new THREE.Fog(0x0a0d12, 25, 60);

  const camera = new THREE.PerspectiveCamera(45, wrap.clientWidth / wrap.clientHeight, 0.1, 200);
  camera.position.set(22, 18, 28);

  const renderer = new THREE.WebGLRenderer({{ antialias: true }});
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setSize(wrap.clientWidth, wrap.clientHeight);
  wrap.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 5;
  controls.maxDistance = 80;
  controls.target.set(0, 1.5, 0);

  // ----- Lighting ----------------------------------------------------------
  scene.add(new THREE.AmbientLight(0xffffff, 0.85));
  const dir1 = new THREE.DirectionalLight(0xffffff, 0.45);
  dir1.position.set(12, 18, 8);
  scene.add(dir1);
  const dir2 = new THREE.DirectionalLight(0x6090ff, 0.20);
  dir2.position.set(-10, 6, -8);
  scene.add(dir2);

  // ----- Terrain mesh ------------------------------------------------------
  const gridN = PAYLOAD.grid_n;
  const positions = new Float32Array(PAYLOAD.positions);
  const colors = new Float32Array(PAYLOAD.colors);
  const indices = new Uint32Array(PAYLOAD.indices);

  const terrainGeo = new THREE.BufferGeometry();
  terrainGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  terrainGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3, true));
  terrainGeo.setIndex(new THREE.BufferAttribute(indices, 1));
  terrainGeo.computeVertexNormals();

  const terrainMat = new THREE.MeshLambertMaterial({{
    vertexColors: true,
    flatShading: true,
    side: THREE.DoubleSide,
  }});
  const terrain = new THREE.Mesh(terrainGeo, terrainMat);
  scene.add(terrain);

  // Wireframe overlay for better readability
  const wireGeo = new THREE.WireframeGeometry(terrainGeo);
  const wireMat = new THREE.LineBasicMaterial({{
    color: 0x223344, transparent: true, opacity: 0.22,
  }});
  const wire = new THREE.LineSegments(wireGeo, wireMat);
  scene.add(wire);

  // Ground shadow disc
  const shadowGeo = new THREE.CircleGeometry(20, 64);
  const shadowMat = new THREE.MeshBasicMaterial({{
    color: 0x000000, transparent: true, opacity: 0.5,
  }});
  const shadow = new THREE.Mesh(shadowGeo, shadowMat);
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.y = -0.05;
  scene.add(shadow);

  // ----- Per-run trajectories ---------------------------------------------
  function colorFor(run) {{
    if (run.tag === 'easy' && run.correct) return {{ line: 0x34c759, glow: 0x6dfaa3 }};
    if (run.tag === 'easy' && !run.correct) return {{ line: 0xff9f0a, glow: 0xffc97a }};
    if (run.tag === 'hard' && run.correct) return {{ line: 0x5e9cff, glow: 0x9cc4ff }};
    return {{ line: 0xff453a, glow: 0xff7a72 }};
  }}

  const trajectories = new THREE.Group();
  scene.add(trajectories);

  const runObjs = PAYLOAD.runs.map((run) => {{
    const n = run.scene_pts.length;
    const pos = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {{
      pos[i*3+0] = run.scene_pts[i][0];
      pos[i*3+1] = run.scene_pts[i][1];
      pos[i*3+2] = run.scene_pts[i][2];
    }}
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setDrawRange(0, 0);

    const c = colorFor(run);
    const lineMat = new THREE.LineBasicMaterial({{
      color: c.line, transparent: true, opacity: 0.9, linewidth: 2,
    }});
    const line = new THREE.Line(geo, lineMat);
    trajectories.add(line);

    // Bead at the head
    const head = new THREE.Mesh(
      new THREE.SphereGeometry(0.32, 16, 16),
      new THREE.MeshBasicMaterial({{
        color: c.glow, transparent: true, opacity: 0,
      }})
    );
    trajectories.add(head);

    // Trail dots (small spheres)
    const sphereGeo = new THREE.SphereGeometry(0.10, 8, 8);
    const sphereMat = new THREE.MeshBasicMaterial({{
      color: c.line, transparent: true, opacity: 0.85,
    }});
    const sphere = new THREE.InstancedMesh(sphereGeo, sphereMat, n);
    const m = new THREE.Matrix4().makeScale(0, 0, 0);
    for (let i = 0; i < n; i++) sphere.setMatrixAt(i, m);
    sphere.instanceMatrix.needsUpdate = true;
    trajectories.add(sphere);

    return {{ run, line, sphere, head, n }};
  }});

  // ----- State + UI --------------------------------------------------------
  let step = 0, playing = false, speed = 10, follow = false;
  let focusIdx = 0, singleMode = false;
  let camMode = 'persp';

  const maxLen = Math.max(...PAYLOAD.runs.map(r => r.n_tokens));
  document.getElementById('hud-tot').textContent = maxLen;
  document.getElementById('step').max = maxLen - 1;

  const $ = id => document.getElementById(id);
  const hudPrompt = $('hud-prompt'), hudStep = $('hud-step'),
        hudTok = $('hud-tok'), hudPpl = $('hud-ppl'),
        hudEnt = $('hud-entropy'), hudElev = $('hud-elev');

  function setCam(mode) {{
    camMode = mode;
    document.querySelectorAll('#cam-buttons button').forEach(b => {{
      b.classList.toggle('active', b.dataset.cam === mode);
    }});
    const t = controls.target;
    if (mode === 'persp') {{
      camera.position.set(22, 18, 28);
    }} else if (mode === 'iso') {{
      camera.position.set(25, 25, 25);
    }} else if (mode === 'top') {{
      camera.position.set(0, 40, 0.001);
      camera.up.set(0, 0, -1);
    }} else if (mode === 'side') {{
      camera.position.set(0, 8, 35);
      camera.up.set(0, 1, 0);
    }}
    if (mode === 'persp' || mode === 'iso' || mode === 'side') {{
      camera.up.set(0, 1, 0);
    }}
    controls.update();
  }}

  function refresh() {{
    for (let i = 0; i < runObjs.length; i++) {{
      const obj = runObjs[i];
      const n = Math.min(Math.floor(step) + 1, obj.n);
      const dim = (!singleMode || focusIdx === i);
      obj.line.geometry.setDrawRange(0, n);
      obj.line.material.opacity = dim ? 0.9 : 0.05;

      const m = new THREE.Matrix4();
      for (let k = 0; k < obj.n; k++) {{
        const p = obj.run.scene_pts[k];
        if (k < n) {{
          const sz = 0.06 + 0.10 * (1.0 / Math.min(4.0, Math.max(1.0, obj.run.ppl[k])));
          m.makeScale(sz, sz, sz);
          m.setPosition(p[0], p[1], p[2]);
        }} else {{
          m.makeScale(0, 0, 0);
        }}
        obj.sphere.setMatrixAt(k, m);
      }}
      obj.sphere.instanceMatrix.needsUpdate = true;
      obj.sphere.material.opacity = dim ? 0.85 : 0.0;
      if (n > 0) {{
        const p = obj.run.scene_pts[n - 1];
        obj.head.position.set(p[0], p[1], p[2]);
        obj.head.material.opacity = dim ? 0.95 : 0;
      }} else {{
        obj.head.material.opacity = 0;
      }}
    }}

    // HUD: focus run info
    const fr = PAYLOAD.runs[focusIdx];
    const n2 = Math.min(Math.floor(step) + 1, fr.n_tokens);
    hudPrompt.textContent = fr.prompt.slice(0, 60) + (fr.prompt.length > 60 ? '…' : '');
    if (n2 > 0) {{
      const k = n2 - 1;
      hudTok.textContent = fr.tok[k] || '·';
      hudPpl.textContent = fr.ppl[k] != null ? fr.ppl[k].toFixed(2) : '—';
      hudEnt.textContent = fr.ent[k] != null ? fr.ent[k].toFixed(2) : '—';
      hudElev.textContent = fr.scene_pts[k] ? fr.scene_pts[k][1].toFixed(2) : '—';
    }}
    // Live text
    let html = '';
    for (let k = 0; k < n2; k++) {{
      const cls = fr.sc[k] ? 'self' : 't';
      html += '<span class="' + cls + '">' + esc(fr.tok[k]) + '</span>';
    }}
    $('live-text').innerHTML = html;
    $('live-text').scrollTop = $('live-text').scrollHeight;
  }}

  function esc(s) {{
    return (s||'').replace(/[&<>"']/g, c => ({{'&':'&','<':'<','>':'>','"':'"',"'":'&#39;'}})[c]);
  }}

  function setStep(s) {{
    step = Math.max(0, Math.min(maxLen - 1, s));
    $('step').value = step;
    $('step-val').textContent = step;
    hudStep.textContent = step;
    refresh();
  }}

  function focusOn(i) {{
    focusIdx = i;
    document.querySelectorAll('.run').forEach(d => {{
      d.classList.toggle('active', parseInt(d.dataset.idx) === i);
    }});
    refresh();
  }}

  // ----- Run list ---------------------------------------------------------
  PAYLOAD.runs.forEach((r, i) => {{
    const div = document.createElement('div');
    div.className = 'run';
    div.dataset.idx = i;
    div.innerHTML = `
      <div class="head">
        <span class="badge b-${{r.tag}}">${{r.tag}}</span>
        <span class="badge ${{r.correct ? 'b-ok' : 'b-no'}}">${{r.correct ? '✓' : '✗'}}</span>
        <span style="color:var(--muted);font-weight:400">${{r.kind}}</span>
      </div>
      <div class="prompt">${{esc(r.prompt)}}</div>
      <div class="gen">${{esc((r.generated_text||'').slice(0, 110))}}${{(r.generated_text||'').length > 110 ? '…' : ''}}</div>`;
    div.addEventListener('click', () => {{
      singleMode = true;
      $('single-btn').style.background = 'var(--accent)';
      $('single-btn').style.color = '#001a2c';
      focusOn(i);
    }});
    $('run-list').appendChild(div);
  }});

  // ----- Buttons ----------------------------------------------------------
  $('play-btn').addEventListener('click', () => {{
    playing = !playing;
    $('play-btn').textContent = playing ? '⏸ Pause' : '▶ Play';
    if (playing && step >= maxLen - 1) setStep(0);
  }});
  $('reset-btn').addEventListener('click', () => setStep(0));
  $('step').addEventListener('input', e => setStep(parseInt(e.target.value)));
  $('speed').addEventListener('input', e => {{
    speed = parseInt(e.target.value);
    $('speed-val').textContent = speed + '×';
  }});
  $('follow').addEventListener('change', e => follow = e.target.checked);
  $('single-btn').addEventListener('click', () => {{
    singleMode = !singleMode;
    $('single-btn').style.background = singleMode ? 'var(--accent)' : 'transparent';
    $('single-btn').style.color = singleMode ? '#001a2c' : 'var(--text)';
    if (!singleMode) focusOn(0);
    refresh();
  }});
  document.querySelectorAll('#cam-buttons button').forEach(b => {{
    b.addEventListener('click', () => setCam(b.dataset.cam));
  }});

  // Hide hint after first interaction
  function hideHint() {{
    const h = document.getElementById('scene-hint');
    if (h) h.style.display = 'none';
    wrap.removeEventListener('pointerdown', hideHint);
  }}
  wrap.addEventListener('pointerdown', hideHint);

  // ----- Render loop ------------------------------------------------------
  let last = performance.now();
  function tick(now) {{
    const dt = (now - last) / 1000;
    last = now;
    if (playing) {{
      step += speed * dt;
      if (step >= maxLen - 1) {{
        step = maxLen - 1; playing = false;
        $('play-btn').textContent = '▶ Play';
      }}
      $('step').value = step;
      $('step-val').textContent = Math.floor(step);
      hudStep.textContent = Math.floor(step);
      refresh();
    }}
    if (follow) {{
      const obj = runObjs[focusIdx];
      const n = Math.min(Math.floor(step) + 1, obj.n);
      if (n > 0) {{
        const p = obj.run.scene_pts[n - 1];
        const target = new THREE.Vector3(p[0], p[1] + 1.5, p[2]);
        controls.target.lerp(target, 0.08);
      }}
    }}
    const t = now * 0.001;
    for (const obj of runObjs) {{
      const s = 1 + 0.18 * Math.sin(t * 6);
      obj.head.scale.setScalar(s);
    }}
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
  focusOn(0);
  console.log('[terrain] ready runs=' + PAYLOAD.runs.length + ' maxLen=' + maxLen);
  setTimeout(() => {{
    const h = document.getElementById('scene-hint');
    if (h) h.style.opacity = '0.7';
  }}, 500);
}})();
</script>
</body>
</html>
"""

    out_file = OUT / "view_terrain.html"
    out_file.write_text(html, encoding="utf-8")
    print(f"wrote {out_file} ({len(html) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()

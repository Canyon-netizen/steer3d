"""Build a fully self-contained HTML viewer.

Produces ``output/view_standalone.html`` that:
  * embeds the run JSON inline (no fetch needed)
  * embeds three.min.js and OrbitControls.js inline (no CDN)
  * works opened directly via file:// (no HTTP server)
"""

from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
VENDOR = OUT / "vendor"

JSON_PATH = OUT / "qwen3_1p7b_runs.json"
THREE_JS = VENDOR / "three.min.js"
ORBIT_JS = VENDOR / "OrbitControls.js"

with open(JSON_PATH) as f:
    data = json.load(f)
# Slim: keep only what the viewer needs
slim = []
for r in data:
    slim.append({
        "prompt": r["prompt"],
        "tag": r["tag"],
        "kind": r["kind"],
        "correct": r["correct"],
        "expected": r.get("expected", ""),
        "generated_text": r.get("generated_text", "")[:300],
        "n_tokens": r.get("n_tokens", 0),
        "frames": [
            {
                "x": f["x"], "y": f["y"], "z": f["z"],
                "tok": f["token"],
                "ppl": f.get("perplexity"),
                "ent": f.get("entropy"),
                "sc": f.get("is_self_check", False),
                "sid": f["step_id"],
            } for f in r["frames"]
        ],
    })

with open(THREE_JS) as f:
    three_js = f.read()
with open(ORBIT_JS) as f:
    orbit_js = f.read()

html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Qwen3-1.7B Reasoning Trajectory 3D</title>
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
  #scene {{ width:100%; height:100%; }}
  #legend {{ position:absolute; left:16px; bottom:16px;
    background:rgba(19,24,32,.85); border:1px solid var(--border);
    border-radius:10px; padding:12px 14px; font-size:12px;
    line-height:1.7; pointer-events:none; }}
  #legend .row {{ display:flex; align-items:center; gap:8px; }}
  #legend .dot {{ width:10px; height:10px; border-radius:50%; }}
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
  #hud {{ position:absolute; top:16px; left:16px;
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
  #err {{ position:absolute; top:8px; right:8px; max-width:50%;
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
    <div id="hud">
      <div><span class="stat">prompt: </span><span id="hud-prompt" class="val">—</span></div>
      <div><span class="stat">step: </span><span id="hud-step" class="val">0</span> /
           <span id="hud-tot" class="val">0</span></div>
      <div><span class="stat">token: </span><span id="hud-tok" class="tok">·</span></div>
      <div><span class="stat">ppl: </span><span id="hud-ppl" class="val">—</span> ·
           <span class="stat">entropy: </span><span id="hud-entropy" class="val">—</span></div>
      <div><span class="stat">xyz: </span><span id="hud-xyz" class="val">—</span></div>
    </div>
    <div id="legend">
      <div class="row"><span class="dot" style="background:#34c759"></span>easy ✓</div>
      <div class="row"><span class="dot" style="background:#ff9f0a"></span>easy ✗</div>
      <div class="row"><span class="dot" style="background:#ff453a"></span>hard ✗</div>
      <div class="row"><span class="dot" style="background:#5e9cff"></span>hard ✓ (rare)</div>
      <div class="row"><span style="display:inline-block;width:14px;height:2px;background:#bbb"></span>trajectory ribbon</div>
      <div class="row"><span style="display:inline-block;width:8px;height:8px;background:#fff;border-radius:50%"></span>current step (pulse)</div>
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
          <input id="follow" type="checkbox" checked /> follow camera
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

<!-- ============= INLINE three.min.js (UMD, exposes global THREE) =========== -->
<script>
{three_js}
</script>
<!-- ============= INLINE OrbitControls (patched to use global THREE) ======= -->
<script>
{orbit_js}
</script>

<!-- ============= Application =============================================== -->
<script>
(function () {{
  // ----- Error reporter so silent failures show up --------------------------
  const errEl = document.getElementById('err');
  function showError(msg) {{
    errEl.textContent = msg; errEl.style.display = 'block';
    console.error(msg);
  }}
  window.addEventListener('error', e => showError('JS error: ' + e.message));
  window.addEventListener('unhandledrejection', e => showError('Promise error: ' + e.message));

  // ----- Inline JSON --------------------------------------------------------
  const RUNS = {json.dumps(slim, ensure_ascii=False)};
  const runs = RUNS;
  const maxLen = Math.max(...runs.map(r => r.frames.length));
  document.getElementById('hud-tot').textContent = maxLen;
  document.getElementById('step').max = maxLen - 1;

  // ----- Three.js sanity check ---------------------------------------------
  if (typeof THREE === 'undefined') {{
    showError('three.js failed to load (THREE undefined)');
    return;
  }}
  if (typeof OrbitControls === 'undefined') {{
    showError('OrbitControls failed to load');
    return;
  }}

  // ----- Scene -------------------------------------------------------------
  const wrap = document.getElementById('scene');
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0d12);

  const camera = new THREE.PerspectiveCamera(50, wrap.clientWidth / wrap.clientHeight, 0.1, 500);
  camera.position.set(20, 16, 30);

  const renderer = new THREE.WebGLRenderer({{ antialias: true }});
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setSize(wrap.clientWidth, wrap.clientHeight);
  wrap.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.06;

  // Star field
  {{
    const starGeo = new THREE.BufferGeometry();
    const N = 1200;
    const pos = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) {{
      const r = 80 + Math.random() * 60;
      const phi = Math.acos(2 * Math.random() - 1);
      const theta = 2 * Math.PI * Math.random();
      pos[i*3+0] = r * Math.sin(phi) * Math.cos(theta);
      pos[i*3+1] = r * Math.sin(phi) * Math.sin(theta);
      pos[i*3+2] = r * Math.cos(phi);
    }}
    starGeo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    scene.add(new THREE.Points(starGeo,
      new THREE.PointsMaterial({{ color:0x445566, size:0.6, sizeAttenuation:true }})));
  }}

  // Axes
  scene.add(new THREE.GridHelper(40, 20, 0x1f2630, 0x161a22));
  function axis(vec, col) {{
    const g = new THREE.BufferGeometry();
    g.setFromPoints([new THREE.Vector3(0,0,0), vec.clone().multiplyScalar(8)]);
    scene.add(new THREE.Line(g, new THREE.LineBasicMaterial({{color:col}})));
    const tip = new THREE.Mesh(
      new THREE.ConeGeometry(0.18, 0.6, 12),
      new THREE.MeshBasicMaterial({{color:col}})
    );
    tip.position.copy(vec.clone().multiplyScalar(8));
    tip.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0), vec.clone().normalize());
    scene.add(tip);
  }}
  axis(new THREE.Vector3(1,0,0), 0xff5555);
  axis(new THREE.Vector3(0,1,0), 0x55ff55);
  axis(new THREE.Vector3(0,0,1), 0x5555ff);

  // ----- Per-run objects ----------------------------------------------------
  function colorFor(run) {{
    if (run.tag === 'easy' && run.correct) return {{ line: 0x34c759, glow: 0x6dfaa3 }};
    if (run.tag === 'easy' && !run.correct) return {{ line: 0xff9f0a, glow: 0xffc97a }};
    if (run.tag === 'hard' && run.correct) return {{ line: 0x5e9cff, glow: 0x9cc4ff }};
    return {{ line: 0xff453a, glow: 0xff7a72 }};
  }}

  const trajectoryGroup = new THREE.Group();
  scene.add(trajectoryGroup);
  const runObjs = runs.map((run, idx) => {{
    const n = run.frames.length;
    const pos = new Float32Array(n * 3);
    const col = new Float32Array(n * 3);
    const c = new THREE.Color(colorFor(run).line);
    for (let i = 0; i < n; i++) {{
      pos[i*3+0] = run.frames[i].x;
      pos[i*3+1] = run.frames[i].y;
      pos[i*3+2] = run.frames[i].z;
      col[i*3+0] = c.r; col[i*3+1] = c.g; col[i*3+2] = c.b;
    }}
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
    geo.setDrawRange(0, 0);
    const line = new THREE.Line(geo,
      new THREE.LineBasicMaterial({{ vertexColors:true, transparent:true, opacity:0.9 }}));
    trajectoryGroup.add(line);

    // token dots
    const sphereGeo = new THREE.SphereGeometry(0.16, 8, 8);
    const sphere = new THREE.InstancedMesh(
      sphereGeo,
      new THREE.MeshBasicMaterial({{ color:colorFor(run).line, transparent:true, opacity:0.0 }}),
      n
    );
    const m = new THREE.Matrix4().makeScale(0, 0, 0);
    for (let i = 0; i < n; i++) sphere.setMatrixAt(i, m);
    sphere.instanceMatrix.needsUpdate = true;
    trajectoryGroup.add(sphere);

    // pulse
    const pulse = new THREE.Mesh(
      new THREE.SphereGeometry(0.5, 16, 16),
      new THREE.MeshBasicMaterial({{ color:colorFor(run).glow, transparent:true, opacity:0.0 }})
    );
    trajectoryGroup.add(pulse);

    // start marker
    const start = new THREE.Mesh(
      new THREE.SphereGeometry(0.3, 12, 12),
      new THREE.MeshBasicMaterial({{ color:colorFor(run).glow, transparent:true, opacity:0.9 }})
    );
    if (run.frames.length) {{
      start.position.set(run.frames[0].x, run.frames[0].y, run.frames[0].z);
    }}
    trajectoryGroup.add(start);

    return {{ run, line, sphere, pulse, start }};
  }});

  // ----- State + UI ---------------------------------------------------------
  let step = 0, playing = false, speed = 10, follow = true;
  let focusIdx = 0, singleMode = false;

  const $ = id => document.getElementById(id);
  const hudPrompt = $('hud-prompt'), hudStep = $('hud-step'),
        hudTok = $('hud-tok'), hudPpl = $('hud-ppl'),
        hudEnt = $('hud-entropy'), hudXyz = $('hud-xyz');

  function refresh() {{
    for (let i = 0; i < runObjs.length; i++) {{
      const obj = runObjs[i];
      const n = Math.min(step + 1, obj.run.frames.length);
      const dim = (!singleMode || focusIdx === i);
      obj.line.geometry.setDrawRange(0, n);
      obj.line.material.opacity = dim ? 0.9 : 0.08;
      const m = new THREE.Matrix4();
      for (let k = 0; k < obj.run.frames.length; k++) {{
        const f = obj.run.frames[k];
        if (k < n) {{
          const ppl = (f.ppl || 1);
          const sz = 0.05 + 0.16 * Math.min(1, (ppl - 1) / 4);
          m.makeScale(sz, sz, sz);
          m.setPosition(f.x, f.y, f.z);
        }} else {{
          m.makeScale(0, 0, 0);
        }}
        obj.sphere.setMatrixAt(k, m);
      }}
      obj.sphere.instanceMatrix.needsUpdate = true;
      obj.sphere.material.opacity = dim ? 0.85 : 0.05;
      if (n > 0) {{
        const f = obj.run.frames[n - 1];
        obj.pulse.position.set(f.x, f.y, f.z);
        obj.pulse.material.opacity = dim ? 0.85 : 0;
        obj.start.material.opacity = dim ? 0.9 : 0.15;
      }} else {{
        obj.pulse.material.opacity = 0;
      }}
    }}
    const fr = runs[focusIdx];
    const n2 = Math.min(step + 1, fr.frames.length);
    hudPrompt.textContent = fr.prompt.slice(0, 60) + (fr.prompt.length > 60 ? '…' : '');
    if (n2 > 0) {{
      const f = fr.frames[n2 - 1];
      hudTok.textContent = f.tok || '·';
      hudPpl.textContent = f.ppl != null ? f.ppl.toFixed(2) : '—';
      hudEnt.textContent = f.ent != null ? f.ent.toFixed(2) : '—';
      hudXyz.textContent = `${{f.x.toFixed(2)}}, ${{f.y.toFixed(2)}}, ${{f.z.toFixed(2)}}`;
    }}
    let html = '';
    for (let k = 0; k < n2; k++) {{
      const f = fr.frames[k];
      if (!f.tok) continue;
      const cls = f.sc ? 'self' : 't';
      html += `<span class="${{cls}}">${{esc(f.tok)}}</span>`;
    }}
    $('live-text').innerHTML = html;
    $('live-text').scrollTop = $('live-text').scrollHeight;
  }}

  function esc(s) {{
    return s.replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}})[c]);
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

  // build run list
  runs.forEach((r, i) => {{
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
      if (singleMode) {{
        if (focusIdx === i && singleMode) {{
          singleMode = false;
          $('single-btn').style.background = 'transparent';
          $('single-btn').style.color = 'var(--text)';
          focusOn(0);
          refresh();
          return;
        }}
      }}
      singleMode = true;
      $('single-btn').style.background = 'var(--accent)';
      $('single-btn').style.color = '#001a2c';
      focusOn(i);
    }});
    $('run-list').appendChild(div);
  }});

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

  // ----- Render loop --------------------------------------------------------
  let last = performance.now();
  function tick(now) {{
    const dt = (now - last) / 1000;
    last = now;
    if (playing) {{
      step += speed * dt;
      if (step >= maxLen - 1) {{
        step = maxLen - 1;
        playing = false;
        $('play-btn').textContent = '▶ Play';
      }}
      $('step').value = step;
      $('step-val').textContent = Math.floor(step);
      hudStep.textContent = Math.floor(step);
      refresh();
    }}
    const t = now * 0.001;
    for (const obj of runObjs) {{
      obj.pulse.scale.setScalar(1 + 0.18 * Math.sin(t * 6));
    }}
    if (follow) {{
      const obj = runObjs[focusIdx];
      const n = Math.min(Math.floor(step) + 1, obj.run.frames.length);
      if (n > 0) {{
        const f = obj.run.frames[n - 1];
        const target = new THREE.Vector3(f.x, f.y, f.z);
        const desired = target.clone().add(new THREE.Vector3(8, 6, 12));
        camera.position.lerp(desired, 0.04);
        controls.target.lerp(target, 0.06);
      }}
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
  console.log('[3d] ready', {{ runs: runs.length, maxLen, threeRev: THREE.REVISION }});
}})();
</script>
</body>
</html>
"""

with open(OUT / "view_standalone.html", "w", encoding="utf-8") as f:
    f.write(html)

print(f"wrote {OUT / 'view_standalone.html'} ({len(html) / 1024:.1f} KB)")
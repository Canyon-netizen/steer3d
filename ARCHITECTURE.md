# Architecture (Reasoning3D v0.2)

## Big picture

Reasoning3D is a **focused, minimal framework** for one job:

> Stream an LLM's hidden states during generation and render the
> resulting reasoning trajectory as a live 3-D animation in the
> browser.

The user owns the model's logic (including any vector-injection
behavior they want); the framework owns the wire protocol,
projection, animation, and UI.

## Component map

```
┌────────────────────────────────────────────────────────────┐
│                      Browser (Next.js)                      │
│                                                              │
│  app/page.tsx  ───>  lib/store.ts  (Zustand)                 │
│                       ├── frames[]  (rolling buffer)         │
│                       ├── latest                            │
│                       └── fullText                           │
│                                                              │
│                  ───>  lib/ws-client.ts  (WebSocket)           │
│                       └── ServerMessage dispatch              │
│                                                              │
│                  ───>  components/Scene3D.tsx (R3F)           │
│                       ├── TrajectoryRibbon  (smoothed path)  │
│                       ├── TokenParticles  (recent spheres)   │
│                       ├── CurrentTokenPulse (glowing ball)  │
│                       ├── DirectionArrow  (velocity hint)    │
│                       └── Axes / Stars                       │
│                                                              │
│                  ───>  components/ControlPanel.tsx           │
│                       ├── prompt textarea                    │
│                       ├── Run / Pause / Reset                 │
│                       ├── Layer dropdown                     │
│                       └── Speed slider                       │
│                                                              │
│                  ───>  components/TokenStreamPanel.tsx        │
│                       └── running text with highlights      │
└────────────────────────────────────────────────────────────┘
                              ↕ WebSocket JSON
┌────────────────────────────────────────────────────────────┐
│                       Backend (FastAPI)                      │
│                                                              │
│  server.py                                                   │
│    ├──> WebSocket endpoint /ws                              │
│    ├──> SessionState per connection                          │
│    │     ├── layer, prompt, speed, paused, cancelled        │
│    │     ├── runner  (SyntheticRunner | HFTransformerRunner)│
│    │     └── projector (OnlinePCA)                          │
│    │                                                          │
│    └──> HTTP: GET /, GET /health                            │
│                                                              │
│  core/                                                       │
│    ├── protocol.py      Frame / ControlMessage              │
│    ├── projector.py     OnlinePCA / SketchUMAP              │
│    ├── activation.py    install_residual_add_hook           │
│    │                    get_residual_at_last_token          │
│    └── model_runner.py  SyntheticRunner / HFTransformerRunner│
│                                                              │
│  examples/                                                   │
│    ├── demo_synthetic.py   (CPU-only default)                │
│    └── demo_real_model.py   (HF + GPU + custom hooks)        │
└────────────────────────────────────────────────────────────┘
```

## Frame pipeline (token by token)

```
                                  ┌───────────────────────┐
                                  │   SyntheticRunner /   │
                                  │   HFTransformerRunner  │
                                  └──────────┬────────────┘
                                             │ generate token t
                                             ▼
                              ┌──────────────────────────────┐
                              │  [Optional] inject_vector()  │
                              │  → install_residual_add_hook │
                              │  → model forward (one token) │
                              │  → remove hook              │
                              └──────────┬───────────────────┘
                                         │
                                         ▼
                              ┌──────────────────────────────┐
                              │  Capture h_t at layer L       │
                              │  (residual stream, last tok)  │
                              └──────────┬───────────────────┘
                                         │
                                         ▼
                              ┌──────────────────────────────┐
                              │  Projector.update(h_t)         │
                              │  OnlinePCA: Welford + SVD     │
                              │  → 3-D Point3D (x, y, z)       │
                              └──────────┬───────────────────┘
                                         │
                                         ▼
                              ┌──────────────────────────────┐
                              │  Build Frame:                  │
                              │  - token text + id             │
                              │  - point                        │
                              │  - perplexity, entropy          │
                              │  - is_self_check (regex match)  │
                              │  - is_revisit (velocity reversal)│
                              └──────────┬───────────────────┘
                                         │
                                         ▼
                              ┌──────────────────────────────┐
                              │  WebSocket send JSON            │
                              │  Frontend ingests frame        │
                              └────────────────────────────────┘
```

The frontend just appends the 3-D point to a Catmull-Rom spline,
shows it as a colored ribbon, and adds a particle. The user sees
the path grow in real time.

## Extension points

| You want to... | Edit |
|----------------|------|
| Plug in your own model + tokenizer loop | `core/model_runner.py:HFTransformerRunner.stream()` |
| Use a different projection algorithm | `core/projector.py` (implement new class with `update()` + `reset()`) |
| Add a new control (e.g. toggle heatmap on/off) | `frontend/lib/frame-types.ts:ControlKind` + `frontend/components/ControlPanel.tsx` + `backend/server.py` dispatch |
| Capture from a different layer type (attention, MLP out) | add a new hook helper in `core/activation.py` |
| Use a different frontend framework | keep `protocol.py` + `server.py` unchanged; rewrite `frontend/` |

## Performance budget

| Stage | Target | Notes |
|-------|--------|-------|
| Backend: hook + capture + project + emit | < 50 ms | Easy on one A100 |
| WebSocket round-trip | < 5 ms | localhost |
| Frontend: receive + render | < 16 ms | One R3F frame @ 60 FPS |
| Total token-to-pixel | < 80 ms | Synthetic demo runs at ~20 Hz |

## What we deliberately do NOT do

- ❌ Compute steering vectors (you provide them or skip entirely).
- ❌ Train SAEs or run a projector on the client.
- ❌ Persist frames (everything is in-memory; restart loses data).
- ❌ Render text inside the 3D scene beyond the current-token label.

These are all reasonable extensions but were cut to keep the framework
small and runnable on a laptop.

## When to extend to a "real" pipeline

The synthetic runner is enough to validate the UI. To wire a real
LLM, replace the body of `HFTransformerRunner.stream()` with a
loop that:

1. Calls your `inject_vector(step_id, token)` to compute any
   steering signal (return `None` for none).
2. Installs the residual-add hook if needed.
3. Generates one token via the HF `generate()` API with a custom
   `LogitsProcessor` or `TextStreamer` (so you control pacing).
4. Removes the hook.
5. Captures the residual stream at the configured layer for the
   new last token.
6. Computes perplexity / entropy from the output logits.
7. Emits a Frame.

The frontend code does not need to change.

## Failure modes & recoveries

| Failure | What happens | Recovery |
|---------|--------------|----------|
| WebSocket disconnects | Frontend shows "disconnected" | `ws-client.ts` auto-reconnects with backoff |
| Model OOM | Server catches, sends `{kind:"error"}` | Frontend surfaces in top bar |
| Projector singularity (very few points) | Falls back to identity; subsequent refits stabilize | Avoid by sending at least 8 frames before switching tabs |
| User changes layer mid-stream | Frontend sends `set_layer`; server picks it up on next start | User needs to `reset` + `Run` to see the new layer's path |
| Speed = 4 (very fast) | Server emits faster than 60 FPS | Frontend still renders every frame; UI may drop intermediate ones |
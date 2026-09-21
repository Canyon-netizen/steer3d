# Steering3D Frontend

Next.js 14 + Three.js (via React Three Fiber) + Tailwind client
that renders streaming reasoning trajectories from the backend
in 3-D.

## Quick start

```bash
npm install
npm run dev
```

The dev server runs at <http://localhost:3000> and expects the
backend at `ws://localhost:8000/ws`. Override with
`NEXT_PUBLIC_WS_URL`.

## Layout

```
app/
├── layout.tsx           ← root layout (metadata + globals.css)
├── page.tsx             ← main page: Scene3D + ControlPanel + TopTokensPanel
└── globals.css          ← Tailwind + dark theme

components/
├── Scene3D.tsx           ← main Three.js scene (paths, dots, arrow, current token)
├── ControlPanel.tsx      ← prompt, preset, alpha slider, layer
├── TopTokensPanel.tsx    ← next-token distribution sidebar
└── Legend.tsx            ← small in-viewport legend

lib/
├── frame-types.ts        ← Frame / ControlMessage types
├── ws-client.ts          ← WebSocket client wrapper
└── store.ts              ← Zustand global state
```

## Customizing the 3D scene

`components/Scene3D.tsx` is intentionally small and well-commented.

To change the look:
- `PathLine` color → `color="..."`
- Trail dots: `TrailDots` size & opacity curves
- Current token: `CurrentToken` particle + label
- Steering arrow: `SteeringVectorArrow` shape (cylinder + cone)

## Connecting a different model backend

The frontend only cares about the WebSocket protocol. As long
as the server sends JSON `Frame` objects shaped like
`lib/frame-types.ts:Frame`, the visualization works.

For deployment:
1. Run the backend on a server (or localhost with port-forwarding)
2. Set `NEXT_PUBLIC_WS_URL` to that server's WebSocket URL
3. `npm run build && npm run start`

## Performance notes

- The scene uses `CatmullRomCurve3` to smooth the path; this is
  O(N) per frame but `getPoints` is called on every render.
  For very long trajectories (>500 points) consider sampling
  every Nth point before feeding into the curve.
- Each token currently adds one entry to the rolling buffer
  (`MAX_FRAMES = 600` in `lib/store.ts`). For larger windows,
  swap to a fixed-size ring buffer.

## Production hardening

Before shipping:
1. Move the WebSocket URL into env config.
2. Add a debounced reconnect with exponential backoff (already in
   `ws-client.ts`).
3. Set CORS allow-origins properly on the backend.
4. Throttle alpha updates — `ControlPanel` already debounces by
   80ms; tune for your server.
5. Add error reporting (Sentry, etc.).
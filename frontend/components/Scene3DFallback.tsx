"use client";

/**
 * 2-D fallback for the trajectory view.
 *
 * react-three-fiber's <Canvas> needs a WebGL context. When one is not
 * available -- older hardware, a hardened browser profile, or the
 * headless Chrome used for verification -- mounting <Canvas> does not
 * degrade gracefully: three.js throws during context creation and takes
 * the whole React tree down with it. So the caller checks support first
 * and only mounts this component when WebGL is genuinely absent.
 *
 * This is a real renderer, not a placeholder. It projects the same
 * points through the same normalisation the 3-D scene uses, draws the
 * same colours from the same `frameColor`, and supports drag-to-orbit
 * and wheel-to-zoom. The difference is that it is drawn by hand into a
 * 2-D context, so it costs nothing and works everywhere.
 *
 * `data-rendered-*` attributes are set on the canvas after each paint.
 * They are how the verification script proves the trajectory was
 * actually rasterised rather than merely present in the DOM.
 */

import { useEffect, useRef } from "react";

import { useApp } from "@/lib/store";
import type { Frame, Point3D } from "@/lib/frame-types";
import { frameColor, toCss } from "@/lib/frame-color";
import { PCA_WORLD_SCALE, WORLD_HALF_EXTENT, trajectoryExtent, extentFraction } from "@/lib/view-scale";

type Cam = { yaw: number; pitch: number; dist: number };

const FOV = (50 * Math.PI) / 180;
const MIN_DIST = 0.6;
const MAX_DIST = 12;

function scale(p: Point3D): Point3D {
  return {
    x: p.x / PCA_WORLD_SCALE,
    y: p.y / PCA_WORLD_SCALE,
    z: p.z / PCA_WORLD_SCALE,
  };
}

type Projected = { x: number; y: number; depth: number };

// --- Cohen-Sutherland segment clipping -----------------------------------
//
// Without this, a point that projects to x = 1e6 (which is what happens the
// moment the trajectory leaves the framed world box) still joins to its
// neighbour by a straight line, and the rasteriser draws that line straight
// across the viewport. The result is a screen full of thin anti-aliased
// streaks in the ribbon's colour -- at 21k "ribbon" pixels while 243 of 245
// points were off-screen. It looks like a rendered trajectory and measures
// like one, which is worse than an empty canvas.
//
// Clipping first makes off-screen means off-screen: the segment is cut to
// the viewport rectangle, or dropped when it misses entirely.
const OUT_LEFT = 1, OUT_RIGHT = 2, OUT_BOTTOM = 4, OUT_TOP = 8;

function outCode(x: number, y: number, xmin: number, ymin: number, xmax: number, ymax: number): number {
  let c = 0;
  if (x < xmin) c |= OUT_LEFT; else if (x > xmax) c |= OUT_RIGHT;
  if (y < ymin) c |= OUT_BOTTOM; else if (y > ymax) c |= OUT_TOP;
  return c;
}

type Seg = [number, number, number, number];

function clipSegment(x0: number, y0: number, x1: number, y1: number, xmin: number, ymin: number, xmax: number, ymax: number): Seg | null {
  let c0 = outCode(x0, y0, xmin, ymin, xmax, ymax);
  let c1 = outCode(x1, y1, xmin, ymin, xmax, ymax);
  for (let guard = 0; guard < 8; guard++) {
    if ((c0 | c1) === 0) return [x0, y0, x1, y1];
    if ((c0 & c1) !== 0) return null;
    const out = c0 || c1;
    let x: number, y: number;
    if (out & OUT_TOP) {
      if (y1 === y0) return null;
      x = x0 + ((x1 - x0) * (ymax - y0)) / (y1 - y0); y = ymax;
    } else if (out & OUT_BOTTOM) {
      if (y1 === y0) return null;
      x = x0 + ((x1 - x0) * (ymin - y0)) / (y1 - y0); y = ymin;
    } else if (out & OUT_RIGHT) {
      if (x1 === x0) return null;
      y = y0 + ((y1 - y0) * (xmax - x0)) / (x1 - x0); x = xmax;
    } else {
      if (x1 === x0) return null;
      y = y0 + ((y1 - y0) * (xmin - x0)) / (x1 - x0); x = xmin;
    }
    if (out === c0) { x0 = x; y0 = y; c0 = outCode(x0, y0, xmin, ymin, xmax, ymax); }
    else { x1 = x; y1 = y; c1 = outCode(x1, y1, xmin, ymin, xmax, ymax); }
  }
  return null;
}

function project(p: Point3D, cam: Cam, w: number, h: number): Projected | null {
  const cy = Math.cos(cam.yaw), sy = Math.sin(cam.yaw);
  const rx = p.x * cy - p.z * sy;
  const rz = p.x * sy + p.z * cy;
  const cp = Math.cos(cam.pitch), sp = Math.sin(cam.pitch);
  const ry = p.y * cp - rz * sp;
  const rz2 = p.y * sp + rz * cp;
  const depth = rz2 + cam.dist;
  if (depth <= 0.05) return null;
  const f = h / 2 / Math.tan(FOV / 2);
  return { x: w / 2 + (rx / depth) * f, y: h / 2 - (ry / depth) * f, depth };
}

export default function Scene3DFallback() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const camRef = useRef<Cam>({ yaw: 0.7, pitch: 0.35, dist: 3.4 });
  const framesRef = useRef<Frame[]>([]);
  const latestRef = useRef<Frame | null>(null);
  const layerRef = useRef<number>(14);

  useEffect(() => {
    const unsub = useApp.subscribe((s) => {
      framesRef.current = s.frames;
      latestRef.current = s.latest;
      layerRef.current = s.layer;
    });
    framesRef.current = useApp.getState().frames;
    latestRef.current = useApp.getState().latest;
    layerRef.current = useApp.getState().layer;
    return unsub;
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let lastPainted = 0;

    const draw = (now: number) => {
      raf = requestAnimationFrame(draw);
      if (now - lastPainted < 30) return; // ~33 fps is plenty here
      lastPainted = now;

      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = wrap.clientWidth, h = wrap.clientHeight;
      if (w === 0 || h === 0) return;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      const cam = camRef.current;
      const frames = framesRef.current;

      ctx.fillStyle = "#0a0d12";
      ctx.fillRect(0, 0, w, h);

      // -- ground grid, sized to the framed world box -------------------
      const E = WORLD_HALF_EXTENT;
      const g = E / 4;
      ctx.lineWidth = 1;
      for (let i = -4; i <= 4; i++) {
        const t = i * g;
        const a = project({ x: t, y: -E, z: -E }, cam, w, h);
        const b = project({ x: t, y: -E, z: E }, cam, w, h);
        if (a && b) {
          ctx.strokeStyle = i === 0 ? "#2a3441" : "#161a22";
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        }
        const c = project({ x: -E, y: -E, z: t }, cam, w, h);
        const d = project({ x: E, y: -E, z: t }, cam, w, h);
        if (c && d) {
          ctx.strokeStyle = i === 0 ? "#2a3441" : "#161a22";
          ctx.beginPath(); ctx.moveTo(c.x, c.y); ctx.lineTo(d.x, d.y); ctx.stroke();
        }
      }

      // -- axis triad -----------------------------------------------------
      const axes: [Point3D, string][] = [
        [{ x: E * 1.15, y: -E, z: -E }, "#ff5555"],
        [{ x: -E, y: E * 1.15, z: -E }, "#55ff55"],
        [{ x: -E, y: -E, z: E * 1.15 }, "#5555ff"],
      ];
      for (const [tip, color] of axes) {
        const o = project({ x: -E, y: -E, z: -E }, cam, w, h);
        const t = project(tip, cam, w, h);
        if (!o || !t) continue;
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.moveTo(o.x, o.y); ctx.lineTo(t.x, t.y); ctx.stroke();
      }

      let painted = 0;
      let onScreen = 0;
      const pts: (Projected & { f: Frame })[] = [];
      for (const f of frames) {
        const p = project(scale(f.point), cam, w, h);
        if (!p) continue;
        painted++;
        if (p.x >= -40 && p.x <= w + 40 && p.y >= -40 && p.y <= h + 40) onScreen++;
        pts.push({ ...p, f });
      }

      // -- trajectory ribbon, one segment per adjacent pair ---------------
      // Clipped to the viewport: see clipSegment. An unclipped segment
      // joining a visible point to one projected at x=1e6 paints a streak
      // right across the canvas, which reads as a trajectory that is not
      // there.
      ctx.lineWidth = 2.4;
      ctx.lineCap = "round";
      for (let i = 0; i < pts.length - 1; i++) {
        const a = pts[i], b = pts[i + 1];
        const seg = clipSegment(a.x, a.y, b.x, b.y, 0, 0, w, h);
        if (!seg) continue;
        const c = frameColor(a.f);
        ctx.strokeStyle = toCss(c);
        // Fade the oldest segments so the head reads as "now".
        const age = i / Math.max(1, pts.length - 1);
        ctx.globalAlpha = 0.15 + 0.8 * age;
        ctx.beginPath(); ctx.moveTo(seg[0], seg[1]); ctx.lineTo(seg[2], seg[3]); ctx.stroke();
      }
      ctx.globalAlpha = 1;

      // -- recent particles ----------------------------------------------
      const recent = pts.slice(-80);
      for (let i = 0; i < recent.length; i++) {
        const p = recent[i];
        const c = frameColor(p.f);
        ctx.globalAlpha = 0.25 + (i / Math.max(1, recent.length - 1)) * 0.75;
        ctx.fillStyle = toCss(c);
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.f.is_self_check ? 4 : 2, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;

      // -- current token pulse + label ------------------------------------
      const latest = latestRef.current;
      if (latest) {
        const p = project(scale(latest.point), cam, w, h);
        if (p) {
          const c = frameColor(latest);
          ctx.fillStyle = toCss(c);
          ctx.beginPath(); ctx.arc(p.x, p.y, 6, 0, Math.PI * 2); ctx.fill();
          ctx.strokeStyle = "rgba(253,224,71,0.7)";
          ctx.lineWidth = 2;
          ctx.beginPath(); ctx.arc(p.x, p.y, 10, 0, Math.PI * 2); ctx.stroke();
          const label = latest.token || "·";
          ctx.font = "13px ui-monospace, monospace";
          const tw = ctx.measureText(label).width;
          ctx.fillStyle = "rgba(0,0,0,0.8)";
          ctx.fillRect(p.x + 13, p.y - 22, tw + 12, 20);
          ctx.strokeStyle = "rgba(250,204,21,0.6)";
          ctx.lineWidth = 1;
          ctx.strokeRect(p.x + 13, p.y - 22, tw + 12, 20);
          ctx.fillStyle = "#fde68a";
          ctx.fillText(label, p.x + 19, p.y - 8);
        }
      }

      // -- proof-of-paint attributes --------------------------------------
      const ext = trajectoryExtent(frames.map((f) => f.point));
      const frac = extentFraction(ext);
      canvas.setAttribute("data-rendered-points", String(painted));
      canvas.setAttribute("data-on-screen-points", String(onScreen));
      canvas.setAttribute("data-layer", String(layerRef.current));
      canvas.setAttribute("data-extent-maxabs", ext ? ext.maxAbs.toFixed(1) : "");
      canvas.setAttribute("data-extent-fraction", frac == null ? "" : frac.toFixed(4));
      canvas.setAttribute("data-has-entropy", String(frames.some((f) => f.entropy != null)));
      canvas.setAttribute("data-painted", "1");
    };

    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, []);

  // -- interaction: drag to orbit, wheel to zoom -------------------------
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let dragging = false;
    let lastX = 0, lastY = 0;

    const down = (e: PointerEvent) => {
      dragging = true; lastX = e.clientX; lastY = e.clientY;
      canvas.setPointerCapture(e.pointerId);
    };
    const move = (e: PointerEvent) => {
      if (!dragging) return;
      const cam = camRef.current;
      cam.yaw -= (e.clientX - lastX) * 0.008;
      cam.pitch = Math.max(-1.45, Math.min(1.45, cam.pitch + (e.clientY - lastY) * 0.008));
      lastX = e.clientX; lastY = e.clientY;
    };
    const up = (e: PointerEvent) => {
      dragging = false;
      if (canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId);
    };
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      const cam = camRef.current;
      cam.dist = Math.max(MIN_DIST, Math.min(MAX_DIST, cam.dist * (1 + Math.sign(e.deltaY) * 0.1)));
    };
    canvas.addEventListener("pointerdown", down);
    canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerup", up);
    canvas.addEventListener("pointercancel", up);
    canvas.addEventListener("wheel", wheel, { passive: false });
    return () => {
      canvas.removeEventListener("pointerdown", down);
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerup", up);
      canvas.removeEventListener("pointercancel", up);
      canvas.removeEventListener("wheel", wheel);
    };
  }, []);

  return (
    <div ref={wrapRef} className="absolute inset-0" data-testid="scene3d-fallback">
      <canvas ref={canvasRef} className="block w-full h-full cursor-grab active:cursor-grabbing" />
      <div className="absolute top-3 left-3 px-2 py-1 rounded bg-black/60 border border-border text-[11px] text-gray-400">
        2D 降级渲染（此环境无 WebGL）· 拖动旋转 · 滚轮缩放
      </div>
    </div>
  );
}

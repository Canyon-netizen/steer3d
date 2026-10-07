"use client";

/**
 * 3-D scene: the model's reasoning trajectory unfolds in front of
 * the user as a glowing ribbon. Each generated token drops a
 * particle along the path; "self-check" moments pulse orange.
 *
 * Design goals:
 *  - Smooth animation between frame updates
 *  - Color encodes entropy / perplexity (confidence heat)
 *  - Current token "pops" out as a labeled particle
 *  - The path's direction shows the *velocity* of reasoning
 *  - Self-check + revisit flags highlight interesting moments
 */

import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Stars, Html, Line } from "@react-three/drei";
import { useMemo, useRef, useState } from "react";
import * as THREE from "three";

import { useApp } from "@/lib/store";
import type { Frame, Point3D } from "@/lib/frame-types";
import { frameColor } from "@/lib/frame-color";
import { PCA_WORLD_SCALE, WORLD_HALF_EXTENT } from "@/lib/view-scale";
import { useWebGLSupport } from "@/lib/use-webgl";
import Scene3DFallback from "./Scene3DFallback";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------


function framesToPoints(frames: Frame[]): Point3D[] {
  // Raw PCA units -> world units. See lib/view-scale.ts for why this
  // single shared divisor is applied here rather than server-side: the
  // live backend and the replay backend send very different magnitudes,
  // and only the renderer sees both.
  return frames.map((f) => ({
    x: f.point.x / PCA_WORLD_SCALE,
    y: f.point.y / PCA_WORLD_SCALE,
    z: f.point.z / PCA_WORLD_SCALE,
  }));
}

function buildSmoothPath(points: Point3D[]): THREE.Vector3[] {
  if (points.length === 0) return [];
  const v3 = points.map((p) => new THREE.Vector3(p.x, p.y, p.z));
  if (v3.length < 4) return v3;
  // CatmullRom for smoothness; centripetal tension avoids overshoot
  const curve = new THREE.CatmullRomCurve3(v3, false, "centripetal", 0.5);
  return curve.getPoints(Math.max(60, v3.length * 3));
}

/** Shared colour rules; `null` entropy is grey, never a confident teal. */
function colorOf(f: Frame | undefined): THREE.Color {
  const c = frameColor(f);
  return new THREE.Color(c.r, c.g, c.b);
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------


function TrajectoryRibbon({ frames }: { frames: Frame[] }) {
  const smoothed = useMemo(() => buildSmoothPath(framesToPoints(frames)), [frames]);

  if (smoothed.length < 2) return null;

  // Build a colored ribbon: one segment per pair, with a per-vertex
  // color derived from the entropy of the source frame.
  const positions: number[] = [];
  const colors: number[] = [];
  const n = frames.length;
  for (let i = 0; i < smoothed.length - 1; i++) {
    // Map each smoothed sample back to a coarse frame index.
    const fIdx = Math.min(n - 1, Math.floor((i / (smoothed.length - 1)) * (n - 1)));
    const frame = frames[fIdx];
    const c = colorOf(frame);
    const a = smoothed[i];
    const b = smoothed[i + 1];
    positions.push(a.x, a.y, a.z, b.x, b.y, b.z);
    colors.push(c.r, c.g, c.b, c.r, c.g, c.b);
  }

  return (
    <Line
      points={positions.reduce<[number, number, number][]>((acc, _v, i) => {
        if (i % 3 === 0) acc.push([positions[i], positions[i + 1], positions[i + 2]]);
        return acc;
      }, [])}
      vertexColors={colors.reduce<[number, number, number][]>((acc, _v, i) => {
        if (i % 3 === 0) acc.push([colors[i], colors[i + 1], colors[i + 2]]);
        return acc;
      }, [])}
      lineWidth={2.4}
      transparent
      opacity={0.92}
    />
  );
}

function TokenParticles({ frames }: { frames: Frame[] }) {
  // Render the last 80 points as small spheres. Older ones fade out.
  const recent = frames.slice(-80);
  // 点一颗珠子 → 逐层推导链跳到那一步。`focusedStep` 是链与 3D 之间唯一的
  // 共享状态（lib/store），所以反向（链跳步 → 3D 高亮）也已经自动成立。
  const focusedStep = useApp((s) => s.focusedStep);
  const setFocusedStep = useApp((s) => s.setFocusedStep);
  const [hoverId, setHoverId] = useState<number | null>(null);
  return (
    <group>
      {recent.map((f, i) => {
        const c = colorOf(f);
        const opacity = 0.25 + (i / recent.length) * 0.75;
        // 聚焦态用**几何**放大而不是只改颜色：颜色在暗背景下不好判读，
        // 而半径是可以量的（判据读 getBoundingClientRect 不管用时，
        // 这里靠 <Html> 徽章把状态暴露到真实 DOM 上）。
        const isFocused = focusedStep === f.step_id;
        const isHover = hoverId === f.step_id;
        const r = isFocused ? 0.028 : isHover ? 0.02 : 0.012;
        return (
          <mesh
            key={f.step_id}
            position={[
              f.point.x / PCA_WORLD_SCALE,
              f.point.y / PCA_WORLD_SCALE,
              f.point.z / PCA_WORLD_SCALE,
            ]}
            onClick={(e) => {
              e.stopPropagation();
              setFocusedStep(f.step_id);
            }}
            onPointerOver={(e) => {
              e.stopPropagation();
              setHoverId(f.step_id);
              document.body.style.cursor = "pointer";
            }}
            onPointerOut={() => {
              setHoverId(null);
              document.body.style.cursor = "";
            }}
          >
            <sphereGeometry args={[r, 12, 12]} />
            <meshStandardMaterial
              color={isFocused ? "#f9fafb" : c}
              emissive={isFocused ? "#f9fafb" : c}
              emissiveIntensity={isFocused ? 3.0 : 0.6}
              transparent
              opacity={opacity}
            />
          </mesh>
        );
      })}
      {/* 聚焦态的标签。drei 的 <Html> 是真实 DOM，所以判据能读到它 ——
          WebGL 画的东西读不到，这是唯一能把 3D 状态交给判据的通道。
          三个分支必须都出声：
            · 步号在窗口内  → 贴着珠子显示 token
            · 步号在窗口外  → 明说不在窗口、已加载多少步
            · 没有聚焦      → 只报已加载步数
          静默什么都不显示是最坏的一种：读者会以为联动坏了。 */}
      <Html
        position={[0, WORLD_HALF_EXTENT * 0.62, 0]}
        distanceFactor={undefined}
        style={{ pointerEvents: "none" }}
      >
        <div
          data-scene-loaded={frames.length}
          data-scene-window-low={recent.length ? recent[0].step_id : ""}
          data-scene-window-high={recent.length ? recent[recent.length - 1].step_id : ""}
          data-scene-focus-state={
            focusedStep == null
              ? "none"
              : recent.some((x) => x.step_id === focusedStep)
              ? "in-window"
              : "out-of-window"
          }
          className="px-1.5 py-0.5 rounded bg-black/70 border border-border text-[9px] font-mono whitespace-nowrap text-gray-400"
        >
          3D 已加载 {frames.length} 步
          {recent.length > 0 && (
            <>
              {" "}· 可见 {recent[0].step_id}–{recent[recent.length - 1].step_id}
            </>
          )}
          {focusedStep != null &&
            !recent.some((x) => x.step_id === focusedStep) && (
              <span className="text-amber-500" data-scene-focus-miss={focusedStep}>
                {" "}· 第 {focusedStep} 步不在 3D 窗口内
              </span>
            )}
        </div>
      </Html>
      {focusedStep != null &&
        (() => {
          const f = recent.find((x) => x.step_id === focusedStep);
          if (!f) return null;
          return (
            <Html
              position={[
                f.point.x / PCA_WORLD_SCALE,
                f.point.y / PCA_WORLD_SCALE,
                f.point.z / PCA_WORLD_SCALE,
              ]}
              distanceFactor={undefined}
              style={{ pointerEvents: "none" }}
            >
              <div
                data-scene-focus="1"
                data-scene-focus-step={f.step_id}
                data-scene-focus-token={f.token ?? ""}
                className="px-1.5 py-0.5 rounded bg-black/80 border border-accent text-[9px] font-mono whitespace-nowrap"
              >
                step {f.step_id} · {f.token || "·"}
              </div>
            </Html>
          );
        })()}
    </group>
  );
}

function CurrentTokenPulse({ latest }: { latest: Frame | null }) {
  const groupRef = useRef<THREE.Group>(null);

  useFrame(({ clock }) => {
    if (!groupRef.current) return;
    const t = clock.getElapsedTime();
    groupRef.current.scale.setScalar(1 + 0.1 * Math.sin(t * 5));
  });

  if (!latest) {
    return (
      <group>
        <mesh>
          <sphereGeometry args={[0.012, 16, 16]} />
          <meshStandardMaterial color="#9ca3af" transparent opacity={0.3} />
        </mesh>
      </group>
    );
  }

  const c = colorOf(latest);
  const pos = [
    latest.point.x / PCA_WORLD_SCALE,
    latest.point.y / PCA_WORLD_SCALE,
    latest.point.z / PCA_WORLD_SCALE,
  ] as [number, number, number];

  return (
    <group ref={groupRef} position={pos}>
      <mesh>
        <sphereGeometry args={[0.055, 24, 24]} />
        <meshStandardMaterial color={c} emissive={c} emissiveIntensity={2.0} />
      </mesh>
      {/* ⚠⚠ `distanceFactor={undefined}`（固定屏幕尺寸）是**刻意**的。
        原来这里是 3 —— 标签随相机距离等比缩放，于是**读者越拉近视轨迹、
        标签越大**：实测把相机拉近后这个黄框大到把轨迹本身盖住，
        而拉近恰恰是唯一能看清轨迹的办法（浅层只占画面宽度 6.6%，
        原因见 lib/view-scale.ts：那是模型的真实方差比，不是画错）。
        ⇒ HUD 必须锁在屏幕尺寸上，锚点跟着 3D 位置走、大小不变。
        同一个文件里那个「3D 已加载 N 步」徽章本来就是这么写的
        （distanceFactor={undefined}），这里是唯一的例外。 */}
      <Html distanceFactor={undefined} position={[0.12, 0.12, 0]}>
        <div
          data-scene-token-badge="1"
          className="px-2 py-1 rounded bg-black/80 border border-yellow-400/60 text-[11px] font-mono whitespace-nowrap text-yellow-100"
        >
          {latest.token || "·"}
        </div>
      </Html>
    </group>
  );
}

function DirectionArrow({ frames }: { frames: Frame[] }) {
  // Visualize the *instantaneous direction* of reasoning — the
  // velocity from the last few points, as a small arrow at the tip.
  const groupRef = useRef<THREE.Group>(null);

  useFrame(({ clock }) => {
    if (!groupRef.current) return;
    groupRef.current.rotation.z = Math.sin(clock.getElapsedTime() * 0.6) * 0.05;
  });

  const tail = frames[frames.length - 3];
  const head = frames[frames.length - 1];
  if (!tail || !head) return null;

  const S = PCA_WORLD_SCALE;
  const start = new THREE.Vector3(tail.point.x / S, tail.point.y / S, tail.point.z / S);
  const end = new THREE.Vector3(head.point.x / S, head.point.y / S, head.point.z / S);
  const dir = end.clone().sub(start);
  const length = Math.max(0.001, dir.length());
  const mid = start.clone().add(end).multiplyScalar(0.5);
  const orientation = new THREE.Vector3(0, 1, 0);
  const quaternion = new THREE.Quaternion().setFromUnitVectors(orientation, dir.clone().normalize());

  return (
    <group position={mid.toArray() as [number, number, number]} quaternion={quaternion}>
      <mesh position={[0, 0, 0]}>
        <cylinderGeometry args={[0.004, 0.004, length, 8]} />
        <meshStandardMaterial color="#9ca3af" emissive="#9ca3af" emissiveIntensity={0.4} />
      </mesh>
      <mesh position={[0, length / 2, 0]}>
        <coneGeometry args={[0.014, 0.035, 12]} />
        <meshStandardMaterial color="#9ca3af" emissive="#9ca3af" emissiveIntensity={0.6} />
      </mesh>
    </group>
  );
}

function Axes() {
  const E = WORLD_HALF_EXTENT;
  return (
    <group>
      <mesh>
        <sphereGeometry args={[0.014, 12, 12]} />
        <meshStandardMaterial color="#9ca3af" transparent opacity={0.4} />
      </mesh>
      <gridHelper args={[E * 2, 12, "#1f2630", "#161a22"]} />
      {/* RGB axis triad */}
      <mesh position={[E * 0.95, 0, 0]} rotation={[0, 0, -Math.PI / 2]}>
        <coneGeometry args={[0.014, 0.06, 8]} />
        <meshStandardMaterial color="#ff5555" />
      </mesh>
      <mesh position={[0, E * 0.95, 0]}>
        <coneGeometry args={[0.014, 0.06, 8]} />
        <meshStandardMaterial color="#55ff55" />
      </mesh>
      <mesh position={[0, 0, E * 0.95]} rotation={[Math.PI / 2, 0, 0]}>
        <coneGeometry args={[0.014, 0.06, 8]} />
        <meshStandardMaterial color="#5555ff" />
      </mesh>
    </group>
  );
}

// ---------------------------------------------------------------------------
// Main scene
// ---------------------------------------------------------------------------


function Scene3DCanvas() {
  const frames = useApp((s) => s.frames);
  const latest = useApp((s) => s.latest);

  return (
    // Framed for the normalised world box [-1,1]^3: at distance ~4.1 with
    // fov 50 the visible half-height is ~1.9, so the deepest layer fills
    // the frame and shallower ones read as proportionally smaller.
    <Canvas camera={{ position: [2.2, 1.8, 3.0], fov: 50 }} dpr={[1, 2]}>
      <color attach="background" args={["#0a0d12"]} />
      <ambientLight intensity={0.45} />
      <pointLight position={[4, 4, 4]} intensity={0.8} />
      <pointLight position={[-4, -3, -4]} intensity={0.4} color="#9c27b0" />

      <Stars radius={8} depth={20} count={800} factor={1.2} fade speed={0.4} />

      <Axes />

      <TrajectoryRibbon frames={frames} />
      <TokenParticles frames={frames} />
      <DirectionArrow frames={frames} />
      <CurrentTokenPulse latest={latest} />

      <OrbitControls enableDamping dampingFactor={0.06} makeDefault />
    </Canvas>
  );
}

export default function Scene3D() {
  // Gating here, not inside Scene3DCanvas: <Canvas> throws while
  // creating a missing context and unwinds the whole React tree, so it
  // must never be mounted in an environment that cannot give it one.
  const webgl = useWebGLSupport();

  if (webgl === null) {
    return <div className="absolute inset-0" data-testid="scene3d-probing" />;
  }
  if (!webgl) {
    return <Scene3DFallback />;
  }
  return (
    <div className="absolute inset-0" data-testid="scene3d-webgl">
      <Scene3DCanvas />
    </div>
  );
}
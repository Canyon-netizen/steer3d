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
import { useMemo, useRef } from "react";
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
  return (
    <group>
      {recent.map((f, i) => {
        const c = colorOf(f);
        const opacity = 0.25 + (i / recent.length) * 0.75;
        return (
          <mesh
            key={f.step_id}
            position={[
              f.point.x / PCA_WORLD_SCALE,
              f.point.y / PCA_WORLD_SCALE,
              f.point.z / PCA_WORLD_SCALE,
            ]}
          >
            <sphereGeometry args={[0.012, 8, 8]} />
            <meshStandardMaterial
              color={c}
              emissive={c}
              emissiveIntensity={0.6}
              transparent
              opacity={opacity}
            />
          </mesh>
        );
      })}
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
      <Html distanceFactor={3} position={[0.12, 0.12, 0]}>
        <div className="px-2.5 py-1.5 rounded-lg bg-black/80 border border-yellow-400/60 text-sm font-mono whitespace-nowrap text-yellow-100 shadow-lg">
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
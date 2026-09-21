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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------


function framesToPoints(frames: Frame[]): Point3D[] {
  return frames.map((f) => f.point);
}

function entropyToColor(entropy: number | null | undefined): THREE.Color {
  // Map entropy in [0, 3] to a heat colormap.
  // Low entropy (confident) -> blue. High entropy (uncertain) -> red.
  const e = Math.max(0, Math.min(3, entropy ?? 1.5));
  const t = e / 3;
  // simple gradient: blue -> cyan -> green -> yellow -> red
  const r = Math.min(1, t * 2);
  const g = Math.min(1, 1 - Math.abs(t - 0.5) * 2);
  const b = Math.min(1, (1 - t) * 2);
  return new THREE.Color(r, g, b);
}

function selfCheckColor(): THREE.Color {
  return new THREE.Color(1.0, 0.6, 0.2);
}

function buildSmoothPath(points: Point3D[]): THREE.Vector3[] {
  if (points.length === 0) return [];
  const v3 = points.map((p) => new THREE.Vector3(p.x, p.y, p.z));
  if (v3.length < 4) return v3;
  // CatmullRom for smoothness; centripetal tension avoids overshoot
  const curve = new THREE.CatmullRomCurve3(v3, false, "centripetal", 0.5);
  return curve.getPoints(Math.max(60, v3.length * 3));
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
    const c = frame?.is_self_check
      ? selfCheckColor()
      : entropyToColor(frame?.entropy);
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
        const c = f.is_self_check
          ? selfCheckColor()
          : entropyToColor(f.entropy);
        const opacity = 0.25 + (i / recent.length) * 0.75;
        return (
          <mesh key={f.step_id} position={[f.point.x, f.point.y, f.point.z]}>
            <sphereGeometry args={[0.05, 8, 8]} />
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
          <sphereGeometry args={[0.05, 16, 16]} />
          <meshStandardMaterial color="#9ca3af" transparent opacity={0.3} />
        </mesh>
      </group>
    );
  }

  const c = latest.is_self_check ? selfCheckColor() : entropyToColor(latest.entropy);
  const pos = [latest.point.x, latest.point.y, latest.point.z] as [number, number, number];

  return (
    <group ref={groupRef} position={pos}>
      <mesh>
        <sphereGeometry args={[0.22, 24, 24]} />
        <meshStandardMaterial color={c} emissive={c} emissiveIntensity={2.0} />
      </mesh>
      <Html distanceFactor={5} position={[0.3, 0.3, 0]}>
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

  const start = new THREE.Vector3(tail.point.x, tail.point.y, tail.point.z);
  const end = new THREE.Vector3(head.point.x, head.point.y, head.point.z);
  const dir = end.clone().sub(start);
  const length = Math.max(0.001, dir.length());
  const mid = start.clone().add(end).multiplyScalar(0.5);
  const orientation = new THREE.Vector3(0, 1, 0);
  const quaternion = new THREE.Quaternion().setFromUnitVectors(orientation, dir.clone().normalize());

  return (
    <group position={mid.toArray() as [number, number, number]} quaternion={quaternion}>
      <mesh position={[0, 0, 0]}>
        <cylinderGeometry args={[0.012, 0.012, length, 8]} />
        <meshStandardMaterial color="#9ca3af" emissive="#9ca3af" emissiveIntensity={0.4} />
      </mesh>
      <mesh position={[0, length / 2, 0]}>
        <coneGeometry args={[0.04, 0.1, 12]} />
        <meshStandardMaterial color="#9ca3af" emissive="#9ca3af" emissiveIntensity={0.6} />
      </mesh>
    </group>
  );
}

function Axes() {
  return (
    <group>
      <mesh>
        <sphereGeometry args={[0.04, 12, 12]} />
        <meshStandardMaterial color="#9ca3af" transparent opacity={0.4} />
      </mesh>
      <gridHelper args={[6, 12, "#1f2630", "#161a22"]} />
      {/* RGB axis triad */}
      <mesh position={[0.5, 0, 0]} rotation={[0, 0, -Math.PI / 2]}>
        <coneGeometry args={[0.04, 0.18, 8]} />
        <meshStandardMaterial color="#ff5555" />
      </mesh>
      <mesh position={[0, 0.5, 0]}>
        <coneGeometry args={[0.04, 0.18, 8]} />
        <meshStandardMaterial color="#55ff55" />
      </mesh>
      <mesh position={[0, 0, 0.5]} rotation={[Math.PI / 2, 0, 0]}>
        <coneGeometry args={[0.04, 0.18, 8]} />
        <meshStandardMaterial color="#5555ff" />
      </mesh>
    </group>
  );
}

// ---------------------------------------------------------------------------
// Main scene
// ---------------------------------------------------------------------------


export default function Scene3D() {
  const frames = useApp((s) => s.frames);
  const latest = useApp((s) => s.latest);

  return (
    <Canvas camera={{ position: [5, 4, 7], fov: 50 }}>
      <color attach="background" args={["#0a0d12"]} />
      <ambientLight intensity={0.45} />
      <pointLight position={[10, 10, 10]} intensity={0.8} />
      <pointLight position={[-10, -8, -10]} intensity={0.4} color="#9c27b0" />

      <Stars radius={50} depth={50} count={1500} factor={3} fade speed={0.4} />

      <Axes />

      <TrajectoryRibbon frames={frames} />
      <TokenParticles frames={frames} />
      <DirectionArrow frames={frames} />
      <CurrentTokenPulse latest={latest} />

      <OrbitControls enableDamping dampingFactor={0.06} makeDefault />
    </Canvas>
  );
}
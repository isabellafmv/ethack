// The map. One Canvas, one point cloud, reused across all four views by
// swapping which three axes it reads (Task 4) -- there is deliberately no
// per-view component here.
//
// No CDN, no external fonts: axis identity is carried by the (always-legible,
// never-rotates) HTML axis pickers around the canvas, not by in-scene 3D
// text, which would otherwise pull a font from a network font loader and
// break the wifi-off rehearsal.
import { useMemo, useRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import type { CompanyScoreResult } from "../scoring/pipeline";
import type { WeightsState } from "../scoring/pipeline";
import type { Company } from "../scoring/types";
import type { ReferenceValues } from "../scoring/reference";
import { axisIsImputed, axisValue, type AxisSlot } from "./views";
import { divergingColor, referenceScoreForAxis } from "./referenceColor";

const HALF_EXTENT = 5;

function toPosition(value: number | null): number {
  if (value === null) return 0;
  return (value / 100) * (2 * HALF_EXTENT) - HALF_EXTENT;
}

export interface ScatterPoint {
  ticker: string;
  position: [number, number, number];
  color: string;
  opacity: number;
  radius: number;
  wireframe: boolean;
}

export const CAMERA_PRESETS = {
  isometric: { position: [12, 10, 12] as [number, number, number], target: [0, 0, 0] as [number, number, number] },
  front: { position: [0, 0, 18], target: [0, 0, 0] as [number, number, number] },
  top: { position: [0, 18, 0.001], target: [0, 0, 0] as [number, number, number] },
  side: { position: [18, 0, 0], target: [0, 0, 0] as [number, number, number] },
};
export type CameraPresetId = keyof typeof CAMERA_PRESETS;

function CameraRig({ preset }: { preset: CameraPresetId | null }) {
  const { camera, controls } = useThree() as unknown as { camera: THREE.Camera; controls: { target: THREE.Vector3; update: () => void } | null };
  const applied = useRef<CameraPresetId | null>(null);
  useFrame(() => {
    if (preset && preset !== applied.current) {
      const cfg = CAMERA_PRESETS[preset];
      camera.position.set(cfg.position[0], cfg.position[1], cfg.position[2]);
      if (controls) {
        controls.target.set(cfg.target[0], cfg.target[1], cfg.target[2]);
        controls.update();
      }
      applied.current = preset;
    }
  });
  return null;
}

function Axes() {
  // Simple colour-coded axis lines (X red, Y green, Z blue) -- the axis
  // pickers around the canvas carry the actual field identity in legible,
  // never-rotating HTML, so these only need to show orientation.
  const lines: [THREE.Vector3, THREE.Vector3, string][] = [
    [new THREE.Vector3(-HALF_EXTENT, 0, 0), new THREE.Vector3(HALF_EXTENT, 0, 0), "#ef4444"],
    [new THREE.Vector3(0, -HALF_EXTENT, 0), new THREE.Vector3(0, HALF_EXTENT, 0), "#22c55e"],
    [new THREE.Vector3(0, 0, -HALF_EXTENT), new THREE.Vector3(0, 0, HALF_EXTENT), "#3b82f6"],
  ];
  return (
    <>
      {lines.map(([a, b, color], i) => {
        const geom = new THREE.BufferGeometry().setFromPoints([a, b]);
        const material = new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.5 });
        return <primitive key={i} object={new THREE.Line(geom, material)} />;
      })}
    </>
  );
}

function Point({ point, onSelect }: { point: ScatterPoint; onSelect: (ticker: string) => void }) {
  return (
    <mesh
      position={point.position}
      onClick={(e) => { e.stopPropagation(); onSelect(point.ticker); }}
    >
      <sphereGeometry args={[point.radius, 16, 16]} />
      <meshStandardMaterial
        color={point.color}
        transparent
        opacity={point.opacity}
        wireframe={point.wireframe}
      />
    </mesh>
  );
}

export interface ScatterViewProps {
  companies: readonly Company[];
  scores: Map<string, CompanyScoreResult>;
  axes: [AxisSlot, AxisSlot, AxisSlot];
  visibleSectors: Set<string>;
  referenceBySector: Map<string, ReferenceValues>;
  weights: WeightsState;
  onSelectCompany: (ticker: string) => void;
  cameraPreset: CameraPresetId | null;
}

export function ScatterView({
  companies, scores, axes, visibleSectors, referenceBySector, weights, onSelectCompany, cameraPreset,
}: ScatterViewProps) {
  const points = useMemo<ScatterPoint[]>(() => {
    const marketCaps = companies
      .map((c) => (typeof c.fields.market_cap_usd?.v === "number" ? c.fields.market_cap_usd.v : null))
      .filter((v): v is number => v !== null && v > 0);
    const sqrtCaps = marketCaps.map(Math.sqrt);
    const minSqrt = sqrtCaps.length ? Math.min(...sqrtCaps) : 0;
    const maxSqrt = sqrtCaps.length ? Math.max(...sqrtCaps) : 1;
    const MIN_R = 0.06, MAX_R = 0.32;

    const out: ScatterPoint[] = [];
    for (const company of companies) {
      if (visibleSectors.size > 0 && !visibleSectors.has(company.sector)) continue;
      const result = scores.get(company.ticker);
      if (!result) continue;

      const values = axes.map((a) => axisValue(result, a));
      if (values.some((v) => v === null)) continue; // can't place a point missing a coordinate

      const refValues = referenceBySector.get(company.sector);
      const deltas = refValues
        ? axes.map((a, i) => {
            const ref = referenceScoreForAxis(a, refValues, weights);
            return ref === null ? null : (values[i] as number) - ref;
          })
        : [];
      const presentDeltas = deltas.filter((d): d is number => d !== null);
      const avgDelta = presentDeltas.length ? presentDeltas.reduce((a, b) => a + b, 0) / presentDeltas.length : null;

      const capRaw = typeof company.fields.market_cap_usd?.v === "number" ? company.fields.market_cap_usd.v : null;
      const sqrtCap = capRaw && capRaw > 0 ? Math.sqrt(capRaw) : minSqrt;
      const sizeT = maxSqrt > minSqrt ? (sqrtCap - minSqrt) / (maxSqrt - minSqrt) : 0.5;
      const radius = MIN_R + Math.max(0, Math.min(1, sizeT)) * (MAX_R - MIN_R);

      const isImputed = axes.some((a) => axisIsImputed(result, a));

      out.push({
        ticker: company.ticker,
        position: [toPosition(values[0]), toPosition(values[1]), toPosition(values[2])],
        color: divergingColor(avgDelta),
        opacity: 0.15 + Math.max(0, Math.min(1, company.confidence)) * 0.85,
        radius,
        wireframe: isImputed,
      });
    }
    return out;
  }, [companies, scores, axes, visibleSectors, referenceBySector, weights]);

  return (
    <Canvas camera={{ position: CAMERA_PRESETS.isometric.position, fov: 45 }}>
      <ambientLight intensity={0.7} />
      <pointLight position={[10, 10, 10]} intensity={0.6} />
      <Axes />
      {points.map((p) => (
        <Point key={p.ticker} point={p} onSelect={onSelectCompany} />
      ))}
      <OrbitControls makeDefault target={[0, 0, 0]} />
      <CameraRig preset={cameraPreset} />
    </Canvas>
  );
}

// The map. One Canvas, one point cloud, reused across all four views by
// swapping which three axes it reads (Task 4) -- there is deliberately no
// per-view component here.
//
// No CDN, no external fonts: axis identity is carried by the (always-legible,
// never-rotates) HTML axis pickers around the canvas, not by in-scene 3D
// text, which would otherwise pull a font from a network font loader and
// break the wifi-off rehearsal.
import { useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import type { CompanyScoreResult } from "../scoring/pipeline";
import type { WeightsState } from "../scoring/pipeline";
import type { Company } from "../scoring/types";
import type { ReferenceValues } from "../scoring/reference";
import { axisIsImputed, axisLabel, axisValue, type AxisSlot } from "./views";
import { divergingColor, referenceScoreForAxis } from "./referenceColor";
import { isSectorVisible } from "../state/useAppState";

// Palette-only axis identity: X = ink, Y = accent, Z = a faded shade of ink
// (rather than a third hue), matching AxisPickers' AXIS_COLORS.
const AXIS_COLORS = ["#000000", "#AAB644", "#000000"];
const AXIS_OPACITIES = [0.85, 0.9, 0.4];

const HALF_EXTENT = 5;
const DIMMED_OPACITY_FACTOR = 0.06; // how much a point fades when hovering a different sector's point

function toPosition(value: number | null): number {
  if (value === null) return 0;
  return (value / 100) * (2 * HALF_EXTENT) - HALF_EXTENT;
}

export interface ScatterPoint {
  ticker: string;
  sector: string;
  position: [number, number, number];
  color: string;
  opacity: number;
  radius: number;
  wireframe: boolean;
}

// Every preset is chosen so the two axes visible on screen both read
// "positive -> up/right", i.e. the best-scoring companies always end up
// toward the top-right corner, in every orthographic view, not just one:
//   - front (looking down -Z): X -> right, Y -> up. Default up=(0,1,0)
//     already gives this (X-right is the standard lookAt convention here).
//   - side: looking from -X (not +X) toward the origin, rather than +X,
//     is what puts +Z on the right instead of the left -- same default
//     up=(0,1,0), just viewed from the opposite side.
//   - top: looking from BELOW (-Y) rather than above, with an explicit
//     up=(0,0,1). Looking down from above can put +X-right or +Z-up, but
//     not both at once (it's a mirror-image choice) -- looking from below
//     is the one position+up pair that gives both simultaneously. Every
//     preset sets `up` explicitly (not just top) so switching between them
//     can't leave a stale up-vector from whichever was active before.
export const CAMERA_PRESETS = {
  isometric: { position: [12, 10, 12] as [number, number, number], target: [0, 0, 0] as [number, number, number], up: [0, 1, 0] as [number, number, number] },
  front: { position: [0, 0, 18], target: [0, 0, 0] as [number, number, number], up: [0, 1, 0] as [number, number, number] },
  top: { position: [0, -18, 0], target: [0, 0, 0] as [number, number, number], up: [0, 0, 1] as [number, number, number] },
  side: { position: [-18, 0, 0], target: [0, 0, 0] as [number, number, number], up: [0, 1, 0] as [number, number, number] },
};
export type CameraPresetId = keyof typeof CAMERA_PRESETS;

function CameraRig({ preset }: { preset: CameraPresetId | null }) {
  const { camera, controls } = useThree() as unknown as { camera: THREE.Camera; controls: { target: THREE.Vector3; update: () => void } | null };
  const applied = useRef<CameraPresetId | null>(null);
  useFrame(() => {
    if (preset && preset !== applied.current) {
      const cfg = CAMERA_PRESETS[preset];
      camera.position.set(cfg.position[0], cfg.position[1], cfg.position[2]);
      camera.up.set(cfg.up[0], cfg.up[1], cfg.up[2]);
      if (controls) {
        controls.target.set(cfg.target[0], cfg.target[1], cfg.target[2]);
        controls.update();
      }
      applied.current = preset;
    }
  });
  return null;
}

/** Renders a small canvas-drawn text label as a texture -- not @react-three/
 * drei's <Text> (troika-three-text), which needs its own font asset. This
 * uses the same system-font stack as the rest of the site (Arial Nova with
 * an Arial fallback) via the browser's native Canvas 2D text API: no network
 * fetch, no CDN, consistent with the "no in-scene text pulled from a font
 * loader" constraint this file has always had -- it just no longer means
 * "no in-scene text at all". */
function useLabelTexture(text: string, color: string): THREE.CanvasTexture {
  return useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 512;
    canvas.height = 128;
    const ctx = canvas.getContext("2d")!;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.font = "700 64px 'Arial Nova', Arial, Helvetica, sans-serif";
    ctx.fillStyle = color;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText(text, 6, canvas.height / 2);
    const texture = new THREE.CanvasTexture(canvas);
    texture.needsUpdate = true;
    return texture;
  }, [text, color]);
}

const AXIS_DIRS = ["x", "y", "z"] as const;
type AxisDir = (typeof AXIS_DIRS)[number];

/** One axis: a thick cylinder shaft, a cone arrowhead at the positive end,
 * and a floating text label just past the tip. */
function Axis({ dir, color, opacity, label }: { dir: AxisDir; color: string; opacity: number; label: string }) {
  const rotation: [number, number, number] =
    dir === "x" ? [0, 0, -Math.PI / 2] : dir === "z" ? [Math.PI / 2, 0, 0] : [0, 0, 0];
  const tip: [number, number, number] =
    dir === "x" ? [HALF_EXTENT, 0, 0] : dir === "z" ? [0, 0, HALF_EXTENT] : [0, HALF_EXTENT, 0];
  const labelPos: [number, number, number] =
    dir === "x" ? [HALF_EXTENT + 0.7, 0, 0] : dir === "z" ? [0, 0, HALF_EXTENT + 0.7] : [0, HALF_EXTENT + 0.7, 0];
  const texture = useLabelTexture(label, color);

  return (
    <>
      <mesh rotation={rotation}>
        <cylinderGeometry args={[0.035, 0.035, HALF_EXTENT * 2, 10]} />
        <meshBasicMaterial color={color} transparent opacity={opacity} />
      </mesh>
      <mesh position={tip} rotation={rotation}>
        <coneGeometry args={[0.11, 0.26, 10]} />
        <meshBasicMaterial color={color} transparent opacity={Math.min(1, opacity + 0.1)} />
      </mesh>
      <sprite position={labelPos} scale={[1.4, 0.35, 1]}>
        <spriteMaterial map={texture} transparent depthTest={false} />
      </sprite>
    </>
  );
}

function Axes({ axes }: { axes: [AxisSlot, AxisSlot, AxisSlot] }) {
  return (
    <>
      {AXIS_DIRS.map((dir, i) => (
        <Axis key={dir} dir={dir} color={AXIS_COLORS[i]} opacity={AXIS_OPACITIES[i]} label={axisLabel(axes[i])} />
      ))}
    </>
  );
}

function Point({
  point, dimmed, highlight, onSelect, onHoverSector, onHoverTicker, onUnhover,
}: {
  point: ScatterPoint;
  dimmed: boolean;
  /** Hovered and/or selected -- either makes the point glow, selection adds
   * the ring below so it stays visible after the pointer moves away (a
   * hover-only glow would vanish the moment you're not touching it). */
  highlight: { hovered: boolean; selected: boolean };
  onSelect: (ticker: string) => void;
  onHoverSector: (sector: string) => void;
  onHoverTicker: (ticker: string | null) => void;
  onUnhover: () => void;
}) {
  const isHighlighted = highlight.hovered || highlight.selected;
  const effectiveOpacity = dimmed && !isHighlighted ? point.opacity * DIMMED_OPACITY_FACTOR : 1;
  // Brighter, not a new hue: emissive uses the point's own colour, so a
  // highlighted point reads as "this one, lit up" rather than introducing
  // a fourth colour into a palette that's deliberately only ever three.
  const radius = point.radius * (highlight.selected ? 1.6 : highlight.hovered ? 1.35 : 1);
  const emissiveIntensity = highlight.selected ? 1.6 : highlight.hovered ? 1.1 : 0;
  return (
    <group>
      <mesh
        position={point.position}
        onClick={(e) => { e.stopPropagation(); onSelect(point.ticker); }}
        onPointerOver={(e) => { e.stopPropagation(); onHoverSector(point.sector); onHoverTicker(point.ticker); }}
        onPointerOut={(e) => { e.stopPropagation(); onHoverTicker(null); onUnhover(); }}
      >
        <sphereGeometry args={[radius, 16, 16]} />
        <meshStandardMaterial
          color={point.color}
          transparent
          opacity={effectiveOpacity}
          wireframe={point.wireframe}
          emissive={point.color}
          emissiveIntensity={emissiveIntensity}
        />
      </mesh>
      {highlight.selected && (
        <mesh position={point.position} rotation={[Math.PI / 2, 0, 0]}>
          <ringGeometry args={[radius * 1.6, radius * 1.9, 32]} />
          <meshBasicMaterial color="#AAB644" transparent opacity={0.9} side={THREE.DoubleSide} depthTest={false} />
        </mesh>
      )}
    </group>
  );
}

export interface ScatterViewProps {
  companies: readonly Company[];
  scores: Map<string, CompanyScoreResult>;
  axes: [AxisSlot, AxisSlot, AxisSlot];
  visibleSectors: Set<string>;
  referenceBySector: Map<string, ReferenceValues>;
  weights: WeightsState | Map<string, WeightsState>;
  onSelectCompany: (ticker: string) => void;
  cameraPreset: CameraPresetId | null;
  /** The company currently open in DetailPanel, if any -- its point gets
   * the ring highlight below so "which point did I click" stays visible
   * even after the pointer moves away (unlike hover, which is transient). */
  selectedTicker: string | null;
}

export function ScatterView({
  companies, scores, axes, visibleSectors, referenceBySector, weights, onSelectCompany, cameraPreset, selectedTicker,
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
      if (!isSectorVisible(company.sector, visibleSectors)) continue;
      const result = scores.get(company.ticker);
      if (!result) continue;

      const values = axes.map((a) => axisValue(result, a));
      if (values.some((v) => v === null)) continue; // can't place a point missing a coordinate

      const refValues = referenceBySector.get(company.sector);
      const deltas = refValues
        ? axes.map((a, i) => {
            const ref = referenceScoreForAxis(a, refValues, weights, company.sector);
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
        sector: company.sector,
        position: [toPosition(values[0]), toPosition(values[1]), toPosition(values[2])],
        color: divergingColor(avgDelta),
        opacity: 0.15 + Math.max(0, Math.min(1, company.confidence)) * 0.85,
        radius,
        wireframe: isImputed,
      });
    }
    return out;
  }, [companies, scores, axes, visibleSectors, referenceBySector, weights]);

  // Hovering any point highlights its whole sector: every point from a
  // DIFFERENT sector fades to near-invisible, so the shape of "where does
  // this sector sit" pops out without a separate filter action. Which
  // point specifically is hovered is tracked separately (below) so THAT
  // one point can also glow, on top of the sector-level dim/fade.
  const [hoveredSector, setHoveredSector] = useState<string | null>(null);
  const [hoveredTicker, setHoveredTicker] = useState<string | null>(null);

  return (
    <Canvas camera={{ position: CAMERA_PRESETS.isometric.position, fov: 45 }}>
      <color attach="background" args={["#EDECEB"]} />
      <ambientLight intensity={0.9} />
      <pointLight position={[10, 10, 10]} intensity={0.5} />
      <Axes axes={axes} />
      {points.map((p) => (
        <Point
          key={p.ticker}
          point={p}
          dimmed={hoveredSector !== null && p.sector !== hoveredSector}
          highlight={{ hovered: p.ticker === hoveredTicker, selected: p.ticker === selectedTicker }}
          onSelect={onSelectCompany}
          onHoverSector={setHoveredSector}
          onHoverTicker={setHoveredTicker}
          onUnhover={() => setHoveredSector(null)}
        />
      ))}
      <OrbitControls makeDefault target={[0, 0, 0]} />
      <CameraRig preset={cameraPreset} />
    </Canvas>
  );
}

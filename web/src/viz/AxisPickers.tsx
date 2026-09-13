// Three axis dropdowns bound to the active view's registry entries (Task 4).
// Colour-matched to the 3D axis lines in ScatterView so the mapping between
// a line's shade and "X: <field>" is obvious without in-scene text. Being
// plain HTML, these stay legible at every camera angle -- they never rotate.
import { useEffect, useId, useRef, useState } from "react";
import { axisKey, axisLabel, axisDescription, axisWeightPct, type AxisSlot, type ViewConfig } from "./views";
import type { WeightsState } from "../scoring/pipeline";

// Palette-only axis identity: X = dark green, Y = ink, Z = a faded shade of
// ink (rather than a third hue) so the three stay visually distinct.
const AXIS_COLORS = ["#2C5628", "rgba(0,0,0,0.7)", "rgba(0,0,0,0.3)"];
const AXIS_NAMES = ["X", "Y", "Z"];

export function AxisPickers({
  view, axes, onChange, weights,
}: {
  view: ViewConfig;
  axes: [AxisSlot, AxisSlot, AxisSlot];
  onChange: (slot: 0 | 1 | 2, axis: AxisSlot) => void;
  /** Live weights state (see useAppState) -- read here only to show the
   * current weight in the info popover; not resolved per sector like
   * DetailPanel's does, since this picker isn't scoped to one company. */
  weights: WeightsState;
}) {
  return (
    <div className="axis-pickers">
      {([0, 1, 2] as const).map((slot) => (
        <AxisPicker
          key={slot}
          slot={slot}
          color={AXIS_COLORS[slot]}
          name={AXIS_NAMES[slot]}
          view={view}
          axis={axes[slot]}
          weights={weights}
          onChange={onChange}
        />
      ))}
    </div>
  );
}

function AxisPicker({
  slot, color, name, view, axis, weights, onChange,
}: {
  slot: 0 | 1 | 2;
  color: string;
  name: string;
  view: ViewConfig;
  axis: AxisSlot;
  weights: WeightsState;
  onChange: (slot: 0 | 1 | 2, axis: AxisSlot) => void;
}) {
  const [infoOpen, setInfoOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const popoverId = useId();

  // Click-to-toggle rather than hover: the popover content runs several
  // sentences, which a hover tooltip (see WeightPanel's native `title`
  // precedent, used only for one-line hints) can't hold or let the viewer
  // read at their own pace, and hover doesn't work on touch.
  useEffect(() => {
    if (!infoOpen) return;
    function handlePointerDown(e: PointerEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setInfoOpen(false);
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") setInfoOpen(false);
    }
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKey);
    };
  }, [infoOpen]);

  // Close whenever the selected axis changes, so the popover never shows
  // stale content for the axis that was picked before.
  useEffect(() => {
    setInfoOpen(false);
  }, [axisKey(axis)]);

  const weightPct = axisWeightPct(axis, weights);

  // Each slot is pinned to its own default axis (X=Environmental, Y=Transition,
  // Z=Governance) -- the only other choice offered is Composite, not the other
  // two pillars, so the dropdown can't scramble which axis shows what.
  const fixedAxis = view.defaultAxes[slot];
  const options = view.options.filter(
    (o) => axisKey(o) === axisKey(fixedAxis) || o.kind === "composite",
  );

  return (
    <div className="axis-picker" style={{ color }} ref={containerRef}>
      <span className="axis-picker-name">{name}</span>
      <select
        value={axisKey(axis)}
        onChange={(e) => {
          const chosen = options.find((o) => axisKey(o) === e.target.value);
          if (chosen) onChange(slot, chosen);
        }}
      >
        {options.map((opt) => (
          <option key={axisKey(opt)} value={axisKey(opt)}>{axisLabel(opt)}</option>
        ))}
      </select>
      <button
        type="button"
        className="axis-picker-info"
        aria-expanded={infoOpen}
        aria-controls={popoverId}
        aria-label={`What does ${axisLabel(axis)} measure?`}
        onClick={() => setInfoOpen((o) => !o)}
      >
        i
      </button>
      {infoOpen && (
        <div
          id={popoverId}
          // Z is the rightmost picker -- anchor its popover to the right
          // edge instead of the left so it opens inward, not off-screen.
          className={slot === 2 ? "axis-picker-popover axis-picker-popover--right" : "axis-picker-popover"}
          role="tooltip"
        >
          {axisDescription(axis).map((block, i) => {
            if (block.kind === "ul") {
              return (
                <ul key={i}>
                  {block.items.map((item) => <li key={item}>{item}</li>)}
                </ul>
              );
            }
            return (
              <p key={i}>
                {"label" in block && <strong>{block.label}: </strong>}
                {block.text}
              </p>
            );
          })}
          {weightPct !== null && (
            <p className="axis-picker-popover-weight">Current weight: {weightPct.toFixed(0)}%</p>
          )}
        </div>
      )}
    </div>
  );
}

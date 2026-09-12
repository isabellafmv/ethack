// Three axis dropdowns bound to the active view's registry entries (Task 4).
// Colour-matched to the 3D axis lines in ScatterView so the mapping between
// a line's shade and "X: <field>" is obvious without in-scene text. Being
// plain HTML, these stay legible at every camera angle -- they never rotate.
import { axisKey, axisLabel, type AxisSlot, type ViewConfig } from "./views";

// Palette-only axis identity: X = ink, Y = accent, Z = a faded shade of ink
// (rather than a third hue) so the three stay visually distinct.
const AXIS_COLORS = ["rgba(0,0,0,0.7)", "#AAB644", "rgba(0,0,0,0.3)"];
const AXIS_NAMES = ["X", "Y", "Z"];

export function AxisPickers({
  view, axes, onChange,
}: {
  view: ViewConfig;
  axes: [AxisSlot, AxisSlot, AxisSlot];
  onChange: (slot: 0 | 1 | 2, axis: AxisSlot) => void;
}) {
  return (
    <div className="axis-pickers">
      {([0, 1, 2] as const).map((slot) => (
        <label key={slot} className="axis-picker" style={{ color: AXIS_COLORS[slot] }}>
          <span className="axis-picker-name">{AXIS_NAMES[slot]}</span>
          <select
            value={axisKey(axes[slot])}
            onChange={(e) => {
              const chosen = view.options.find((o) => axisKey(o) === e.target.value);
              if (chosen) onChange(slot, chosen);
            }}
          >
            {view.options.map((opt) => (
              <option key={axisKey(opt)} value={axisKey(opt)}>{axisLabel(opt)}</option>
            ))}
          </select>
        </label>
      ))}
    </div>
  );
}

// Three axis dropdowns bound to the active view's registry entries (Task 4).
// Colour-matched to the 3D axis lines in ScatterView so the mapping between
// "red line" and "X: <field>" is obvious without in-scene text. Being plain
// HTML, these stay legible at every camera angle -- they never rotate.
import { axisKey, axisLabel, type AxisSlot, type ViewConfig } from "./views";

const AXIS_COLORS = ["#ef4444", "#22c55e", "#3b82f6"];
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
        <label key={slot} className="axis-picker" style={{ borderColor: AXIS_COLORS[slot] }}>
          <span className="axis-picker-name" style={{ color: AXIS_COLORS[slot] }}>{AXIS_NAMES[slot]}</span>
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

// Permanent legend covering all three encodings (Task 7). Colour is
// reference-relative, not sector -- sector lives in the filter panel, never
// on this scale, so the two are never confused.
import type { ReferenceSpec } from "../scoring/reference";
import { referenceLabel } from "../scoring/reference";

export function Legend({ reference, deltaMode }: { reference: ReferenceSpec; deltaMode: "raw" | "sector_adjusted" }) {
  return (
    <div className="panel legend">
      <h3>Legend</h3>
      <div className="legend-row">
        <div className="legend-swatch legend-swatch--gradient" />
        <div>
          <strong>Colour</strong> &mdash; {referenceLabel(reference, deltaMode)}.
          Accent = better, grey = at reference, black = worse.
        </div>
      </div>
      <div className="legend-row">
        <div className="legend-sizes">
          <span className="legend-dot legend-dot--sm" />
          <span className="legend-dot legend-dot--md" />
          <span className="legend-dot legend-dot--lg" />
        </div>
        <div><strong>Size</strong> &mdash; market cap, sqrt-scaled and clamped.</div>
      </div>
      <div className="legend-row">
        <div className="legend-sizes">
          <span className="legend-dot legend-dot--dim" />
          <span className="legend-dot legend-dot--bright" />
        </div>
        <div><strong>Opacity</strong> &mdash; confidence (dim = low evidence, bright = high).</div>
      </div>
      <div className="legend-row">
        <div className="legend-sizes">
          <span className="legend-dot legend-dot--wire" />
        </div>
        <div><strong>Wireframe</strong> &mdash; an imputed value on one of the visible axes, not a measurement.</div>
      </div>
    </div>
  );
}

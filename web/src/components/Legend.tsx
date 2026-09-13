// Permanent legend covering all three encodings (Task 7). Titles only --
// the swatches themselves plus the axis pickers/coverage strip carry the
// detail; this is just "what does each channel mean", not a paragraph.
export function Legend() {
  return (
    <div className="panel legend">
      <h3>Legend</h3>
      <div className="legend-row">
        <div className="legend-swatch legend-swatch--gradient" />
        <strong>Low to High Scoring</strong>
      </div>
      <div className="legend-row">
        <div className="legend-sizes">
          <span className="legend-dot legend-dot--sm" />
          <span className="legend-dot legend-dot--md" />
          <span className="legend-dot legend-dot--lg" />
        </div>
        <strong>Market Cap</strong>
      </div>
      <div className="legend-row">
        <div className="legend-sizes">
          <span className="legend-dot legend-dot--dim" />
          <span className="legend-dot legend-dot--bright" />
        </div>
        <strong>Calculation Confidence</strong>
      </div>
      {/* <div className="legend-row">
        <div className="legend-sizes">
          <span className="legend-dot legend-dot--wire" />
        </div>
        <strong>Wireframe</strong>
      </div>*/}
    </div>
  );
}

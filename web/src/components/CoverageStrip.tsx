// "Of N companies, how many have measured / imputed / not-disclosed values
// on the three visible axes." Honest coverage on screen is a differentiator,
// not an admission -- an axis reading "0 / 500" is rendered exactly as
// prominently as one reading "480 / 500".
import { axisLabel, type AxisSlot } from "../viz/views";
import type { AxisCoverage } from "../viz/coverage";

export function CoverageStrip({ coverages }: { coverages: AxisCoverage[] }) {
  return (
    <div className="panel coverage-strip">
      <h3>Coverage (this view)</h3>
      {coverages.map((cov) => (
        <CoverageBar key={JSON.stringify(cov.axis)} axis={cov.axis} coverage={cov} />
      ))}
    </div>
  );
}

function CoverageBar({ axis, coverage }: { axis: AxisSlot; coverage: AxisCoverage }) {
  const { measured, imputed, unavailable, total } = coverage;
  const pct = (n: number) => (total === 0 ? 0 : (n / total) * 100);
  return (
    <div className="coverage-bar-row">
      <div className="coverage-bar-label">
        {axisLabel(axis)} <span className="count">({measured}/{total} measured{imputed ? `, ${imputed} imputed` : ""})</span>
      </div>
      <div className="coverage-bar">
        <div className="coverage-bar-segment coverage-bar-segment--measured" style={{ width: `${pct(measured)}%` }} />
        <div className="coverage-bar-segment coverage-bar-segment--imputed" style={{ width: `${pct(imputed)}%` }} />
        <div className="coverage-bar-segment coverage-bar-segment--unavailable" style={{ width: `${pct(unavailable)}%` }} />
      </div>
    </div>
  );
}

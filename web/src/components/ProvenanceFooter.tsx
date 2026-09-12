// "The map is showing yesterday's numbers" is a classic 2 a.m. hour lost --
// generated_at, schema_version and a basis-year note stay on screen always,
// and the footer goes amber past a 2-hour staleness threshold.
const STALE_MS = 2 * 60 * 60 * 1000;

export function ProvenanceFooter({
  generatedAt, schemaVersion, analysisYear, isFixture,
}: {
  generatedAt: string;
  schemaVersion: number;
  analysisYear: number;
  isFixture: boolean;
}) {
  const ageMs = Date.now() - new Date(generatedAt).getTime();
  const stale = !isFixture && ageMs > STALE_MS;
  const ageLabel = formatAge(ageMs);

  return (
    <footer className={`provenance-footer${stale ? " provenance-footer--stale" : ""}`}>
      <span>Generated {ageLabel} ago ({generatedAt})</span>
      <span>schema v{schemaVersion}</span>
      <span>
        Emissions FY{analysisYear} (latest GHGRP); financials FY2025. Fiscal
        year-ends span Jan-Dec, which is standard practice.
      </span>
      {stale && <span className="provenance-footer-warning">STALE &gt; 2h</span>}
    </footer>
  );
}

function formatAge(ms: number): string {
  const mins = Math.round(ms / 60000);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  const rem = mins % 60;
  return `${hours}h ${rem}m`;
}

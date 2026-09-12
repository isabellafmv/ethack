export function ProvenanceFooter({
  schemaVersion, analysisYear,
}: {
  schemaVersion: number;
  analysisYear: number;
}) {
  return (
    <footer className="provenance-footer">
      <span>schema v{schemaVersion}</span>
      <span>
        Emissions FY{analysisYear} (latest GHGRP); financials FY2025.
      </span>
    </footer>
  );
}

export function ProvenanceFooter({

}: {
  schemaVersion: number;
  analysisYear: number;
}) {
  return (
    <footer className="provenance-footer">
      {/* <span>schema v{schemaVersion}</span> */}
      <span>
        Emissions FY2023 (latest GHGRP); financials FY2025.
      </span>
    </footer>
  );
}

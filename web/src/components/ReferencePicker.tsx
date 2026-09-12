// Sets what "better/worse" is measured against (Task 5). The mode is always
// named in the legend/label -- "vs NVDA, raw" vs "vs NVDA, sector-adjusted"
// are different claims, and the UI must never pick one silently.
import { useState } from "react";
import type { ReferenceSpec } from "../scoring/reference";
import type { Company } from "../scoring/types";

export function ReferencePicker({
  reference, onChangeReference, deltaMode, onChangeDeltaMode, companies,
}: {
  reference: ReferenceSpec;
  onChangeReference: (r: ReferenceSpec) => void;
  deltaMode: "raw" | "sector_adjusted";
  onChangeDeltaMode: (m: "raw" | "sector_adjusted") => void;
  companies: readonly Company[];
}) {
  const [query, setQuery] = useState("");
  const matches = query.length > 0
    ? companies.filter((c) => c.ticker.toLowerCase().includes(query.toLowerCase()) || c.name.toLowerCase().includes(query.toLowerCase())).slice(0, 8)
    : [];

  return (
    <div className="panel reference-picker">
      <h3>Reference point</h3>
      <div className="reference-modes">
        {(["sector_median", "sector_best", "index_median", "company"] as const).map((mode) => (
          <label key={mode} className="radio-row">
            <input
              type="radio"
              name="reference-mode"
              checked={reference.mode === mode}
              onChange={() => onChangeReference(mode === "company" ? { mode, companyTicker: reference.companyTicker } : { mode })}
            />
            {modeLabel(mode)}
          </label>
        ))}
      </div>
      {reference.mode === "company" && (
        <div className="reference-company-search">
          <input
            type="text"
            placeholder="Search company or ticker..."
            value={reference.companyTicker ? `${reference.companyTicker}` : query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {matches.length > 0 && (
            <ul className="search-results">
              {matches.map((c) => (
                <li key={c.ticker}>
                  <button onClick={() => { onChangeReference({ mode: "company", companyTicker: c.ticker }); setQuery(""); }}>
                    {c.ticker} &mdash; {c.name}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {!reference.companyTicker && <p className="hint">No company selected -- falling back to sector median.</p>}
        </div>
      )}
      <div className="delta-mode-toggle">
        <label>
          <input type="radio" name="delta-mode" checked={deltaMode === "sector_adjusted"} onChange={() => onChangeDeltaMode("sector_adjusted")} />
          Sector-adjusted
        </label>
        <label>
          <input type="radio" name="delta-mode" checked={deltaMode === "raw"} onChange={() => onChangeDeltaMode("raw")} />
          Raw
        </label>
      </div>
    </div>
  );
}

function modeLabel(mode: ReferenceSpec["mode"]): string {
  switch (mode) {
    case "sector_median": return "Sector median";
    case "sector_best": return "Sector best-in-class";
    case "index_median": return "Index median";
    case "company": return "Named company";
  }
}

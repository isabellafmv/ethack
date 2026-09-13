// The other entry point into DetailPanel, not a separate feature: a 3D
// scatter alone makes it hard to scan/sort/compare companies, and several
// dimensions (confidence, disclosure coverage, n_indicators_available)
// have no visual encoding in the 3D view beyond opacity/wireframe, which
// don't read as numbers. Same props shape as ScatterView on purpose
// (companies/scores/visibleSectors/onSelectCompany) -- this is a second
// renderer over the exact same computeScores() output and the exact same
// sector-visibility rule (isSectorVisible), not a second data pipeline.
import { useMemo, useState } from "react";
import type { CompanyScoreResult, PillarResult } from "../scoring/pipeline";
import { PILLARS } from "../scoring/pipeline";
import type { Pillar } from "../scoring/registry";
import type { Company } from "../scoring/types";
import { isSectorVisible } from "../state/useAppState";
import { PILLAR_SCORE_NAMES } from "../viz/views";

export interface TableViewProps {
  companies: readonly Company[];
  scores: Map<string, CompanyScoreResult>;
  visibleSectors: Set<string>;
  onSelectCompany: (ticker: string) => void;
}

type SortKey =
  | "ticker" | "name" | "sector" | "confidence" | "composite"
  | `pillar:${Pillar}` | `coverage:${Pillar}`;

interface SortState {
  key: SortKey;
  direction: "asc" | "desc";
}

interface Row {
  ticker: string;
  name: string;
  sector: string;
  confidence: number;
  composite: number | null;
  pillars: Record<Pillar, PillarResult>;
}

function nAvailable(pillar: PillarResult): number {
  return pillar.subScores.filter((s) => s.statusClass !== "unavailable").length;
}

/** Nulls always sort to the end, regardless of direction -- an ascending
 * sort putting every "n/a" row at the TOP would read as those companies
 * having the best (lowest) score, exactly the "absence is a finding, not a
 * zero" mistake this codebase avoids everywhere else. */
function compareNullable(a: number | null, b: number | null, direction: "asc" | "desc"): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return direction === "asc" ? a - b : b - a;
}

function sortValue(row: Row, key: SortKey): number | string | null {
  if (key === "ticker") return row.ticker;
  if (key === "name") return row.name;
  if (key === "sector") return row.sector;
  if (key === "confidence") return row.confidence;
  if (key === "composite") return row.composite;
  if (key.startsWith("pillar:")) return row.pillars[key.slice(7) as Pillar].score;
  return row.pillars[key.slice(9) as Pillar].disclosureCoverage;
}

function fmtScore(v: number | null): string {
  return v === null ? "n/a" : v.toFixed(1);
}

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "ticker", label: "Ticker" },
  { key: "name", label: "Company" },
  { key: "sector", label: "Sector" },
  { key: "composite", label: "Composite" },
  ...PILLARS.map((p): { key: SortKey; label: string } => ({ key: `pillar:${p}`, label: PILLAR_SCORE_NAMES[p] })),
  { key: "confidence", label: "Confidence" },
  ...PILLARS.map((p): { key: SortKey; label: string } => ({ key: `coverage:${p}`, label: `${PILLAR_SCORE_NAMES[p]} coverage` })),
];

export function TableView({ companies, scores, visibleSectors, onSelectCompany }: TableViewProps) {
  const [sort, setSort] = useState<SortState>({ key: "composite", direction: "desc" });

  const rows = useMemo<Row[]>(() => {
    const out: Row[] = [];
    for (const c of companies) {
      if (!isSectorVisible(c.sector, visibleSectors)) continue;
      const result = scores.get(c.ticker);
      if (!result) continue;
      out.push({
        ticker: c.ticker,
        name: c.name,
        sector: c.sector,
        confidence: c.confidence,
        composite: result.composite,
        pillars: result.pillars,
      });
    }
    return out;
  }, [companies, scores, visibleSectors]);

  const sorted = useMemo(() => {
    const withValues = rows.map((row) => ({ row, value: sortValue(row, sort.key) }));
    withValues.sort((a, b) => {
      if (typeof a.value === "string" || typeof b.value === "string") {
        const as = String(a.value ?? "");
        const bs = String(b.value ?? "");
        const cmp = as.localeCompare(bs);
        return sort.direction === "asc" ? cmp : -cmp;
      }
      return compareNullable(a.value, b.value, sort.direction);
    });
    return withValues.map((w) => w.row);
  }, [rows, sort]);

  const toggleSort = (key: SortKey) => {
    setSort((prev) =>
      prev.key === key
        ? { key, direction: prev.direction === "asc" ? "desc" : "asc" }
        : { key, direction: "desc" }
    );
  };

  return (
    <div className="table-view-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {COLUMNS.map((col) => (
              <th key={col.key} onClick={() => toggleSort(col.key)}>
                {col.label}
                {sort.key === col.key && <span className="sort-arrow">{sort.direction === "asc" ? " ▲" : " ▼"}</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={row.ticker} onClick={() => onSelectCompany(row.ticker)}>
              <td>{row.ticker}</td>
              <td>{row.name}</td>
              <td>{row.sector}</td>
              <td className={row.composite === null ? "cell-na" : undefined}>{fmtScore(row.composite)}</td>
              {PILLARS.map((p) => (
                <td key={p} className={row.pillars[p].score === null ? "cell-na" : undefined}>
                  {fmtScore(row.pillars[p].score)}
                </td>
              ))}
              <td>{Math.round(row.confidence * 100)}%</td>
              {PILLARS.map((p) => (
                <td key={p} className="count">
                  {nAvailable(row.pillars[p])}/{row.pillars[p].subScores.length} ({Math.round(row.pillars[p].disclosureCoverage * 100)}%)
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {sorted.length === 0 && <p className="hint">No companies match the current sector filter.</p>}
    </div>
  );
}

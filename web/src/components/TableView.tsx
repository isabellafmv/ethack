// The other entry point into DetailPanel, not a separate feature: a 3D
// scatter alone makes it hard to scan/sort/compare companies, and several
// dimensions (confidence, disclosure coverage, n_indicators_available)
// have no visual encoding in the 3D view beyond opacity/wireframe, which
// don't read as numbers. Same props shape as ScatterView on purpose
// (companies/scores/visibleSectors/onSelectCompany) -- this is a second
// renderer over the exact same computeScores() output and the exact same
// sector-visibility rule (isSectorVisible), not a second data pipeline.
//
// Every score column carries its own inline bar (0-100 scaled to the cell
// width) so a reader can compare two rows -- or two columns in the same
// row -- at a glance instead of reading eight columns of bare digits and
// doing the comparison in their head. Coverage gets the same treatment:
// a short filled/unfilled bar reads faster than "6/13 (46%)" ever will,
// with the fraction kept alongside for anyone who wants the exact count.
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
  visibleSectors: Set<string> | null;
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

/** A 0-100 score rendered as a number plus an inline bar, so its position
 * within the possible range is visible without reading the digits -- the
 * same score column two rows apart is now a length comparison, not a
 * subtraction. `title` carries the one-line "what is this number" text
 * that used to live nowhere in the table at all. */
function ScoreCell({ value, title }: { value: number | null; title: string }) {
  if (value === null) return <td className="cell-na" title={title}>n/a</td>;
  return (
    <td className="cell-score" title={title}>
      <span className="cell-score-inner">
        <span className="cell-score-num">{value.toFixed(1)}</span>
        <span className="cell-score-bar"><span className="cell-score-bar-fill" style={{ width: `${value}%` }} /></span>
      </span>
    </td>
  );
}

function CoverageCell({ pillar, pillarName, ticker }: { pillar: PillarResult; pillarName: string; ticker: string }) {
  const n = nAvailable(pillar);
  const total = pillar.subScores.length;
  const pct = total > 0 ? n / total : 0;
  return (
    <td
      className="cell-coverage"
      title={`${ticker}: ${n} of ${total} ${pillarName} indicators disclosed (${Math.round(pct * 100)}%).`}
    >
      <span className="coverage-mini"><span className="coverage-mini-fill" style={{ width: `${pct * 100}%` }} /></span>
      <span className="count">{n}/{total}</span>
    </td>
  );
}

const COLUMN_HELP: Partial<Record<SortKey, string>> = {
  composite: "0–100. Blends Environmental, Transition and Governance, each already scored against sector peers.",
  confidence: "How much of this company's overall picture rests on measured (not imputed) data.",
};

const COLUMNS: { key: SortKey; label: string; help?: string }[] = [
  { key: "ticker", label: "Ticker" },
  { key: "name", label: "Company" },
  { key: "sector", label: "Sector" },
  { key: "composite", label: "Composite", help: COLUMN_HELP.composite },
  ...PILLARS.map((p): { key: SortKey; label: string; help?: string } => ({
    key: `pillar:${p}`,
    label: PILLAR_SCORE_NAMES[p],
    help: `${PILLAR_SCORE_NAMES[p]} pillar score, 0–100 — open a row for what feeds into it.`,
  })),
  { key: "confidence", label: "Confidence", help: COLUMN_HELP.confidence },
  ...PILLARS.map((p): { key: SortKey; label: string; help?: string } => ({
    key: `coverage:${p}`,
    label: `${PILLAR_SCORE_NAMES[p]} coverage`,
    help: `Share of ${PILLAR_SCORE_NAMES[p]} indicators this company has actually disclosed.`,
  })),
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
      {/* <p className="table-view-hint">
        Composite, pillar and coverage scores are 0&ndash;100. Most are the company&rsquo;s standing among its own sector peers, not a fixed scale &mdash; hover any header or bar for what it measures.
      </p>  */}
      <table className="data-table">
        <thead>
          <tr>
            {COLUMNS.map((col) => (
              <th key={col.key} onClick={() => toggleSort(col.key)} title={col.help}>
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
              <ScoreCell value={row.composite} title={`${row.ticker} composite: ${fmtScore(row.composite)} of 100.`} />
              {PILLARS.map((p) => (
                <ScoreCell
                  key={p}
                  value={row.pillars[p].score}
                  title={`${row.ticker} ${PILLAR_SCORE_NAMES[p]}: ${fmtScore(row.pillars[p].score)} of 100.`}
                />
              ))}
              <td>{Math.round(row.confidence * 100)}%</td>
              {PILLARS.map((p) => (
                <CoverageCell key={p} pillar={row.pillars[p]} pillarName={PILLAR_SCORE_NAMES[p]} ticker={row.ticker} />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {sorted.length === 0 && <p className="hint">No companies match the current sector filter.</p>}
    </div>
  );
}

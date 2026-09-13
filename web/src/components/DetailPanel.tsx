// Task 6, "the best demo moment available": click a point, see the full
// derivation -- raw inputs, fiscal years, sources, status, the computed
// value, the sector percentile, and the weight applied. Quotes lazy-load on
// first open (they are not needed to draw the point, only to inspect it).
//
// Every number in here is shown next to the thing that lets a reader place
// it: a sub-score gets a percentile bar and "vs N sector peers" caption
// (not just a bare 0-100), a raw field gets a plain-language label and a
// human-formatted value (not a snake_case key and an unformatted float),
// and two disagreeing sources get an explicit "which one counts" line
// instead of a run-on sentence built from whatever source code happens to
// be on file.
import { useEffect, useState } from "react";
import { normalizedWeights, type CompanyScoreResult, type SubScoreResult, type WeightsState } from "../scoring/pipeline";
import { registryForPillar, type Pillar, type SubScoreDef } from "../scoring/registry";
import { PILLARS } from "../scoring/pipeline";
import { PILLAR_SCORE_NAMES } from "../viz/views";
import type { Company, FieldRecord, SchemaField } from "../scoring/types";
import { loadQuotes } from "../data/useMatrix";

const SOURCE_LABELS: Record<string, string> = {
  S01: "SEC XBRL (financial filings)",
  S02: "SEC 10-K (text analysis)",
  S03: "SEC full-text search",
  S04: "SEC proxy statement",
  S05: "SEC exhibit 21 (subsidiaries)",
  S06: "GLEIF (entity registry)",
  S07: "Market data",
  S08: "Company reference universe",
  S09: "Science Based Targets initiative",
  S10: "Company sustainability disclosure",
  S11: "Violation Tracker (court/agency records)",
  S12: "Senate lobbying disclosure",
  S13: "CDP (Carbon Disclosure Project)",
  S14: "Kaggle ESG Risk Ratings",
  S15: "EPA GHGRP (measured)",
  S18: "EPA ECHO (compliance/enforcement)",
  S19: "EPA eGRID (grid emissions factors)",
  imputed: "Imputed (sector proxy)",
};
const STATUS_LABELS: Record<FieldRecord["st"], string> = {
  structural: "Structural", quote_verified: "Quote-verified", imputed: "Imputed",
  not_disclosed: "Not disclosed", quote_failed: "Quote failed",
};

/** `S01~team` etc. -- a team-imported variant of a base source, not a new
 * source. Falls back to the raw code (never silently blank) only if even
 * the base code isn't recognized, so an unmapped source is still visible
 * as *something* rather than disappearing. */
function sourceLabel(code: string): string {
  if (SOURCE_LABELS[code]) return SOURCE_LABELS[code];
  const teamSuffix = "~team";
  if (code.endsWith(teamSuffix)) {
    const base = code.slice(0, -teamSuffix.length);
    return `${SOURCE_LABELS[base] ?? base} (team-verified import)`;
  }
  return code;
}

/** Schema descriptions are written for the pipeline's own maintainers and
 * sometimes trail off into an implementation note after " -- " (e.g. "...
 * -- the fallback chain lives in sources/s01_sec_xbrl/fields.py"). Only the
 * first clause is fit for a reader looking at one company's numbers. */
function fieldLabel(field: string, schema: Record<string, SchemaField> | undefined): string {
  const desc = schema?.[field]?.description;
  const clause = desc?.split(/\s+--\s+|\s+—\s+/)[0]?.trim();
  if (clause) return clause;
  return field.replace(/_/g, " ");
}

function formatUsd(n: number): string {
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

const UNIT_LABELS: Record<string, string> = {
  tco2e: "t CO₂e",
  kgco2e_per_mwh: "kg CO₂e/MWh",
};

function formatFieldValue(rec: FieldRecord): string {
  const { v, u } = rec;
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "string") return v;
  if (u === "usd") return formatUsd(v);
  if (u === "pct") return `${v.toFixed(1)}%`;
  if (u === null || u === "year") return v.toLocaleString();
  const unitLabel = UNIT_LABELS[u] ?? u.replace(/_/g, " ");
  return `${v.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${unitLabel}`;
}

/** What the sub-score's 0-100 number actually means -- most are a sector
 * percentile (so "68" means "better than 68% of sector peers"), but a
 * handful of registry entries are an absolute blended formula instead
 * (scoringMode 'absolute' / 'sector_normalized'), where the same "68" is
 * just the final score, not a rank. Mislabeling the second group as a
 * percentile would be a false claim, not a simplification. */
function subScoreContext(sub: SubScoreDef, subResult: SubScoreResult, sector: string): string {
  if (subResult.score === null) return "";
  const mode = sub.scoringMode ?? "sector_percentile";
  if (mode === "sector_percentile") {
    return `Better than ${subResult.score.toFixed(0)}% of ${subResult.coverageN} ${sector} peers.`;
  }
  if (mode === "universe_percentile") {
    return `Better than ${subResult.score.toFixed(0)}% of ${subResult.coverageN} S&P 500 companies.`;
  }
  return "Final 0–100 score from a fixed formula — not a peer ranking.";
}

export function DetailPanel({
  company, result, urls, weights, isFixture, schema, onClose,
}: {
  company: Company;
  result: CompanyScoreResult;
  urls: string[];
  weights: WeightsState;
  isFixture: boolean;
  schema?: Record<string, SchemaField>;
  onClose: () => void;
}) {
  const [quotes, setQuotes] = useState<Record<string, string> | null>(null);
  const normalized = normalizedWeights(weights);

  useEffect(() => {
    let cancelled = false;
    setQuotes(null);
    loadQuotes(isFixture).then((payload) => {
      if (!cancelled) setQuotes(payload.quotes[company.ticker] ?? {});
    }).catch(() => { if (!cancelled) setQuotes({}); });
    return () => { cancelled = true; };
  }, [company.ticker, isFixture]);

  return (
    <div className="detail-panel">
      <div className="detail-panel-header">
        <div>
          <h2>{company.name}</h2>
          <span className="detail-ticker">{company.ticker} &middot; {company.sector} &middot; {company.sub_industry}</span>
        </div>
        <button className="close-button" onClick={onClose} aria-label="Close">&times;</button>
      </div>

      <div className="detail-composite">
        Composite: <strong>{fmtScore(result.composite)}</strong>
        <span className="count"> (overall confidence {(company.confidence * 100).toFixed(0)}%)</span>
        <p className="composite-explainer">
          0&ndash;100, blending {PILLARS.map((p) => PILLAR_SCORE_NAMES[p]).join(" / ")} &mdash; each pillar is
          already scored relative to {company.sector} sector peers wherever the data allows it.
        </p>
      </div>

      {PILLARS.map((pillar) => (
        <PillarBlock
          key={pillar}
          pillar={pillar}
          result={result}
          company={company}
          urls={urls}
          quotes={quotes}
          schema={schema}
          pillarWeight={normalized.pillars[pillar]}
          subWeights={normalized.subscores}
        />
      ))}
    </div>
  );
}

function PillarBlock({
  pillar, result, company, urls, quotes, schema, pillarWeight, subWeights,
}: {
  pillar: Pillar;
  result: CompanyScoreResult;
  company: Company;
  urls: string[];
  quotes: Record<string, string> | null;
  schema?: Record<string, SchemaField>;
  pillarWeight: number;
  subWeights: Record<string, number>;
}) {
  const pillarResult = result.pillars[pillar];
  return (
    <section className="detail-pillar">
      <h3>{PILLAR_SCORE_NAMES[pillar]} &mdash; {fmtScore(pillarResult.score)} <span className="count">(weight {(pillarWeight * 100).toFixed(0)}%)</span></h3>
      {pillarResult.score !== null && (
        <div className="pct-bar pct-bar--pillar">
          <div className="pct-bar-fill" style={{ width: `${pillarResult.score}%` }} />
        </div>
      )}
      <p className="pct-caption">
        {(pillarResult.disclosureCoverage * 100).toFixed(0)}% of this pillar&rsquo;s tracked indicators are disclosed for {company.ticker}.
      </p>
      {registryForPillar(pillar).map((sub) => {
        const subResult = pillarResult.subScores.find((s) => s.id === sub.id)!;
        return (
          <div key={sub.id} className="detail-subscore">
            <div className="detail-subscore-header">
              <strong>{sub.label}</strong>
              <span>{fmtScore(subResult.score)} <span className="count">(weight {((subWeights[sub.id] ?? 0) * 100).toFixed(0)}%)</span></span>
            </div>
            {subResult.score !== null && (
              <>
                <div className="pct-bar">
                  <div className="pct-bar-fill" style={{ width: `${subResult.score}%` }} />
                </div>
                <p className="pct-caption">{subScoreContext(sub, subResult, company.sector)}</p>
              </>
            )}
            {subResult.statusClass === "unavailable" ? (
              <p className="not-disclosed">
                {company.name} hasn&rsquo;t disclosed {sub.inputs.map((f) => fieldLabel(f, schema)).join(" or ")}
                {" "}(or the reported figure failed source verification).
              </p>
            ) : (
              <>
                <p className="raw-value">
                  Raw value: {subResult.rawValue?.toLocaleString(undefined, { maximumFractionDigits: 3 })}
                  {subResult.statusClass === "imputed" && <span className="badge badge--imputed"> imputed</span>}
                </p>
                <ul className="input-list">
                  {sub.inputs.map((field) => {
                    const rec = company.fields[field];
                    const label = fieldLabel(field, schema);
                    if (!rec) return <li key={field}>{label}: not disclosed</li>;
                    return (
                      <li key={field}>
                        {label}: <strong>{formatFieldValue(rec)}</strong> &middot; FY{rec.fy} &middot;{" "}
                        <span className={`badge badge--${rec.st}`}>{STATUS_LABELS[rec.st]}</span> &middot;{" "}
                        {sourceLabel(rec.src)}
                        {urls[rec.url] && (
                          <>
                            {" "}&middot; <a href={urls[rec.url]} target="_blank" rel="noreferrer">source</a>
                          </>
                        )}
                        {quotes && quotes[field] && <blockquote>&ldquo;{quotes[field]}&rdquo;</blockquote>}
                      </li>
                    );
                  })}
                </ul>
                {sub.inputs.map((field) => {
                  const alts = company.alternatives[field];
                  if (!alts || alts.length === 0) return null;
                  const primary = company.fields[field];
                  const label = fieldLabel(field, schema);
                  return (
                    <div key={field} className="data-conflict">
                      <strong>Conflicting sources for {label}</strong>
                      <p>
                        Used in scoring: <b>{formatFieldValue(primary)}</b> ({sourceLabel(primary.src)}).{" "}
                        {alts.map((a, i) => {
                          const bothNumeric = typeof primary.v === "number" && typeof a.v === "number";
                          const diffPct = bothNumeric && primary.v !== 0
                            ? Math.abs(((a.v as number) - (primary.v as number)) / (primary.v as number)) * 100
                            : null;
                          return (
                            <span key={i}>
                              Also reported: {formatFieldValue(a)} ({sourceLabel(a.src)})
                              {diffPct !== null ? ` — differs by ${diffPct.toFixed(0)}%` : ""}
                              {i < alts.length - 1 ? "; " : ""}
                            </span>
                          );
                        })}
                      </p>
                    </div>
                  );
                })}
              </>
            )}
          </div>
        );
      })}
    </section>
  );
}

function fmtScore(score: number | null): string {
  return score === null ? "n/a" : score.toFixed(1);
}

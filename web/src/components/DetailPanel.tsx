// Task 6, "the best demo moment available": click a point, see the full
// derivation -- raw inputs, fiscal years, sources, status, the computed
// value, the sector percentile, and the weight applied. Quotes lazy-load on
// first open (they are not needed to draw the point, only to inspect it).
import { useEffect, useState } from "react";
import { normalizedWeights, type CompanyScoreResult, type WeightsState } from "../scoring/pipeline";
import { registryForPillar, type Pillar } from "../scoring/registry";
import { PILLARS } from "../scoring/pipeline";
import { PILLAR_SCORE_NAMES } from "../viz/views";
import type { Company, FieldRecord } from "../scoring/types";
import { loadQuotes } from "../data/useMatrix";

const SOURCE_LABELS: Record<string, string> = {
  S15: "EPA GHGRP (measured)", S10: "Company disclosure", S09: "SBTi", S01: "SEC XBRL",
  S04: "Proxy statement", S02: "10-K text analysis", S24: "USPTO patents", S11: "Court/agency records",
  imputed: "Imputed (sector proxy)",
};
const STATUS_LABELS: Record<FieldRecord["st"], string> = {
  structural: "Structural", quote_verified: "Quote-verified", imputed: "Imputed",
  not_disclosed: "Not disclosed", quote_failed: "Quote failed",
};

export function DetailPanel({
  company, result, urls, weights, isFixture, onClose,
}: {
  company: Company;
  result: CompanyScoreResult;
  urls: string[];
  weights: WeightsState;
  isFixture: boolean;
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
      </div>

      {PILLARS.map((pillar) => (
        <PillarBlock
          key={pillar}
          pillar={pillar}
          result={result}
          company={company}
          urls={urls}
          quotes={quotes}
          pillarWeight={normalized.pillars[pillar]}
          subWeights={normalized.subscores}
        />
      ))}
    </div>
  );
}

function PillarBlock({
  pillar, result, company, urls, quotes, pillarWeight, subWeights,
}: {
  pillar: Pillar;
  result: CompanyScoreResult;
  company: Company;
  urls: string[];
  quotes: Record<string, string> | null;
  pillarWeight: number;
  subWeights: Record<string, number>;
}) {
  const pillarResult = result.pillars[pillar];
  return (
    <section className="detail-pillar">
      <h3>{PILLAR_SCORE_NAMES[pillar]} &mdash; {fmtScore(pillarResult.score)} <span className="count">(weight {(pillarWeight * 100).toFixed(0)}%)</span></h3>
      {registryForPillar(pillar).map((sub) => {
        const subResult = pillarResult.subScores.find((s) => s.id === sub.id)!;
        return (
          <div key={sub.id} className="detail-subscore">
            <div className="detail-subscore-header">
              <strong>{sub.label}</strong>
              <span>{fmtScore(subResult.score)} <span className="count">(weight {((subWeights[sub.id] ?? 0) * 100).toFixed(0)}%, n={subResult.coverageN})</span></span>
            </div>
            {subResult.statusClass === "unavailable" ? (
              <p className="not-disclosed">Not disclosed &mdash; {sub.inputs.join(", ")} missing or untrusted for {company.ticker}.</p>
            ) : (
              <>
                <p className="raw-value">
                  Raw value: {subResult.rawValue?.toLocaleString(undefined, { maximumFractionDigits: 3 })}
                  {subResult.statusClass === "imputed" && <span className="badge badge--imputed"> imputed</span>}
                </p>
                <ul className="input-list">
                  {sub.inputs.map((field) => {
                    const rec = company.fields[field];
                    if (!rec) return <li key={field}>{field}: not disclosed</li>;
                    return (
                      <li key={field}>
                        {field}: {String(rec.v)}{rec.u ? ` ${rec.u}` : ""} &middot; FY{rec.fy} &middot;{" "}
                        <span className={`badge badge--${rec.st}`}>{STATUS_LABELS[rec.st]}</span> &middot;{" "}
                        {SOURCE_LABELS[rec.src] ?? rec.src}
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
                  return (
                    <p key={field} className="say-do-gap">
                      {SOURCE_LABELS[primary.src] ?? primary.src} says {String(primary.v)}{primary.u ? ` ${primary.u}` : ""}, the{" "}
                      {alts.map((a, i) => (
                        <span key={i}>{SOURCE_LABELS[a.src] ?? a.src} says {String(a.v)}{a.u ? ` ${a.u}` : ""}{i < alts.length - 1 ? "; " : ""}</span>
                      ))}
                    </p>
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

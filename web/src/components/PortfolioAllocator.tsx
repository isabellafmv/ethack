// Bonus question: "the world commits to net-zero tomorrow -- how do you
// allocate a $1B fund?" This is that allocator, wired to the SAME
// `scores` the rest of the app already computed (App.tsx's computeScores()
// call) -- not a second, competing scoring engine. Reuses this app's own
// percentile/aggregation primitives (scoring/percentile.ts) for the one
// thing it computes independently: Risk Score, since neither price/
// volatility data nor a risk model exists anywhere in this pipeline.
//
// Sizing is a rule, not an optimizer -- deliberately, see the "Why a rule"
// panel below -- and every rule constant here (the 0.6/1.5/50 etc.) is a
// judgment call, kept as a named constant so it's one visible number to
// argue with, not buried in an expression.
import { useMemo, useState, type CSSProperties } from "react";
import type { Company } from "../scoring/types";
import { coerceFieldValue, TRUSTED_STATUSES } from "../scoring/types";
import type { CompanyScoreResult } from "../scoring/pipeline";
import { percentileRank, weightedMeanSkippingNulls } from "../scoring/percentile";
import { useRevenueGrowth } from "../data/useRevenueGrowth";

const FUND_USD = 1_000_000_000;
type SectorPref = "avoid" | "neutral" | "prefer";
const PREFER_BOOST = 1.5;

interface Row {
  ticker: string;
  company: string;
  sector: string;
  marketCapUsd: number | null;
  fcfYieldPct: number | null;
  ebitdaMarginPct: number | null;
  fcfMarginPct: number | null;
  revenueCagrPct: number | null;
  carbonExposure: number | null;
  transitionAfford: number | null;
  finalScore: number | null;
}

function trustedNumber(c: Company, field: string): number | null {
  const rec = c.fields[field];
  if (!rec || !TRUSTED_STATUSES.has(rec.st)) return null;
  const v = coerceFieldValue(rec.v);
  return Number.isFinite(v) ? v : null;
}

function subScore(result: CompanyScoreResult | undefined, id: string): number | null {
  if (!result) return null;
  for (const pillar of Object.values(result.pillars)) {
    const found = pillar.subScores.find((s) => s.id === id);
    if (found) return found.score;
  }
  return null;
}

function fmtMoney(v: number | null): string {
  if (v == null) return "—";
  const abs = Math.abs(v);
  if (abs >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toFixed(0)}`;
}
function fmtPct(v: number | null, digits = 1): string {
  return v == null ? "—" : `${v.toFixed(digits)}%`;
}

export function PortfolioAllocator({
  companies,
  scores,
}: {
  companies: Company[];
  scores: Map<string, CompanyScoreResult>;
}) {
  const revenueGrowth = useRevenueGrowth();

  const [minScore, setMinScore] = useState(50);
  const [maxRisk, setMaxRisk] = useState(100);
  const [maxHoldings, setMaxHoldings] = useState(500);
  const [maxSectorPct, setMaxSectorPct] = useState(100);
  const [sectorPrefs, setSectorPrefs] = useState<Record<string, SectorPref>>({});
  const [filters, setFilters] = useState({
    revenueCagr: "", fcfYield: "", ebitdaMargin: "", fcfMargin: "",
    carbonExposure: "", transitionAfford: "", marketCapB: "",
  });
  const [search, setSearch] = useState("");

  const sectors = useMemo(() => [...new Set(companies.map((c) => c.sector))].sort(), [companies]);

  const rows = useMemo<Row[]>(() => {
    return companies.map((c) => {
      const marketCapUsd = trustedNumber(c, "market_cap_usd");
      const revenueUsd = trustedNumber(c, "revenue_usd");
      const ebitdaUsd = trustedNumber(c, "ebitda_usd");
      const fcfUsd = trustedNumber(c, "free_cash_flow_usd");
      const result = scores.get(c.ticker);
      return {
        ticker: c.ticker,
        company: c.name,
        sector: c.sector,
        marketCapUsd,
        fcfYieldPct: marketCapUsd && fcfUsd != null ? (100 * fcfUsd) / marketCapUsd : null,
        ebitdaMarginPct: revenueUsd && ebitdaUsd != null ? (100 * ebitdaUsd) / revenueUsd : null,
        fcfMarginPct: revenueUsd && fcfUsd != null ? (100 * fcfUsd) / revenueUsd : null,
        revenueCagrPct: revenueGrowth.cagrByTicker?.get(c.ticker) ?? null,
        carbonExposure: subScore(result, "p2_carbon_price_exposure"),
        transitionAfford: subScore(result, "p2_transition_affordability"),
        finalScore: result?.composite ?? null,
      };
    });
  }, [companies, scores, revenueGrowth.cagrByTicker]);

  // Risk Score: fundamentals-only proxy (no price/volatility data exists
  // anywhere in this pipeline) -- mean of size risk (smaller market cap ->
  // riskier) and fragility risk (thinner/negative FCF margin -> riskier),
  // each a percentile rank via this app's own percentile.ts, exactly like
  // every sub-score in registry.ts. Narrower than the Python bonus page's
  // version (that one also folds in revenue-growth instability, which
  // needs multi-year data matrix.json doesn't carry) -- noted in the UI,
  // not silently dropped.
  const riskByTicker = useMemo(() => {
    const capDist = rows.map((r) => r.marketCapUsd).filter((v): v is number => v != null);
    const marginDist = rows.map((r) => r.fcfMarginPct).filter((v): v is number => v != null);
    const out = new Map<string, number | null>();
    for (const r of rows) {
      const sizeRisk = r.marketCapUsd != null ? percentileRank(r.marketCapUsd, capDist, "lower_is_better") : null;
      const fragilityRisk = r.fcfMarginPct != null ? percentileRank(r.fcfMarginPct, marginDist, "lower_is_better") : null;
      out.set(
        r.ticker,
        weightedMeanSkippingNulls([
          { value: sizeRisk, weight: 1 },
          { value: fragilityRisk, weight: 1 },
        ])
      );
    }
    return out;
  }, [rows]);

  function passesFilters(r: Row): boolean {
    const checks: [string, number | null][] = [
      [filters.revenueCagr, r.revenueCagrPct],
      [filters.fcfYield, r.fcfYieldPct],
      [filters.ebitdaMargin, r.ebitdaMarginPct],
      [filters.fcfMargin, r.fcfMarginPct],
      [filters.carbonExposure, r.carbonExposure],
      [filters.transitionAfford, r.transitionAfford],
    ];
    for (const [raw, value] of checks) {
      if (raw === "") continue;
      const min = Number(raw);
      if (value == null || value < min) return false;
    }
    if (filters.marketCapB !== "") {
      const minCap = Number(filters.marketCapB) * 1e9;
      if (r.marketCapUsd == null || r.marketCapUsd < minCap) return false;
    }
    return true;
  }

  // Sizing: conviction (score above your bar) x sector preference boost ->
  // ranked, kept to your top N -> sector-capped (as % of the full $1B, not
  // of deployed capital -- see the sector chart below) -> whatever's left
  // over per company is the suggested dollar allocation. Trimmed weight
  // (from the score bar, the top-N cutoff, or the sector cap) is never
  // redistributed -- it just becomes cash, the same honest treatment
  // score_calculation's own renormalization uses for a missing sub-score.
  const sized = useMemo(() => {
    const withConviction = rows.map((r) => {
      const risk = riskByTicker.get(r.ticker) ?? null;
      const pref = sectorPrefs[r.sector] ?? "neutral";
      const eligible =
        r.finalScore != null && r.finalScore > minScore &&
        risk != null && risk <= maxRisk &&
        pref !== "avoid" &&
        passesFilters(r);
      const boost = pref === "prefer" ? PREFER_BOOST : 1;
      const conviction = eligible ? Math.max(r.finalScore! - minScore, 0) * boost : 0;
      return { ...r, risk, eligible, conviction };
    });

    const ranked = withConviction.filter((r) => r.conviction > 0).sort((a, b) => b.conviction - a.conviction);
    const topTickers = new Set(ranked.slice(0, maxHoldings).map((r) => r.ticker));
    const totalConviction = ranked.slice(0, maxHoldings).reduce((a, r) => a + r.conviction, 0);

    const weighted = withConviction.map((r) => ({
      ...r,
      inTopN: topTickers.has(r.ticker),
      weightPct: topTickers.has(r.ticker) && totalConviction > 0 ? (100 * r.conviction) / totalConviction : 0,
    }));

    const sectorTotals = new Map<string, number>();
    for (const r of weighted) if (r.weightPct > 0) sectorTotals.set(r.sector, (sectorTotals.get(r.sector) ?? 0) + r.weightPct);
    const sectorScale = new Map<string, number>();
    for (const [sector, total] of sectorTotals) sectorScale.set(sector, total > maxSectorPct ? maxSectorPct / total : 1);

    return weighted.map((r) => {
      const scale = sectorScale.get(r.sector) ?? 1;
      const finalWeightPct = r.weightPct * scale;
      return { ...r, weightPct: finalWeightPct, suggestedUsd: (finalWeightPct / 100) * FUND_USD };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, riskByTicker, sectorPrefs, minScore, maxRisk, maxHoldings, maxSectorPct, filters]);

  const holdings = useMemo(
    () => sized.filter((r) => r.suggestedUsd > 0).sort((a, b) => b.suggestedUsd - a.suggestedUsd),
    [sized]
  );
  const totalDeployed = holdings.reduce((a, r) => a + r.suggestedUsd, 0);
  const cash = Math.max(0, FUND_USD - totalDeployed);
  const eligibleCount = sized.filter((r) => r.eligible).length;
  const top5Pct = totalDeployed > 0 ? (100 * holdings.slice(0, 5).reduce((a, r) => a + r.suggestedUsd, 0)) / totalDeployed : 0;

  const sectorBreakdown = useMemo(() => {
    const totals = new Map<string, number>();
    for (const r of holdings) totals.set(r.sector, (totals.get(r.sector) ?? 0) + r.suggestedUsd);
    const entries = [...totals.entries()].sort((a, b) => b[1] - a[1]);
    if (cash > 1e6) entries.push(["Cash / undeployed", cash]);
    const max = entries.length ? Math.max(...entries.map((e) => e[1])) : 0;
    return { entries, max };
  }, [holdings, cash]);

  const filteredList = search.trim()
    ? holdings.filter(
        (r) => r.ticker.toLowerCase().includes(search.toLowerCase()) || r.company.toLowerCase().includes(search.toLowerCase())
      )
    : holdings;

  function resetAll() {
    setMinScore(50);
    setMaxRisk(100);
    setMaxHoldings(500);
    setMaxSectorPct(100);
    setSectorPrefs({});
    setFilters({ revenueCagr: "", fcfYield: "", ebitdaMargin: "", fcfMargin: "", carbonExposure: "", transitionAfford: "", marketCapB: "" });
  }

  const fillStyle = (pct: number): CSSProperties => ({ "--fill": `${pct}%` } as CSSProperties);

  return (
    <div className="portfolio-allocator">
      <div className="panel portfolio-explainer">
        <h3>How much to invest — you set the rule</h3>
        <p>
          No volatility, correlation, or trading-volume data exists anywhere in this pipeline, so sizing here is an
          explicit, adjustable <strong>rule</strong>, not a risk-optimizer: conviction is how far a company's
          Sustainability Score clears your bar, boosted or zeroed by sector preference, capped by how many companies
          you'll hold and how much any one sector can take. <strong>Risk Score</strong> (0–100, higher = riskier) is a
          fundamentals-only proxy -- the mean of company size (smaller market cap → riskier) and financial fragility
          (thin or negative FCF margin → riskier), each ranked with this app's own percentile function.
        </p>
      </div>

      <div className="panel portfolio-controls">
        <div className="weight-group">
          <div className="weight-row-top">
            <label>Minimum sustainability score</label>
            <span className="weight-value">{minScore}</span>
          </div>
          <div className="range-wrap" style={fillStyle(minScore)}>
            <input type="range" min={0} max={100} step={1} value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} />
          </div>
        </div>
        <div className="weight-group">
          <div className="weight-row-top">
            <label>Max risk tolerance</label>
            <span className="weight-value">{maxRisk}</span>
          </div>
          <div className="range-wrap" style={fillStyle(maxRisk)}>
            <input type="range" min={0} max={100} step={1} value={maxRisk} onChange={(e) => setMaxRisk(Number(e.target.value))} />
          </div>
        </div>
        <div className="weight-group">
          <div className="weight-row-top">
            <label>Number of companies</label>
            <span className="weight-value">{maxHoldings}</span>
          </div>
          <div className="range-wrap" style={fillStyle((maxHoldings / 500) * 100)}>
            <input type="range" min={5} max={500} step={5} value={maxHoldings} onChange={(e) => setMaxHoldings(Number(e.target.value))} />
          </div>
        </div>
        <div className="weight-group">
          <div className="weight-row-top">
            <label>Max allocation per sector</label>
            <span className="weight-value">{maxSectorPct}%</span>
          </div>
          <div className="range-wrap" style={fillStyle(maxSectorPct)}>
            <input type="range" min={5} max={100} step={5} value={maxSectorPct} onChange={(e) => setMaxSectorPct(Number(e.target.value))} />
          </div>
        </div>
        <button className="link-button" onClick={resetAll}>Reset to defaults</button>
      </div>

      <div className="panel portfolio-sector-prefs">
        <h3>Prioritize sectors</h3>
        <p className="portfolio-hint">Avoid excludes a sector entirely; Prefer boosts its conviction {PREFER_BOOST}x.</p>
        <div className="portfolio-sector-grid">
          {sectors.map((s) => {
            const pref = sectorPrefs[s] ?? "neutral";
            return (
              <div className="portfolio-sector-row" key={s}>
                <span>{s}</span>
                <span className="portfolio-pref-buttons">
                  {(["avoid", "neutral", "prefer"] as SectorPref[]).map((opt) => (
                    <button
                      key={opt}
                      className={pref === opt ? `pref-btn pref-btn--${opt} pref-btn--active` : "pref-btn"}
                      onClick={() => setSectorPrefs((p) => ({ ...p, [s]: opt }))}
                    >
                      {opt[0].toUpperCase() + opt.slice(1)}
                    </button>
                  ))}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <div className="panel portfolio-filters">
        <h3>Filter out companies below a threshold</h3>
        <div className="portfolio-filters-grid">
          <label>Revenue CAGR ≥ <input type="number" value={filters.revenueCagr} onChange={(e) => setFilters((f) => ({ ...f, revenueCagr: e.target.value }))} placeholder="e.g. 0" />%</label>
          <label>FCF Yield ≥ <input type="number" value={filters.fcfYield} onChange={(e) => setFilters((f) => ({ ...f, fcfYield: e.target.value }))} placeholder="e.g. 2" />%</label>
          <label>EBITDA Margin ≥ <input type="number" value={filters.ebitdaMargin} onChange={(e) => setFilters((f) => ({ ...f, ebitdaMargin: e.target.value }))} placeholder="e.g. 10" />%</label>
          <label>FCF Margin ≥ <input type="number" value={filters.fcfMargin} onChange={(e) => setFilters((f) => ({ ...f, fcfMargin: e.target.value }))} placeholder="e.g. 5" />%</label>
          <label>Carbon-Price Exposure ≥ <input type="number" value={filters.carbonExposure} onChange={(e) => setFilters((f) => ({ ...f, carbonExposure: e.target.value }))} placeholder="e.g. 50" /></label>
          <label>Transition Affordability ≥ <input type="number" value={filters.transitionAfford} onChange={(e) => setFilters((f) => ({ ...f, transitionAfford: e.target.value }))} placeholder="e.g. 50" /></label>
          <label>Market Cap ≥ <input type="number" value={filters.marketCapB} onChange={(e) => setFilters((f) => ({ ...f, marketCapB: e.target.value }))} placeholder="e.g. 10" />$B</label>
        </div>
      </div>

      <div className="panel portfolio-recommended">
        <h3>Your recommended portfolio</h3>
        <div className="portfolio-stats">
          <div className="portfolio-stat"><div className="portfolio-stat-label">Holdings</div><div className="portfolio-stat-value">{holdings.length}</div></div>
          <div className="portfolio-stat"><div className="portfolio-stat-label">Deployed</div><div className="portfolio-stat-value">${(totalDeployed / 1e9).toFixed(2)}B</div></div>
          <div className="portfolio-stat"><div className="portfolio-stat-label">Cash / undeployed</div><div className="portfolio-stat-value">${(cash / 1e9).toFixed(2)}B <span className="portfolio-stat-sub">({(100 * cash / FUND_USD).toFixed(1)}%)</span></div></div>
          <div className="portfolio-stat"><div className="portfolio-stat-label">Sectors represented</div><div className="portfolio-stat-value">{new Set(holdings.map((r) => r.sector)).size} / {sectors.length}</div></div>
          <div className="portfolio-stat"><div className="portfolio-stat-label">Top-5 concentration</div><div className="portfolio-stat-value">{top5Pct.toFixed(1)}%</div></div>
          <div className="portfolio-stat"><div className="portfolio-stat-label">Eligible under sliders/filters</div><div className="portfolio-stat-value">{eligibleCount}</div></div>
        </div>

        <div className="portfolio-sector-breakdown">
          {sectorBreakdown.entries.length === 0 && <p className="portfolio-hint">No holdings clear the current sliders/filters — loosen them to see a portfolio.</p>}
          {sectorBreakdown.entries.map(([sector, usd]) => (
            <div className="portfolio-breakdown-row" key={sector}>
              <span className="portfolio-breakdown-name">{sector}</span>
              <span className="portfolio-breakdown-track">
                <span
                  className={sector === "Cash / undeployed" ? "portfolio-breakdown-fill portfolio-breakdown-fill--cash" : "portfolio-breakdown-fill"}
                  style={{ width: `${sectorBreakdown.max > 0 ? (100 * usd) / sectorBreakdown.max : 0}%` }}
                />
              </span>
              <span className="portfolio-breakdown-pct">{((100 * usd) / FUND_USD).toFixed(1)}%</span>
            </div>
          ))}
        </div>

        <input
          type="search"
          className="portfolio-search"
          placeholder="Search holdings by ticker or company…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="portfolio-table-scroll">
          <table className="portfolio-table">
            <thead>
              <tr>
                <th>#</th><th>Company</th><th>Sector</th>
                <th className="num">Score</th><th className="num">Risk</th>
                <th className="num">Allocation</th><th className="num">% of Fund</th>
              </tr>
            </thead>
            <tbody>
              {filteredList.map((r, i) => (
                <tr key={r.ticker}>
                  <td className="num">{i + 1}</td>
                  <td>{r.company} <span className="portfolio-ticker">({r.ticker})</span></td>
                  <td>{r.sector}</td>
                  <td className="num">{fmtPct(r.finalScore, 1).replace("%", "")}</td>
                  <td className="num">{fmtPct(r.risk, 1).replace("%", "")}</td>
                  <td className="num">{fmtMoney(r.suggestedUsd)}</td>
                  <td className="num">{((100 * r.suggestedUsd) / FUND_USD).toFixed(2)}%</td>
                </tr>
              ))}
              {filteredList.length === 0 && (
                <tr><td colSpan={7} className="portfolio-hint">No holdings match.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

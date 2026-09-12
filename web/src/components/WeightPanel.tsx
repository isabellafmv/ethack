// Task 2: pillar + sub-score weight sliders, presets, and the rank
// sensitivity readout -- "a ranking that collapses under a 10% weight change
// is not a ranking." Rank sensitivity is computed on demand (a button, not
// every slider tick): 30 resampled computeScores() calls is cheap once, but
// running it on every drag frame would make the sliders feel laggy for no
// benefit -- the composite recompute itself already happens live.
import { useState, type CSSProperties } from "react";
import { PILLARS, normalizedWeights, type WeightsState } from "../scoring/pipeline";
import { registryForPillar, type Pillar } from "../scoring/registry";
import { PRESETS, type PresetId, type WeightMode, applyPreset } from "../scoring/weights";
import { rankSensitivity, type RankSpread } from "../scoring/rankSensitivity";
import { PILLAR_SCORE_NAMES } from "../viz/views";
import type { Company } from "../scoring/types";

const SLIDER_MAX = 3;
/** The displayed percentage AND the fill bar both have to track this same
 * value/max ratio -- the same one the native thumb itself is positioned by
 * (0-3, not each pillar's normalized 0-100% share of the total, which
 * depends on the OTHER two sliders too). A slider can only ever honestly
 * represent its OWN position; showing the normalized share next to it read
 * as "the number and the dot disagree" the moment more than one slider
 * differed from its default, because they were never the same quantity. */
const rawPct = (value: number) => Math.round((value / SLIDER_MAX) * 100);

export function WeightPanel({
  weights, onChange, companies, weightMode, onChangeWeightMode, materialityStatus, sensitivityWeights,
}: {
  weights: WeightsState;
  onChange: (w: WeightsState) => void;
  companies: readonly Company[];
  weightMode: WeightMode;
  onChangeWeightMode: (m: WeightMode) => void;
  materialityStatus: "loading" | "ready" | "unavailable";
  sensitivityWeights: WeightsState | Map<string, WeightsState>;
}) {
  const normalized = normalizedWeights(weights);
  const [sensitivity, setSensitivity] = useState<Map<string, RankSpread> | null>(null);
  const [computing, setComputing] = useState(false);
  const isMateriality = weightMode === "materiality";

  const setPillarWeight = (pillar: Pillar, value: number) => {
    onChange({ ...weights, pillars: { ...weights.pillars, [pillar]: value } });
  };
  const setSubWeight = (id: string, value: number) => {
    onChange({ ...weights, subscores: { ...weights.subscores, [id]: value } });
  };
  const runPreset = (preset: PresetId) => {
    onChangeWeightMode("manual");
    onChange(applyPreset(preset, weights));
  };

  const runSensitivity = () => {
    setComputing(true);
    // Yield a frame so the "computing..." state actually paints before the
    // ~30-sample resampling work runs on the main thread.
    requestAnimationFrame(() => {
      setSensitivity(rankSensitivity(companies, sensitivityWeights));
      setComputing(false);
    });
  };

  const topVolatile = sensitivity
    ? [...sensitivity.values()].sort((a, b) => b.spread - a.spread).slice(0, 5)
    : [];
  const medianSpread = sensitivity
    ? median([...sensitivity.values()].map((s) => s.spread))
    : null;

  return (
    <div className="panel weight-panel">
      <h3>Weights</h3>
      <div className="presets">
        {(Object.keys(PRESETS) as PresetId[]).map((id) => (
          <button key={id} onClick={() => runPreset(id)}>{PRESETS[id].label}</button>
        ))}
        <button
          className={isMateriality ? "preset-materiality preset-materiality--active" : "preset-materiality"}
          disabled={materialityStatus !== "ready"}
          onClick={() => onChangeWeightMode(isMateriality ? "manual" : "materiality")}
          title={materialityStatus !== "ready" ? "materiality.json not loaded" : undefined}
        >
          Materiality-weighted (per sector)
        </button>
      </div>
      {isMateriality && (
        <p className="materiality-explainer">
          Each sector scores against its own SASB-style importance weights
          (e.g. Utilities weighs carbon intensity heavily; Financials weighs
          governance instead) -- see data/materiality.csv. The sliders below
          reflect your last manual setting, not what's actually being used.
        </p>
      )}

      {PILLARS.map((pillar) => (
        <div key={pillar} className="weight-group">
          {/* Its own stacked layout, not the 3-column weight-row grid the
              sub-score rows use below -- "Environmental Impact"/"Transition
              risk" are long enough that giving them a fixed label column
              wide enough to avoid truncating squeezed the slider track down
              to a few px in this sidebar's width (the actual cause of a
              "the fill doesn't show" report -- it was rendering, just inside
              an invisibly narrow track, not a browser bug). A full-width
              label row above a full-width slider row has room for both. */}
          <div className="weight-row-top">
            <label>{PILLAR_SCORE_NAMES[pillar]}</label>
            <span className="weight-value">{Math.round(normalized.pillars[pillar] * 100)}%</span>
          </div>
          <div
            className={isMateriality ? "range-wrap range-wrap--disabled" : "range-wrap"}
            style={{ "--fill": `${rawPct(weights.pillars[pillar] ?? 1)}%` } as CSSProperties}
          >
            <input
              type="range" min={0} max={SLIDER_MAX} step={0.05}
              value={weights.pillars[pillar] ?? 1}
              disabled={isMateriality}
              onChange={(e) => setPillarWeight(pillar, Number(e.target.value))}
            />
          </div>
          <details>
            <summary>Sub-scores</summary>
            {registryForPillar(pillar).map((sub) => (
              <div key={sub.id} className="weight-row weight-row--sub">
                <label>{sub.label}</label>
                <div
                  className={isMateriality ? "range-wrap range-wrap--disabled" : "range-wrap"}
                  style={{ "--fill": `${rawPct(weights.subscores[sub.id] ?? 1)}%` } as CSSProperties}
                >
                  <input
                    type="range" min={0} max={SLIDER_MAX} step={0.05}
                    value={weights.subscores[sub.id] ?? 1}
                    disabled={isMateriality}
                    onChange={(e) => setSubWeight(sub.id, Number(e.target.value))}
                  />
                </div>
                <span className="weight-value">{Math.round((normalized.subscores[sub.id] ?? 0) * 100)}%</span>
              </div>
            ))}
          </details>
        </div>
      ))}

      <div className="rank-sensitivity">
        <button onClick={runSensitivity} disabled={computing}>
          {computing ? "Computing..." : "Check rank sensitivity (±10%)"}
        </button>
        {sensitivity && (
          <div className="rank-sensitivity-results">
            <p>Median rank spread across the index: <strong>{medianSpread}</strong> places.</p>
            <p>Most rank-sensitive companies at this weighting:</p>
            <ol>
              {topVolatile.map((s) => (
                <li key={s.ticker}>
                  {s.ticker}: rank #{s.baseRank}, swings #{s.minRank}&ndash;#{s.maxRank} (&Delta;{s.spread})
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </div>
  );
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

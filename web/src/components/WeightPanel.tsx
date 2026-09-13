// Task 2: pillar weight sliders, presets, and the rank sensitivity readout
// -- "a ranking that collapses under a 10% weight change is not a ranking."
// Rank sensitivity is computed on demand (a button, not every slider tick):
// 30 resampled computeScores() calls is cheap once, but running it on every
// drag frame would make the sliders feel laggy for no benefit -- the
// composite recompute itself already happens live.
//
// Sub-score weight sliders were removed from this panel (pillar weights
// only, now) -- weights.subscores stays at its default equal split within
// each pillar, since there's no UI left to change it. computeScores/
// normalizedWeights/materiality mode all still support per-sub-score
// weights underneath; only this control surface shrank.
import { useState, type CSSProperties } from "react";
import { PILLARS, normalizedWeights, type WeightsState } from "../scoring/pipeline";
import type { Pillar } from "../scoring/registry";
import { PRESETS, type PresetId, type WeightMode, applyPreset } from "../scoring/weights";
import { rankSensitivity, type RankSpread } from "../scoring/rankSensitivity";
import { PILLAR_SCORE_NAMES } from "../viz/views";
import type { Company } from "../scoring/types";

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

  // Three sliders that always sum to 100%, not three independent 0-3
  // multipliers renormalized behind the scenes -- dragging one to a target
  // percentage rescales the OTHER two proportionally (preserving their
  // relative ratio to each other) to consume exactly the remaining budget.
  // That's what makes "drag one, watch all three move" true instead of just
  // the number next to the dragged slider changing while its siblings sit
  // still: every slider's `value` is this same normalized share, so a
  // change to any one of them re-renders every thumb's position, not just
  // its label.
  const setPillarWeight = (pillar: Pillar, targetPct: number) => {
    const others = PILLARS.filter((p) => p !== pillar);
    const oldOtherSum = others.reduce((sum, p) => sum + Math.max(0, weights.pillars[p] ?? 1), 0);
    const remaining = 100 - targetPct;
    const rescaledOthers = Object.fromEntries(
      others.map((p) => [
        p,
        oldOtherSum > 0 ? (Math.max(0, weights.pillars[p] ?? 1) / oldOtherSum) * remaining : remaining / others.length,
      ])
    );
    onChange({ ...weights, pillars: { ...weights.pillars, [pillar]: targetPct, ...rescaledOthers } });
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

      {PILLARS.map((pillar) => {
        const pct = Math.round(normalized.pillars[pillar] * 100);
        return (
          <div key={pillar} className="weight-group">
            <div className="weight-row-top">
              <label>{PILLAR_SCORE_NAMES[pillar]}</label>
              <span className="weight-value">{pct}%</span>
            </div>
            <div
              className={isMateriality ? "range-wrap range-wrap--disabled" : "range-wrap"}
              style={{ "--fill": `${pct}%` } as CSSProperties}
            >
              <input
                type="range" min={0} max={100} step={1}
                value={pct}
                disabled={isMateriality}
                onChange={(e) => setPillarWeight(pillar, Number(e.target.value))}
              />
            </div>
          </div>
        );
      })}

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

// Task 2: pillar + sub-score weight sliders, presets, and the rank
// sensitivity readout -- "a ranking that collapses under a 10% weight change
// is not a ranking." Rank sensitivity is computed on demand (a button, not
// every slider tick): 30 resampled computeScores() calls is cheap once, but
// running it on every drag frame would make the sliders feel laggy for no
// benefit -- the composite recompute itself already happens live.
import { useState } from "react";
import { PILLARS, normalizedWeights, type WeightsState } from "../scoring/pipeline";
import { registryForPillar, type Pillar } from "../scoring/registry";
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
          <div className="weight-row">
            <label>{PILLAR_SCORE_NAMES[pillar]}</label>
            <input
              type="range" min={0} max={3} step={0.05}
              value={weights.pillars[pillar] ?? 1}
              disabled={isMateriality}
              onChange={(e) => setPillarWeight(pillar, Number(e.target.value))}
              style={{ background: `linear-gradient(to right, var(--ink) ${Math.round(normalized.pillars[pillar] * 100)}%, var(--ink-12) 0)` }}
            />
            <span className="weight-value">{Math.round(normalized.pillars[pillar] * 100)}%</span>
          </div>
          <details>
            <summary>Sub-scores</summary>
            {registryForPillar(pillar).map((sub) => (
              <div key={sub.id} className="weight-row weight-row--sub">
                <label>{sub.label}</label>
                <input
                  type="range" min={0} max={3} step={0.05}
                  value={weights.subscores[sub.id] ?? 1}
                  disabled={isMateriality}
                  onChange={(e) => setSubWeight(sub.id, Number(e.target.value))}
                  style={{ background: `linear-gradient(to right, var(--ink) ${Math.round((normalized.subscores[sub.id] ?? 0) * 100)}%, var(--ink-12) 0)` }}
                />
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

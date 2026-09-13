// Task 2: pillar weight sliders and presets.
//
// Sub-score weight sliders were removed from this panel (pillar weights
// only, now) -- weights.subscores stays at its default equal split within
// each pillar, since there's no UI left to change it. computeScores/
// normalizedWeights/materiality mode all still support per-sub-score
// weights underneath; only this control surface shrank.
import type { CSSProperties } from "react";
import { PILLARS, normalizedWeights, type WeightsState } from "../scoring/pipeline";
import type { Pillar } from "../scoring/registry";
import { PRESETS, type PresetId, type WeightMode, applyPreset } from "../scoring/weights";
import { PILLAR_SCORE_NAMES } from "../viz/views";

export function WeightPanel({
  weights, onChange, weightMode, onChangeWeightMode, materialityStatus,
}: {
  weights: WeightsState;
  onChange: (w: WeightsState) => void;
  weightMode: WeightMode;
  onChangeWeightMode: (m: WeightMode) => void;
  materialityStatus: "loading" | "ready" | "unavailable";
}) {
  const normalized = normalizedWeights(weights);
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

  return (
    <details className="panel weight-panel">
      <summary>Weights</summary>
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
      <p className="materiality-explainer">
        These sliders/presets set the <strong>Composite</strong> weighting only --
        on the Map view (Environmental / Transition / Governance axes), each
        pillar shows its own unweighted score, so dragging a slider here won't
        move a point unless you switch an axis to Composite.
      </p>

      {isMateriality && (
        <p className="materiality-explainer">
          Each sector scores against its own SASB-style importance weights
          (e.g. Utilities weighs carbon intensity heavily; Financials weighs
          governance instead) -- see data/materiality.csv. Unlike the presets
          above, this reweights the sub-scores <em>within</em> each pillar, so
          it's the one mode that does move points on the Map view. The sliders
          below reflect your last manual setting, not what's actually being used.
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
    </details>
  );
}

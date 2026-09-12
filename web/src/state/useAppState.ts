// All viewer-adjustable state that isn't the loaded payload itself: weights
// (persisted to the URL hash per Task 2 -- "a specific view is shareable and
// reproducible"), sector filter, active view + its axis selections,
// reference point, and the selected company for the detail panel.
import { useCallback, useEffect, useMemo, useState } from "react";
import { defaultWeights, type WeightsState } from "../scoring/pipeline";
import {
  decodeWeightModeFromHash, decodeWeightsFromHash,
  encodeWeightModeToHash, encodeWeightsToHash, type WeightMode,
} from "../scoring/weights";
import type { ReferenceSpec } from "../scoring/reference";
import { VIEWS, viewById, type AxisSlot, type ViewConfig } from "../viz/views";

export interface AppState {
  weights: WeightsState;
  setWeights: (w: WeightsState) => void;
  weightMode: WeightMode;
  setWeightMode: (m: WeightMode) => void;
  selectedSectors: Set<string>;
  toggleSector: (sector: string, allSectors: string[]) => void;
  clearSectorFilter: () => void;
  activeViewId: ViewConfig["id"];
  setActiveViewId: (id: ViewConfig["id"]) => void;
  axes: [AxisSlot, AxisSlot, AxisSlot];
  setAxis: (slot: 0 | 1 | 2, axis: AxisSlot) => void;
  reference: ReferenceSpec;
  setReference: (r: ReferenceSpec) => void;
  deltaMode: "raw" | "sector_adjusted";
  setDeltaMode: (m: "raw" | "sector_adjusted") => void;
  selectedTicker: string | null;
  setSelectedTicker: (t: string | null) => void;
}

export function useAppState(): AppState {
  const [weights, setWeightsState] = useState<WeightsState>(
    () => decodeWeightsFromHash(window.location.hash) ?? defaultWeights()
  );
  const [weightMode, setWeightModeState] = useState<WeightMode>(
    () => decodeWeightModeFromHash(window.location.hash)
  );
  const [selectedSectors, setSelectedSectors] = useState<Set<string>>(new Set());
  const [activeViewId, setActiveViewId] = useState<ViewConfig["id"]>("global");
  const [axesByView, setAxesByView] = useState<Record<string, [AxisSlot, AxisSlot, AxisSlot]>>(
    () => Object.fromEntries(VIEWS.map((v) => [v.id, v.defaultAxes]))
  );
  const [reference, setReference] = useState<ReferenceSpec>({ mode: "sector_median" });
  const [deltaMode, setDeltaMode] = useState<"raw" | "sector_adjusted">("sector_adjusted");
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);

  // `mode=` is only ever appended when non-manual, so a manual-mode URL is
  // byte-identical to what it was before weight modes existed at all.
  const writeHash = useCallback((w: WeightsState, mode: WeightMode) => {
    const modeSeg = encodeWeightModeToHash(mode);
    window.history.replaceState(null, "", `#${modeSeg ? `${encodeWeightsToHash(w)}&${modeSeg}` : encodeWeightsToHash(w)}`);
  }, []);

  const setWeights = useCallback((w: WeightsState) => {
    setWeightsState(w);
    writeHash(w, weightMode);
  }, [weightMode, writeHash]);

  // Sliders always write through to `weights` regardless of mode (see
  // WeightPanel), so switching back to manual needs no separate stash --
  // whatever was last set is still sitting there, untouched.
  const setWeightMode = useCallback((m: WeightMode) => {
    setWeightModeState(m);
    writeHash(weights, m);
  }, [weights, writeHash]);

  // A shared link should reproduce the weights (and mode) it was copied at,
  // including back/forward through browser history.
  useEffect(() => {
    const onHashChange = () => {
      const fromHash = decodeWeightsFromHash(window.location.hash);
      if (fromHash) setWeightsState(fromHash);
      setWeightModeState(decodeWeightModeFromHash(window.location.hash));
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  // `selectedSectors` empty means "all visible" -- a shorthand, not a literal
  // empty selection. Toggling must expand that shorthand to the full set
  // first, so unchecking one sector out of "all visible" excludes just that
  // one sector rather than collapsing to "only this one" (checkbox semantics
  // a viewer would otherwise read as inverted).
  const toggleSector = useCallback((sector: string, allSectors: string[]) => {
    setSelectedSectors((prev) => {
      const effective = prev.size === 0 ? new Set(allSectors) : new Set(prev);
      if (effective.has(sector)) effective.delete(sector);
      else effective.add(sector);
      return effective.size === allSectors.length ? new Set() : effective;
    });
  }, []);
  const clearSectorFilter = useCallback(() => setSelectedSectors(new Set()), []);

  const setAxis = useCallback((slot: 0 | 1 | 2, axis: AxisSlot) => {
    setAxesByView((prev) => {
      const current = [...(prev[activeViewId] ?? viewById(activeViewId).defaultAxes)] as [AxisSlot, AxisSlot, AxisSlot];
      current[slot] = axis;
      return { ...prev, [activeViewId]: current };
    });
  }, [activeViewId]);

  const axes = useMemo(
    () => axesByView[activeViewId] ?? viewById(activeViewId).defaultAxes,
    [axesByView, activeViewId]
  );

  return {
    weights, setWeights,
    weightMode, setWeightMode,
    selectedSectors, toggleSector, clearSectorFilter,
    activeViewId, setActiveViewId,
    axes, setAxis,
    reference, setReference,
    deltaMode, setDeltaMode,
    selectedTicker, setSelectedTicker,
  };
}

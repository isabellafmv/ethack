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

/** The one place "is this sector currently visible" is decided -- `null`
 * means "show everything" (the default, and what "Select all" resets to),
 * distinct from an explicit empty Set (every sector deselected via "Unselect
 * all", which shows nothing). ScatterView, the composite/coverage calc in
 * App.tsx, and TableView all need the exact same answer to this question; a
 * second reimplementation is how the table and the 3D view end up
 * disagreeing about which companies are in scope. */
export function isSectorVisible(sector: string, selectedSectors: ReadonlySet<string> | null): boolean {
  return selectedSectors === null || selectedSectors.has(sector);
}

export interface AppState {
  weights: WeightsState;
  setWeights: (w: WeightsState) => void;
  weightMode: WeightMode;
  setWeightMode: (m: WeightMode) => void;
  selectedSectors: Set<string> | null;
  toggleSector: (sector: string, allSectors: string[]) => void;
  clearSectorFilter: () => void;
  selectNoSectors: () => void;
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
  const [selectedSectors, setSelectedSectors] = useState<Set<string> | null>(null);
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

  // `null` means "all visible" -- a shorthand for "every sector, including
  // ones not loaded yet", not a literal Set. Toggling must expand that
  // shorthand to the full set first, so unchecking one sector out of "all
  // visible" excludes just that one sector rather than collapsing to "only
  // this one" (checkbox semantics a viewer would otherwise read as
  // inverted). Ending up back at the full set collapses to `null` too, so
  // "Select all" and manually re-checking every box land in the same state.
  const toggleSector = useCallback((sector: string, allSectors: string[]) => {
    setSelectedSectors((prev) => {
      const effective = prev === null ? new Set(allSectors) : new Set(prev);
      if (effective.has(sector)) effective.delete(sector);
      else effective.add(sector);
      return effective.size === allSectors.length ? null : effective;
    });
  }, []);
  const clearSectorFilter = useCallback(() => setSelectedSectors(null), []);
  // Explicit empty Set, not `null` -- `null` means "all visible", so hiding
  // every sector needs its own literal (empty) selection to be distinguishable.
  const selectNoSectors = useCallback(() => setSelectedSectors(new Set()), []);

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
    selectedSectors, toggleSector, clearSectorFilter, selectNoSectors,
    activeViewId, setActiveViewId,
    axes, setAxis,
    reference, setReference,
    deltaMode, setDeltaMode,
    selectedTicker, setSelectedTicker,
  };
}

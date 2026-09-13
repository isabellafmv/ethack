import { useMemo, useState } from "react";
import { useMatrix } from "./data/useMatrix";
import { useMaterialityWeights } from "./data/useMaterialityWeights";
import { useAppState, isSectorVisible } from "./state/useAppState";
import { computeScores, weightsForSector, type WeightsState } from "./scoring/pipeline";
import { resolveReference } from "./scoring/reference";
import { VIEWS, viewById } from "./viz/views";
import { axisCoverage } from "./viz/coverage";
import { ScatterView, CAMERA_PRESETS, type CameraPresetId } from "./viz/ScatterView";
import { AxisPickers } from "./viz/AxisPickers";
import { FixtureBadge } from "./components/FixtureBadge";
import { ProvenanceFooter } from "./components/ProvenanceFooter";
import { SectorFilter } from "./components/SectorFilter";
import { Legend } from "./components/Legend";
import { CoverageStrip } from "./components/CoverageStrip";
// import { ReferencePicker } from "./components/ReferencePicker"; -- parked, see the app-sidebar--right JSX below
import { WeightPanel } from "./components/WeightPanel";
import { DetailPanel } from "./components/DetailPanel";
import { SearchBox } from "./components/SearchBox";
import { TableView } from "./components/TableView";
import { PortfolioAllocator } from "./components/PortfolioAllocator";
import "./App.css";

type DisplayMode = "3d" | "table" | "portfolio";

export default function App() {
  const matrix = useMatrix();
  const materiality = useMaterialityWeights();
  const state = useAppState();
  const [cameraPreset, setCameraPreset] = useState<CameraPresetId | null>("isometric");
  const [displayMode, setDisplayMode] = useState<DisplayMode>("3d");

  const companies = matrix.payload?.companies ?? [];

  // In materiality mode, each company scores against its OWN sector's
  // importance weights instead of one global set -- see computeScores'
  // per-sector Map support. Falls back to the manual weights whenever
  // materiality.json hasn't loaded (or failed to), so materiality mode is
  // never something the rest of the app has to guard against being absent.
  const effectiveWeights = useMemo<WeightsState | Map<string, WeightsState>>(
    () => (state.weightMode === "materiality" && materiality.status === "ready" ? materiality.weights! : state.weights),
    [state.weightMode, materiality.status, materiality.weights, state.weights]
  );

  // Percentiles are sector-relative and computed over the FULL universe --
  // sector filtering below is a display concern only (see pipeline.ts's own
  // note on this), so `scores` never depends on the filter.
  const scores = useMemo(() => computeScores(companies, effectiveWeights), [companies, effectiveWeights]);

  const sectorCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const c of companies) m.set(c.sector, (m.get(c.sector) ?? 0) + 1);
    return m;
  }, [companies]);

  const referenceBySector = useMemo(() => {
    const m = new Map<string, ReturnType<typeof resolveReference>>();
    for (const sector of sectorCounts.keys()) m.set(sector, resolveReference(companies, state.reference, sector));
    return m;
  }, [companies, sectorCounts, state.reference]);

  const view = viewById(state.activeViewId);

  const visibleResults = useMemo(() => {
    const out = [];
    for (const c of companies) {
      if (!isSectorVisible(c.sector, state.selectedSectors)) continue;
      const r = scores.get(c.ticker);
      if (r) out.push(r);
    }
    return out;
  }, [companies, scores, state.selectedSectors]);

  const coverages = useMemo(
    () => state.axes.map((axis) => axisCoverage(axis, visibleResults)),
    [state.axes, visibleResults]
  );

  const selectedCompany = state.selectedTicker
    ? companies.find((c) => c.ticker === state.selectedTicker) ?? null
    : null;
  const selectedResult = state.selectedTicker ? scores.get(state.selectedTicker) ?? null : null;

  if (matrix.status === "loading") {
    return <div className="center-message">Loading sustainability data...</div>;
  }
  if (matrix.status === "error" || !matrix.payload) {
    return (
      <div className="error-banner">
        <h1>Data failed to load</h1>
        <p>{matrix.error}</p>
      </div>
    );
  }

  return (
    <div className="app-shell">
      {matrix.isFixture && <FixtureBadge />}
      <header className="app-header">
        <h1 className="app-title">S&amp;P 500 Sustainability Map</h1>
        <p className="app-subtitle">A 3D view of environmental, transition &amp; governance impact</p>
      </header>
      <div className="app-toolbar">
        <nav className="view-tabs">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              className={v.id === state.activeViewId ? "view-tab view-tab--active" : "view-tab"}
              onClick={() => state.setActiveViewId(v.id)}
            >
              {v.label}
            </button>
          ))}
        </nav>
        <SearchBox companies={companies} onSelect={state.setSelectedTicker} />
      </div>

      <div className="app-body">
        <aside className="app-sidebar app-sidebar--left">
          <SectorFilter
            sectorCounts={sectorCounts}
            selected={state.selectedSectors}
            onToggle={state.toggleSector}
            onClear={state.clearSectorFilter}
          />
          <CoverageStrip coverages={coverages} />
        </aside>

        <main className="app-main">
          <div className="display-mode-toggle">
            <button
              className={displayMode === "3d" ? "display-mode-tab display-mode-tab--active" : "display-mode-tab"}
              onClick={() => setDisplayMode("3d")}
            >
              3D
            </button>
            <button
              className={displayMode === "table" ? "display-mode-tab display-mode-tab--active" : "display-mode-tab"}
              onClick={() => setDisplayMode("table")}
            >
              Table
            </button>
            <button
              className={displayMode === "portfolio" ? "display-mode-tab display-mode-tab--active" : "display-mode-tab"}
              onClick={() => setDisplayMode("portfolio")}
            >
              Portfolio
            </button>
          </div>
          {displayMode === "3d" && (
            <AxisPickers view={view} axes={state.axes} onChange={state.setAxis} weights={state.weights} />
          )}
          {displayMode === "3d" && (
            <div className="camera-presets">
              {(Object.keys(CAMERA_PRESETS) as CameraPresetId[]).map((p) => (
                <button
                  key={p}
                  className={p === cameraPreset ? "camera-preset camera-preset--active" : "camera-preset"}
                  onClick={() => setCameraPreset(p)}
                >
                  {p}
                </button>
              ))}
            </div>
          )}
          {displayMode !== "portfolio" && (
            <div className="scatter-container">
              {displayMode === "3d" ? (
                <ScatterView
                  companies={companies}
                  scores={scores}
                  axes={state.axes}
                  visibleSectors={state.selectedSectors}
                  referenceBySector={referenceBySector}
                  weights={effectiveWeights}
                  onSelectCompany={state.setSelectedTicker}
                  cameraPreset={cameraPreset}
                />
              ) : (
                <TableView
                  companies={companies}
                  scores={scores}
                  visibleSectors={state.selectedSectors}
                  onSelectCompany={state.setSelectedTicker}
                />
              )}
            </div>
          )}
          {displayMode === "portfolio" && (
            <div className="portfolio-container">
              <PortfolioAllocator companies={companies} scores={scores} />
            </div>
          )}
        </main>

        <aside className="app-sidebar app-sidebar--right">
          <Legend />
          <WeightPanel
            weights={state.weights}
            onChange={state.setWeights}
            companies={companies}
            weightMode={state.weightMode}
            onChangeWeightMode={state.setWeightMode}
            materialityStatus={materiality.status}
            sensitivityWeights={effectiveWeights}
          />
          {/* ReferencePicker parked, not deleted -- state.reference/deltaMode
              (and the coloring/delta logic everywhere that reads them) are
              untouched, just fixed at their defaults (sector median,
              sector-adjusted) with no UI to change them for now. */}
          {/* <ReferencePicker
            reference={state.reference}
            onChangeReference={state.setReference}
            deltaMode={state.deltaMode}
            onChangeDeltaMode={state.setDeltaMode}
            companies={companies}
          /> */}
        </aside>

        {selectedCompany && selectedResult && (
          <DetailPanel
            company={selectedCompany}
            result={selectedResult}
            urls={matrix.payload.urls}
            weights={weightsForSector(effectiveWeights, selectedCompany.sector)}
            isFixture={matrix.isFixture}
            onClose={() => state.setSelectedTicker(null)}
          />
        )}
      </div>

      <ProvenanceFooter
        schemaVersion={matrix.payload.schema_version}
        analysisYear={matrix.payload.analysis_year}
      />
    </div>
  );
}

// 11 GICS sectors, multi-select, with counts. `selected === null` means "show
// everything" -- filtering only ever narrows the DISPLAYED set; percentiles
// are still computed over the full universe (see App.tsx), because a
// company's sector-relative rank must not shift just because a viewer hid an
// unrelated sector.
export function SectorFilter({
  sectorCounts, selected, onToggle, onSelectAll, onSelectNone,
}: {
  sectorCounts: Map<string, number>;
  selected: Set<string> | null;
  onToggle: (sector: string, allSectors: string[]) => void;
  onSelectAll: () => void;
  onSelectNone: () => void;
}) {
  const sectors = [...sectorCounts.keys()].sort();
  const handleToggle = (sector: string) => onToggle(sector, sectors);
  return (
    <details className="panel sector-filter">
      <summary>Sectors</summary>
      <div className="sector-filter-actions">
        <button className="link-button" onClick={onSelectAll} disabled={selected === null}>
          Select all
        </button>
        <button className="link-button" onClick={onSelectNone} disabled={selected !== null && selected.size === 0}>
          Unselect all
        </button>
      </div>
      <ul>
        {sectors.map((sector) => (
          <li key={sector}>
            <label>
              <input
                type="checkbox"
                checked={selected === null || selected.has(sector)}
                onChange={() => handleToggle(sector)}
              />
              {sector} <span className="count">({sectorCounts.get(sector)})</span>
            </label>
          </li>
        ))}
      </ul>
    </details>
  );
}

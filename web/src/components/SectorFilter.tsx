// 11 GICS sectors, multi-select, with counts. An empty selection means "show
// everything" -- filtering only ever narrows the DISPLAYED set; percentiles
// are still computed over the full universe (see App.tsx), because a
// company's sector-relative rank must not shift just because a viewer hid an
// unrelated sector.
export function SectorFilter({
  sectorCounts, selected, onToggle, onClear,
}: {
  sectorCounts: Map<string, number>;
  selected: Set<string>;
  onToggle: (sector: string, allSectors: string[]) => void;
  onClear: () => void;
}) {
  const sectors = [...sectorCounts.keys()].sort();
  const handleToggle = (sector: string) => onToggle(sector, sectors);
  return (
    <div className="panel sector-filter">
      <div className="panel-header">
        <h3>Sectors</h3>
        {selected.size > 0 && <button className="link-button" onClick={onClear}>show all</button>}
      </div>
      <ul>
        {sectors.map((sector) => (
          <li key={sector}>
            <label>
              <input
                type="checkbox"
                checked={selected.size === 0 || selected.has(sector)}
                onChange={() => handleToggle(sector)}
              />
              {sector} <span className="count">({sectorCounts.get(sector)})</span>
            </label>
          </li>
        ))}
      </ul>
    </div>
  );
}

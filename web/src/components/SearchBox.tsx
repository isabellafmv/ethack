// Search / jump-to-company (Task 7).
import { useState } from "react";
import type { Company } from "../scoring/types";

export function SearchBox({ companies, onSelect }: { companies: readonly Company[]; onSelect: (ticker: string) => void }) {
  const [query, setQuery] = useState("");
  const matches = query.length > 0
    ? companies.filter((c) => c.ticker.toLowerCase().includes(query.toLowerCase()) || c.name.toLowerCase().includes(query.toLowerCase())).slice(0, 8)
    : [];
  return (
    <div className="search-box">
      <input
        type="text"
        placeholder="Search company or ticker..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      {matches.length > 0 && (
        <ul className="search-results">
          {matches.map((c) => (
            <li key={c.ticker}>
              <button onClick={() => { onSelect(c.ticker); setQuery(""); }}>{c.ticker} &mdash; {c.name}</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

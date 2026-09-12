// Tiny RFC4180 CSV parser shared by every data/*.csv-reading build script
// (make-fixture.ts, make-materiality.ts). Handles quoted fields with
// embedded commas/quotes -- both data/wide_FY2025.csv (company names like
// "Booking Holdings, Inc.") and data/materiality.csv (a quoted, comma-
// containing rationale column) need it, so it lives here once rather than
// twice.
export function parseCsv(text: string): Record<string, string>[] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else inQuotes = false;
      } else field += ch;
    } else if (ch === '"') inQuotes = true;
    else if (ch === ",") { row.push(field); field = ""; }
    else if (ch === "\n") {
      if (text[i - 1] !== "\r" || field !== "" || row.length > 0) {
        row.push(field); field = "";
        rows.push(row); row = [];
      }
    } else if (ch === "\r") { /* skip, handled with \n */ }
    else field += ch;
  }
  if (field !== "" || row.length > 0) { row.push(field); rows.push(row); }
  const header = rows[0];
  return rows.slice(1).filter((r) => r.length === header.length).map((r) => {
    const obj: Record<string, string> = {};
    header.forEach((h, i) => (obj[h] = r[i]));
    return obj;
  });
}

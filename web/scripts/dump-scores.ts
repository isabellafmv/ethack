// Runs the real scoring engine (registry.ts + pipeline.ts) against the
// committed matrix.json and dumps per-company results as JSON, so the
// numbers can be inspected/visualized without a running React app.
import { readFileSync, writeFileSync } from "node:fs";
import { computeScores, defaultWeights } from "../src/scoring/pipeline";
import type { MatrixPayload } from "../src/scoring/types";

const matrixPath = process.argv[2] ?? "public/data/matrix.json";
const outPath = process.argv[3] ?? "public/data/scores_dump.json";

const matrix: MatrixPayload = JSON.parse(readFileSync(matrixPath, "utf-8"));
const results = computeScores(matrix.companies, defaultWeights());

const rows = matrix.companies.map((c) => {
  const r = results.get(c.ticker)!;
  const byId = (pillar: "P1" | "P2" | "P3") =>
    Object.fromEntries(r.pillars[pillar].subScores.map((s) => [s.id, s.score]));
  return {
    ticker: c.ticker,
    company: c.name,
    sector: c.sector,
    composite: r.composite,
    p1_score: r.pillars.P1.score,
    p2_score: r.pillars.P2.score,
    p3_score: r.pillars.P3.score,
    p2_subscores: byId("P2"),
    p3_subscores: byId("P3"),
    p2_coverage: Object.fromEntries(r.pillars.P2.subScores.map((s) => [s.id, s.coverageN])),
    p3_coverage: Object.fromEntries(r.pillars.P3.subScores.map((s) => [s.id, s.coverageN])),
  };
});

writeFileSync(outPath, JSON.stringify(rows));
console.log(`wrote ${outPath} — ${rows.length} companies`);
console.log("P2 scored:", rows.filter((r) => r.p2_score !== null).length);
console.log("P3 scored:", rows.filter((r) => r.p3_score !== null).length);

// Task 8's second opinion: scoring has exactly one RUNTIME implementation
// (this TypeScript registry), which is correct -- two live implementations
// drift -- but it means a formula bug in the registry would be invisible.
// `score_calculation/score.py` (Lane A, not this file's job to write) is a
// CHECKER, not a producer: it computes the same sub-scores at default
// weights from the same matrix.json and writes data/scores_oracle.csv.
// This script is the other half of that check -- it asserts TS and Python
// agree within 1e-6 on every (ticker, sub-score) pair.
//
// THE CONTRACT for data/scores_oracle.csv (this is what score.py must
// produce -- tell Lane A before they write it, per Task 8):
//   Long-format CSV, header exactly: ticker,subscore_id,value
//   - `ticker`: canonical ticker, matching matrix.json's companies[].ticker
//   - `subscore_id`: one of the ids in web/src/scoring/registry.ts (e.g.
//     "p1_carbon_intensity")
//   - `value`: the sector percentile score (0-100, ALREADY polarity-adjusted
//     so 100 is always "best"), computed at the registry's DEFAULT weights
//     (equal weight within each pillar -- see scoring/pipeline.ts
//     defaultWeights()). Same definition as SubScoreResult.score in
//     pipeline.ts, not the raw computed value before percentile-ranking.
//   - Omit a row entirely for a company/sub-score with no score (matches
//     this codebase's "null is not zero" rule) -- do not write 0 or blank.
//
// Run with `npm run oracle` first (produces the CSV), then `npm run
// verify:oracle`.
import { readFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { computeScores, defaultWeights } from "../src/scoring/pipeline";
import { REGISTRY } from "../src/scoring/registry";
import type { MatrixPayload } from "../src/scoring/types";

const TOLERANCE = 1e-6;
const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "..", "..");
const MATRIX_PATH = resolve(REPO_ROOT, "web", "public", "data", "matrix.json");
const ORACLE_CSV_PATH = resolve(REPO_ROOT, "data", "scores_oracle.csv");

interface OracleRow {
  ticker: string;
  subscoreId: string;
  value: number;
}

function parseOracleCsv(text: string): OracleRow[] {
  const lines = text.trim().split("\n");
  const header = lines[0].split(",").map((h) => h.trim());
  const tickerIdx = header.indexOf("ticker");
  const subIdx = header.indexOf("subscore_id");
  const valIdx = header.indexOf("value");
  if (tickerIdx === -1 || subIdx === -1 || valIdx === -1) {
    throw new Error(`scores_oracle.csv header must be "ticker,subscore_id,value", got "${lines[0]}"`);
  }
  return lines.slice(1).filter(Boolean).map((line) => {
    const cols = line.split(",");
    return { ticker: cols[tickerIdx], subscoreId: cols[subIdx], value: Number(cols[valIdx]) };
  });
}

function main() {
  if (!existsSync(MATRIX_PATH)) {
    console.error(`No matrix.json at ${MATRIX_PATH}. Run "npm run data" first.`);
    process.exit(1);
  }
  if (!existsSync(ORACLE_CSV_PATH)) {
    console.error(
      `No oracle output at ${ORACLE_CSV_PATH}. Run "npm run oracle" first ` +
      `(needs score_calculation/score.py -- see the CONTRACT comment at the ` +
      `top of this file for the CSV shape it must produce).`
    );
    process.exit(1);
  }

  const payload = JSON.parse(readFileSync(MATRIX_PATH, "utf-8")) as MatrixPayload;
  const tsScores = computeScores(payload.companies, defaultWeights());
  const validIds = new Set(REGISTRY.map((s) => s.id));

  const oracleRows = parseOracleCsv(readFileSync(ORACLE_CSV_PATH, "utf-8"));

  const disagreements: { ticker: string; subscoreId: string; ts: number | null; oracle: number; diff: number }[] = [];
  let compared = 0;
  for (const row of oracleRows) {
    if (!validIds.has(row.subscoreId)) {
      console.warn(`oracle CSV references unknown sub-score id "${row.subscoreId}" (ticker ${row.ticker}) -- skipping`);
      continue;
    }
    const companyResult = tsScores.get(row.ticker);
    if (!companyResult) {
      console.warn(`oracle CSV references unknown ticker "${row.ticker}" -- skipping`);
      continue;
    }
    const sub = REGISTRY.find((s) => s.id === row.subscoreId)!;
    const tsResult = companyResult.pillars[sub.pillar].subScores.find((s) => s.id === row.subscoreId);
    const tsValue = tsResult?.score ?? null;
    compared++;
    const diff = tsValue === null ? NaN : Math.abs(tsValue - row.value);
    if (tsValue === null || diff > TOLERANCE) {
      disagreements.push({ ticker: row.ticker, subscoreId: row.subscoreId, ts: tsValue, oracle: row.value, diff });
    }
  }

  console.log(`Compared ${compared} (ticker, sub-score) pairs against the oracle.`);
  if (disagreements.length === 0) {
    console.log(`PASS -- TS and Python agree within ${TOLERANCE} on all rows.`);
    return;
  }

  disagreements.sort((a, b) => (Number.isNaN(b.diff) ? 1 : b.diff) - (Number.isNaN(a.diff) ? 1 : a.diff));
  console.error(`FAIL -- ${disagreements.length} disagreement(s). Worst offenders:`);
  for (const d of disagreements.slice(0, 20)) {
    console.error(`  ${d.ticker} / ${d.subscoreId}: TS=${d.ts ?? "null"} oracle=${d.oracle} diff=${d.diff}`);
  }
  process.exit(1);
}

main();

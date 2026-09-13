// Shapes mirror pipeline/export_matrix.py's payload exactly. Do not rename a
// key here without renaming it there in the same change -- this file and
// export_matrix.py are two halves of one contract.

export type Status =
  | "structural"
  | "quote_verified"
  | "imputed"
  | "not_disclosed"
  | "quote_failed";

/** Statuses whose value may be trusted downstream (mirrors schema.py TRUSTED). */
export const TRUSTED_STATUSES: ReadonlySet<Status> = new Set([
  "structural",
  "quote_verified",
  "imputed",
]);

/** The distribution a percentile is computed over excludes anything not a
 * direct measurement -- imputed values are scored against it but never widen
 * it. Mirrors the "computed over companies with a real value only" rule. */
export const MEASURED_STATUSES: ReadonlySet<Status> = new Set([
  "structural",
  "quote_verified",
]);

export interface FieldRecord {
  v: number | string | boolean;
  u: string | null;
  fy: number;
  src: string;
  st: Status;
  c: number;
  url: number;
}

export interface SchemaField {
  unit: string | null;
  pillar: string;
  dtype: string;
  description: string;
}

export interface Company {
  ticker: string;
  name: string;
  sector: string;
  sub_industry: string;
  fields: Record<string, FieldRecord>;
  alternatives: Record<string, FieldRecord[]>;
  confidence: number;
}

export interface MatrixPayload {
  schema_version: number;
  generated_at: string;
  analysis_year: number;
  schema: Record<string, SchemaField>;
  source_priority: string[];
  urls: string[];
  companies: Company[];
}

export interface QuotesPayload {
  schema_version: number;
  generated_at: string;
  quotes: Record<string, Record<string, string>>;
}

/** Coerces one FieldRecord.v to a number (booleans -> 1/0), NaN for anything
 * that isn't numeric. Shared by pipeline.ts (per-field resolution) and
 * registry.ts (cross-company aggregate compute()s, e.g. sector-level
 * benchmarks that read raw FieldRecord values directly rather than going
 * through resolveInputs) so there is exactly one coercion rule in the
 * codebase. A categorical string field (e.g. sbti_target_type) coerces to
 * NaN here -- pipeline.ts layers its own category-code lookup on top of
 * this for the one sub-score that needs it, rather than teaching this
 * shared primitive about any specific field's vocabulary. */
export function coerceFieldValue(v: number | string | boolean | undefined): number {
  if (v === undefined) return NaN;
  if (typeof v === "boolean") return v ? 1 : 0;
  if (typeof v === "number") return v;
  const n = Number(v);
  return Number.isFinite(n) ? n : NaN;
}

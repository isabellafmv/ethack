// Boot-time data loading. Tries the real payload first, falls back to the
// fixture, and never renders a silent guess: a truncated/malformed payload or
// a registry/schema mismatch surfaces as a named error, not an empty screen.
//
// Real vs fixture is a loud, persistent distinction (see FIXTURE DATA badge
// in Shell.tsx) -- "someone will demo this by accident" is the whole reason
// this file exists rather than a plain fetch in App.tsx.
import { useEffect, useState } from "react";
import { assertRegistryMatchesSchema } from "../scoring/registry";
import type { MatrixPayload, QuotesPayload } from "../scoring/types";

export interface MatrixState {
  status: "loading" | "ready" | "error";
  payload: MatrixPayload | null;
  isFixture: boolean;
  error: string | null;
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} -> HTTP ${res.status}`);
  return (await res.json()) as T;
}

function validateShape(payload: unknown): asserts payload is MatrixPayload {
  const p = payload as Partial<MatrixPayload> | null;
  if (!p || typeof p !== "object") throw new Error("payload is not an object");
  if (typeof p.schema_version !== "number") throw new Error("payload.schema_version missing or not a number");
  if (!p.schema || typeof p.schema !== "object") throw new Error("payload.schema missing");
  if (!Array.isArray(p.companies)) throw new Error("payload.companies missing or not an array");
  if (!Array.isArray(p.urls)) throw new Error("payload.urls missing or not an array");
}

/** Loads matrix.json, falling back to matrix.fixture.json. Runs the boot-time
 * registry/schema contract check (assertRegistryMatchesSchema) before ever
 * marking data 'ready' -- a renamed or dropped field must break loudly here,
 * not produce an empty axis three components downstream. */
export function useMatrix(): MatrixState {
  const [state, setState] = useState<MatrixState>({
    status: "loading",
    payload: null,
    isFixture: false,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let payload: unknown;
      let isFixture = false;
      try {
        payload = await fetchJson<unknown>("/data/matrix.json");
      } catch {
        isFixture = true;
        try {
          payload = await fetchJson<unknown>("/data/matrix.fixture.json");
        } catch (fixtureErr) {
          if (!cancelled) {
            setState({
              status: "error", payload: null, isFixture: true,
              error: `Could not load matrix.json or matrix.fixture.json: ${(fixtureErr as Error).message}`,
            });
          }
          return;
        }
      }
      try {
        validateShape(payload);
        assertRegistryMatchesSchema(payload.schema);
      } catch (err) {
        if (!cancelled) {
          setState({ status: "error", payload: null, isFixture, error: (err as Error).message });
        }
        return;
      }
      if (!cancelled) setState({ status: "ready", payload, isFixture, error: null });
    })();
    return () => { cancelled = true; };
  }, []);

  return state;
}

let quotesCache: Promise<QuotesPayload> | null = null;

/** Lazily loads quotes.json (or the fixture variant), once, on first call --
 * the quote is the demo but is not needed to draw a point, per the payload
 * split in pipeline/export_matrix.py. */
export function loadQuotes(isFixture: boolean): Promise<QuotesPayload> {
  if (!quotesCache) {
    const url = isFixture ? "/data/quotes.fixture.json" : "/data/quotes.json";
    quotesCache = fetchJson<QuotesPayload>(url).catch((err) => {
      quotesCache = null;
      throw err;
    });
  }
  return quotesCache;
}

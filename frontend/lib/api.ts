/**
 * Live-API bridge (used when NEXT_PUBLIC_USE_FIXTURES="0" or toggled to LIVE API).
 * The UI must never crash if backend is unreachable: gracefully fall back.
 */

import { API_BASE } from "./config";
import type { AuditEvent, GraphElements, RecommendResult, ReviewDecision } from "./types";

export type StageStep = { n: number; step?: "a" | "b" | "arm" };

export interface CalibrationPayload {
  gauge_id: string;
  as_found_error_mm: number;
  as_found_u_mm: number;
  result?: string;
  direct?: boolean;
}

export interface ScopeInput {
  material?: string;
  process?: string;
  machine?: string;
  feature_class?: string;
  tolerance_band?: string;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${path} -> ${res.status}: ${text}`);
    }
    return (await res.json()) as T;
  } catch (err) {
    console.warn(`[liveApi] post ${path} error:`, err);
    throw err;
  }
}

export const liveApi = {
  graph: async (): Promise<GraphElements> => {
    const res = await fetch(`${API_BASE}/graph`);
    if (!res.ok) throw new Error(`/graph -> ${res.status}`);
    const data = await res.json();
    return (data.elements || data) as GraphElements;
  },

  memory: async (id: string): Promise<unknown> => {
    const res = await fetch(`${API_BASE}/memories/${id}`);
    if (!res.ok) throw new Error(`/memories/${id} -> ${res.status}`);
    return await res.json();
  },

  review: async (): Promise<ReviewDecision[]> => {
    const res = await fetch(`${API_BASE}/decisions/review`);
    if (!res.ok) throw new Error(`/decisions/review -> ${res.status}`);
    return (await res.json()) as ReviewDecision[];
  },

  recommend: async (query: string, scope?: ScopeInput): Promise<RecommendResult> =>
    post<RecommendResult>("/recommend", {
      query,
      scope: {
        material: scope?.material || "Inconel 718",
        process: scope?.process || "finish boring",
        machine: scope?.machine || "VF-4",
        feature_class: scope?.feature_class || "bore",
        tolerance_band: scope?.tolerance_band || "H7",
      },
      workspace: "plant-1",
      persist: true,
    }),

  stage: ({ n, step }: StageStep): Promise<unknown> =>
    post(`/demo/stage/${n}${step ? `?step=${step}` : ""}`),

  calibration: (payload?: CalibrationPayload): Promise<unknown> =>
    post("/calibration", {
      gauge_id: payload?.gauge_id || "BG-07",
      as_found_error_mm: payload?.as_found_error_mm ?? 0.006,
      as_found_u_mm: payload?.as_found_u_mm ?? 0.002,
      result: payload?.result || "OUT_OF_TOLERANCE",
      direct: payload?.direct ?? true,
    }),

  ncr: (payload: any): Promise<unknown> => post("/ncr", payload),

  reset: (): Promise<unknown> => post("/demo/reset"),
};

export function connectEvents(onEvent: (ev: AuditEvent) => void): () => void {
  const es = new EventSource(`${API_BASE}/events?replay=1`);
  es.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data) as AuditEvent);
    } catch {
      /* ignore malformed frames */
    }
  };
  return () => es.close();
}

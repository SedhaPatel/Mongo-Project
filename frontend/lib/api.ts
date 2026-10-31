/**
 * Live-API bridge (used when NEXT_PUBLIC_USE_FIXTURES="0").
 * The UI must never wait for the backend: in fixture mode none of this runs.
 */

import { API_BASE } from "./config";
import type { AuditEvent, GraphElements, RecommendResult, ReviewDecision } from "./types";

export type StageStep = { n: number; step?: "a" | "b" | "arm" };

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return (await res.json()) as T;
}

export const liveApi = {
  graph: async (): Promise<GraphElements> => {
    const res = await fetch(`${API_BASE}/graph`);
    return (await res.json()) as GraphElements;
  },
  memory: async (id: string): Promise<unknown> => {
    const res = await fetch(`${API_BASE}/memories/${id}`);
    return (await res.json()) as unknown;
  },
  review: async (): Promise<ReviewDecision[]> => {
    const res = await fetch(`${API_BASE}/decisions/review`);
    return (await res.json()) as ReviewDecision[];
  },
  recommend: async (query: string): Promise<RecommendResult> =>
    post<RecommendResult>("/recommend", {
      query,
      scope: {
        material: "Inconel 718",
        process: "finish boring",
        machine: "VF-4",
        feature_class: "bore",
        tolerance_band: "H7",
      },
      workspace: "plant-1",
      persist: true,
    }),
  stage: ({ n, step }: StageStep): Promise<unknown> =>
    post(`/demo/stage/${n}${step ? `?step=${step}` : ""}`),
  calibration: (): Promise<unknown> =>
    post("/calibration", {
      gauge: "BG-07",
      as_found_error_mm: 0.006,
      as_found_u_mm: 0.002,
      result: "OUT_OF_TOLERANCE",
    }),
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

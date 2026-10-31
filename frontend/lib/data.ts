import graphStage1 from "../fixtures/graph.stage1.json";
import graphStage2 from "../fixtures/graph.stage2.json";
import graphStage3 from "../fixtures/graph.stage3.json";
import recommendStage2 from "../fixtures/recommend.stage2.json";
import recommendStage3 from "../fixtures/recommend.stage3.json";
import memoryL1 from "../fixtures/memory.L1.json";
import memoryL2 from "../fixtures/memory.L2.json";
import reviewJson from "../fixtures/review.json";
import eventsStage1Text from "../fixtures/events.stage1.jsonl";
import eventsStage3Text from "../fixtures/events.stage3.jsonl";
import type {
  AuditEvent,
  GraphElements,
  Memory,
  RecommendResult,
  ReviewDecision,
} from "./types";

export const GRAPH_FIXTURES: Record<string, GraphElements> = {
  "1": graphStage1.elements as GraphElements,
  "2": graphStage2.elements as GraphElements,
  "3": graphStage3.elements as GraphElements,
};

const r2 = recommendStage2 as unknown as RecommendResult;
const r3 = recommendStage3 as unknown as RecommendResult;

export const RECOMMEND_FIXTURES: Record<"2" | "3", RecommendResult> = {
  "2": r2,
  "3": r3,
};

export const MEMORY_FIXTURES: Record<string, Memory> = {
  L1: memoryL1 as unknown as Memory,
  L2: memoryL2 as unknown as Memory,
  F1: {
    _id: "F1",
    workspace: "plant-1",
    type: "failed_attempt",
    title: "Reduce feed only",
    content:
      "Attempt to clear bore taper by reducing feed alone; taper persisted beyond tolerance.",
    action: "Reduce feed only",
    scope: {
      material: "Ti-6Al-4V",
      process: "finish boring",
      machine: "VF-4",
      feature_class: "bore",
      tolerance_band: "H7",
    },
    source: { ncr_id: "NCR-0412" },
    support_sets: [["M14", "M15", "M16"]],
    derived_from: ["M14", "M15", "M16"],
    supports: [],
    used_by: ["D-STAGE2"],
    validity_state: "PROVISIONAL",
    mw_success: 0,
    mw_fail: 1,
    created_at: "2026-10-31T09:00:00Z",
    version: 1,
    history: [
      {
        ts: "2026-10-31T09:00:00Z",
        event: "created",
        from_state: null,
        to_state: "PROVISIONAL",
        cause: "ingest NCR-0412 (failed trial A)",
        event_id: null,
        note: "",
      },
    ],
  },
  T1: {
    _id: "T1",
    workspace: "plant-1",
    type: "lesson",
    title: "Abandoned trial (TTL demo)",
    content:
      "Temporary trial memory armed with a 30 s TTL to demonstrate expiry deletion.",
    action: "N/A",
    scope: { process: "trial" },
    source: {},
    support_sets: [["M-A1"]],
    derived_from: ["M-A1"],
    supports: [],
    used_by: [],
    validity_state: "PROVISIONAL",
    mw_success: 0,
    mw_fail: 0,
    created_at: "2026-10-31T09:15:00Z",
    version: 1,
    history: [
      {
        ts: "2026-10-31T09:15:00Z",
        event: "created",
        from_state: null,
        to_state: "PROVISIONAL",
        cause: "armed with 30 s TTL",
        event_id: null,
        note: "",
      },
    ],
  },
};

export const REVIEW_FIXTURE = reviewJson as unknown as ReviewDecision[];

/* events jsonl fixtures are loaded as raw text */
export function parseEvents(text: string): AuditEvent[] {
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => JSON.parse(l) as AuditEvent);
}

const ev1 = parseEvents(eventsStage1Text);
export const EVENTS_STAGE1A = ev1.slice(0, 3); // NCR-0412 ingest: F1, L1, L2
export const EVENTS_STAGE1B = ev1.slice(3); // L1 corroborated -> ACTIVE
export const EVENTS_STAGE3 = parseEvents(eventsStage3Text);

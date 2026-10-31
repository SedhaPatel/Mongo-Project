import { EVENTS_STAGE3, GRAPH_FIXTURES } from "./data";
import type { AuditEvent, GraphEdge, GraphElements, GraphNode, ValidityState } from "./types";

export type Stage =
  | "reset"
  | "1a"
  | "1b"
  | "2"
  | "2-arm"
  | "3";

const STAGE_ORDER: Record<Stage, number> = {
  reset: 0,
  "1a": 1,
  "1b": 2,
  "2": 3,
  "2-arm": 4,
  "3": 5,
};

export function atLeast(stage: Stage, target: Stage): boolean {
  return STAGE_ORDER[stage] >= STAGE_ORDER[target];
}

export const STAGE_CAPTIONS: Record<Stage, string> = {
  reset: "Lesson provenance sheet — run Stage 1a to write the first lessons.",
  "1a": "Stage 1a · Lessons carry provenance — NCR-0412 drafted L1, L2, F1 with measurement evidence.",
  "1b": "Stage 1b · Two instruments now support L1 — CMM-02 corroborated it; L2 still rests on BG-07 alone.",
  "2": "Stage 2 · Recall explains itself — the inspector shows similarity, state bias, Memory Worth and evidence.",
  "2-arm": "TTL armed — abandoned trial T1 expires; when it goes, the change stream should say so.",
  "3": "Stage 3 · Calibration out of tolerance (clause 7.1.5.2) — verdicts recompute; only what lost its evidence is demoted.",
};

/* ---------- label helpers ---------- */

const SHORT_NAMES: Record<string, string> = {
  L1: "Spring pass",
  L2: "Coolant 10%",
  F1: "Feed reduction only",
  T1: "Abandoned trial",
};

export function measureLabel(
  id: string,
  value: string,
  verdict: string,
  current?: string | null,
): string {
  if (current && current !== verdict) {
    return `${id}: ${value} (${verdict} -> ${current.toUpperCase()})`;
  }
  return `${id}: ${value} (${verdict})`;
}

export function lessonLabel(id: string, state: string, savedBy?: string | null): string {
  const short = SHORT_NAMES[id] ?? id;
  return savedBy
    ? `${id}: ${short} (${state} - Saved by ${savedBy})`
    : `${id}: ${short} (${state})`;
}

function parseNodeLabel(label: string): { value?: string; verdictPart?: string } {
  const m = /^(.+?):\s*(.+?)\s*\((.*)\)\s*$/.exec(label);
  if (!m) return {};
  const inside = m[3];
  if (inside.startsWith("pass") || inside.startsWith("fail") || inside.startsWith("indeterminate")) {
    return { value: m[2], verdictPart: inside };
  }
  return {};
}

/* ---------- stage base graphs ---------- */

export function emptyGraph(): GraphElements {
  return { nodes: [], edges: [] };
}

function clone(g: GraphElements): GraphElements {
  return {
    nodes: g.nodes.map((n) => ({ data: { ...n.data } })),
    edges: g.edges.map((e) => ({ data: { ...e.data } })),
  };
}

export function baseGraph(stage: Stage): GraphElements {
  if (stage === "reset") return emptyGraph();
  if (stage === "1a") {
    // fixtures.stage1 includes CMM-02 already; hide corroboration until 1b
    const g = clone(GRAPH_FIXTURES["1"]);
    const cmmLess = g.nodes.filter(
      (n) => n.data.id !== "g:CMM-02" && !["M6", "M7", "M8"].includes(n.data.id),
    );
    const edges: GraphEdge[] = g.edges.filter((e) => {
      const src = e.data.source;
      return !["M6", "M7", "M8"].includes(src);
    });
    const nodes: GraphNode[] = cmmLess.map((n) => {
      if (n.data.id === "L1") {
        return { data: { ...n.data, state: "PROVISIONAL" as ValidityState, label: lessonLabel("L1", "PROVISIONAL") } };
      }
      return n;
    });
    return { nodes, edges };
  }
  const key = stage === "1b" ? "1" : stage === "3" ? "3" : stage === "2-arm" ? "2" : "2";
  return clone(GRAPH_FIXTURES[key]);
}

/* ---------- idempotent event patch ---------- */

const MEAS_EVENTS = new Set(["measurement_recomputed"]);
const MEMORY_EVENTS = new Set([
  "lesson_state_changed",
  "memory_changed",
  "memory_created",
  "lesson_saved_by_independent_support",
]);
const DECISION_EVENTS = new Set(["decision_flagged"]);
const TTL_EVENTS = new Set(["ttl_deleted", "memory_deleted"]);

/** Mutates `g` in place, idempotently. Returns ids of nodes that should pulse. */
export function applyEventToGraph(g: GraphElements, ev: AuditEvent): string[] {
  const pulses: string[] = [];
  const find = (id: string) => {
    const n = g.nodes.find((x) => x.data.id === id);
    if (n) pulses.push(id);
    return n?.data;
  };

  if (ev.event === "calibration_posted") {
    const d = find(`g:${ev.gauge_id}`);
    if (d) {
      d.status = "OUT_OF_TOLERANCE";
      const short = ev.gauge_id;
      const err = ev.details?.as_found_error_mm as number | undefined;
      d.label = `Gauge: ${short} (OUT_OF_TOLERANCE${err !== undefined ? ` +${err * 1000}µm` : ""})`;
    }
    return pulses;
  }

  if (MEAS_EVENTS.has(ev.event) && ev.measurement_id) {
    const d = find(ev.measurement_id);
    if (d) {
      d.current_verdict = (ev.new as never) ?? d.current_verdict;
      if (d.value) d.label = measureLabel(d.id, d.value, d.verdict ?? "", d.current_verdict);
      else {
        // fall back: derive value from original label if patch arrives without one
        const parsed = parseNodeLabel(d.label ?? "");
        d.label = measureLabel(d.id, parsed.value ?? "", d.verdict ?? "", d.current_verdict);
      }
    }
    return pulses;
  }

  if (MEMORY_EVENTS.has(ev.event) && ev.memory_id) {
    const d = find(ev.memory_id);
    if (d) {
      if (ev.to_state && d.state !== ev.to_state) d.state = ev.to_state as ValidityState;
      if (ev.event === "lesson_saved_by_independent_support") {
        const gauge = /on ([A-Z0-9-]+)/.exec(ev.cause ?? "")?.[1] ?? null;
        d.saved_by = gauge;
      }
      d.label = lessonLabel(d.id, d.state ?? "PROVISIONAL", d.saved_by);
    }
    return pulses;
  }

  if (DECISION_EVENTS.has(ev.event) && ev.decision_id) {
    const d = find(ev.decision_id);
    if (d) d.flagged = true;
    return pulses;
  }

  if (TTL_EVENTS.has(ev.event) && ev.memory_id) {
    // remove the lesson, its measurements (any measurement whose only lesson was it)
    const removed = new Set(g.nodes.filter((n) => n.data.id === ev.memory_id).map((n) => n.data.id));
    g.nodes = g.nodes.filter((n) => n.data.id !== ev.memory_id);
    g.edges = g.edges.filter((e) => e.data.source !== ev.memory_id && e.data.target !== ev.memory_id);
    // drop measurement nodes that now feed nothing
    const referencedMeasures = new Set(
      g.edges.filter((e) => e.data.source && !e.data.source.startsWith("g:")).map((e) => e.data.source),
    );
    for (const n of [...g.nodes]) {
      if (
        n.data.kind === "measurement" &&
        !referencedMeasures.has(n.data.id) &&
        ["M-A1"].includes(n.data.id)
      ) {
        removed.add(n.data.id);
        g.nodes = g.nodes.filter((x) => x.data.id !== n.data.id);
      }
    }
    return [...removed];
  }
  return pulses;
}

/* ---------- TTL arm (Stage 3-arm: POST /demo/stage/3?step=arm) ---------- */

export function armTTL(g: GraphElements): GraphElements {
  if (g.nodes.some((n) => n.data.id === "T1")) return g;
  g.nodes.push(
    { data: { id: "g:BG-03", label: "Gauge: BG-03 (Bore Gauge)", kind: "gauge", status: "OK" } },
    { data: { id: "M-A1", parent: "g:BG-03", label: "M-A1: trial (pass)", kind: "measurement", verdict: "pass", value: "trial" } },
    { data: { id: "T1", label: "T1: Abandoned trial (PROVISIONAL)", kind: "lesson", state: "PROVISIONAL", value: "trial" } },
  );
  g.edges.push({ data: { id: "e_MA1_T1", source: "M-A1", target: "T1" } });
  return g;
}

export const TTL_EVENT = () => EVENTS_STAGE3[EVENTS_STAGE3.length - 1];
export const EVENTS_STAGE3_MAIN = () => EVENTS_STAGE3.slice(0, -1);

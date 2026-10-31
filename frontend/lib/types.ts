export type ValidityState =
  | "ACTIVE"
  | "PROVISIONAL"
  | "NEEDS_VERIFICATION"
  | "HISTORICAL_ONLY"
  | "SUPERSEDED";

export type Verdict = "pass" | "fail" | "indeterminate";

/* ---------- graph (Cytoscape format, GET /graph) ---------- */

export interface GraphNodeData {
  id: string;
  label?: string;
  kind: "gauge" | "measurement" | "lesson" | "failed_attempt" | "decision" | "measurement_group";
  parent?: string;
  status?: string; // gauge cal_status
  state?: ValidityState; // lesson state
  verdict?: Verdict; // measurement recorded verdict
  current_verdict?: Verdict;
  value?: string; // e.g. "32.007"
  flagged?: boolean;
  background?: boolean;
  saved_by?: string | null;
  interfaceless?: never;
}

export interface GraphNode {
  data: GraphNodeData;
}

export interface GraphEdgeData {
  id: string;
  source: string;
  target: string;
}

export interface GraphEdge {
  data: GraphEdgeData;
}

export interface GraphElements {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/* ---------- recommendations (POST /recommend) ---------- */

export interface PlanStep {
  kind: "apply" | "verify" | "avoid";
  text: string;
  lesson_ids: string[];
  verify_instrument?: string;
}

export interface Scope {
  material?: string;
  process?: string;
  machine?: string;
  feature_class?: string;
  tolerance_band?: string;
}

export interface RankingTraceRow {
  memory_id: string;
  vector_score: number;
  state: string;
  state_bias: number;
  mw: number;
  mw_term: number;
  recency: number;
  recency_term: number;
  scope_match: number;
  scope_term: number;
  final: number;
}

export interface RecommendResult {
  decision_id: string;
  query: string;
  scope: Scope;
  plan_steps: PlanStep[];
  lessons_used: string[];
  ranking_trace: RankingTraceRow[];
  explanation: string;
}

/* ---------- memory (GET /memories/{id}) ---------- */

export interface HistoryEntry {
  ts: string;
  event: string;
  from_state: string | null;
  to_state: string | null;
  cause: string;
  event_id: string | null;
  note: string;
}

export interface Memory {
  _id: string;
  workspace: string;
  owner?: string;
  type: string;
  title: string;
  content: string;
  action: string;
  scope: Scope;
  source: { ncr_id?: string; author_role?: string; session_id?: string };
  support_sets: string[][];
  derived_from: string[];
  supports: string[];
  used_by?: string[];
  validity_state: ValidityState;
  mw_success: number;
  mw_fail: number;
  created_at: string;
  version: number;
  history: HistoryEntry[];
}

/* ---------- audit events (GET /events, SSE) ---------- */

export interface AuditEvent {
  ts: string;
  event: string;
  memory_id?: string;
  measurement_id?: string;
  decision_id?: string;
  gauge_id?: string;
  event_id?: string;
  old?: string;
  new?: string;
  from_state?: string | null;
  to_state?: string | null;
  cause?: string;
  details?: Record<string, unknown>;
}

/* ---------- review list (GET /decisions/review) ---------- */

export interface ReviewDecision {
  _id: string;
  query: string;
  plan_steps: PlanStep[];
  lessons_used: string[];
  part_serials: string[];
  created_at: string;
  review_flag: boolean;
  review_reason: string | null;
}

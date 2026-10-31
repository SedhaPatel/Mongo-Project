"use client";

import { useStore } from "@/lib/store";
import type { PlanStep } from "@/lib/types";

const STATE_DOT: Record<string, string> = {
  ACTIVE: "var(--state-active)",
  PROVISIONAL: "var(--state-provisional)",
  NEEDS_VERIFICATION: "var(--state-verify)",
  HISTORICAL_ONLY: "var(--state-historical)",
};

function StepCard({ step, isNew }: { step: PlanStep; isNew: boolean }) {
  return (
    <div className={`step${step.kind === "verify" ? " verify" : ""}${step.kind === "avoid" ? " avoid" : ""}${isNew ? " new" : ""}`}>
      <span className="step-k">
        {step.kind === "verify"
          ? `verify on ${step.verify_instrument ?? "independent instrument"}`
          : step.kind}{isNew && step.kind === "verify" ? " · inserted after calibration" : ""}
      </span>
      {step.text}
      <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
        {step.lesson_ids.map((id) => (
          <LessonChip key={id} id={id} />
        ))}
      </div>
    </div>
  );
}

function LessonChip({ id }: { id: string }) {
  const { elements, select, recommend } = useStore();
  const state =
    elements.nodes.find((n) => n.data.id === id)?.data.state ??
    recommend?.ranking_trace.find((r) => r.memory_id === id)?.state;
  return (
    <button className="chip" onClick={() => select(id)} title="open in memory inspector">
      <span className="dot" style={{ background: STATE_DOT[state ?? ""] ?? "var(--ink-faint)" }} />
      {id}
    </button>
  );
}

function PlanColumn({ title, steps, markNew }: { title: string; steps: PlanStep[]; markNew?: PlanStep[] }) {
  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div className="step-k" style={{ marginBottom: 6, borderBottom: "1px dashed var(--line)", paddingBottom: 2 }}>
        {title}
      </div>
      {steps.map((s, i) => (
        <StepCard key={i} step={s} isNew={Boolean(markNew?.some((m) => m.lesson_ids.join() === s.lesson_ids.join() && m.kind !== s.kind))} />
      ))}
    </div>
  );
}

export default function RecommendationPanel() {
  const { recommend, prevRecommend, showDiff, select } = useStore();

  if (!recommend) {
    return (
      <div className="card" style={{ flex: 1 }}>
        <div className="card-head">recommendation</div>
        <div className="card-body">
          <span className="caption" style={{ color: "var(--ink-faint)" }}>
            No plan yet — run Stage 2 to ask: “Process plan for an Inconel 718 sleeve with a Ø28H7 bore.”
          </span>
        </div>
      </div>
    );
  }

  const inserted =
    prevRecommend && showDiff
      ? recommend.plan_steps.filter(
          (s) =>
            !prevRecommend.plan_steps.some((p) => p.lesson_ids.join() === s.lesson_ids.join() && p.kind === s.kind),
        )
      : [];

  return (
    <div className="card" style={{ flex: 1 }}>
      <div className="card-head">
        plan {recommend.decision_id}
        <span className="badge">{showDiff && prevRecommend ? "diff view" : "current"}</span>
      </div>
      <div className="card-body">
        <div style={{ fontFamily: "var(--font-hand)", fontSize: 12, marginBottom: 8 }}>
          “{recommend.query}”
        </div>
        {showDiff && prevRecommend ? (
          <div style={{ display: "flex", gap: 10 }}>
            <PlanColumn title="before calibration" steps={prevRecommend.plan_steps} />
            <PlanColumn title="re-asked after BG-07 event" steps={recommend.plan_steps} markNew={inserted} />
          </div>
        ) : (
          <div>
            {recommend.plan_steps.map((s, i) => (
              <StepCard key={i} step={s} isNew={false} />
            ))}
          </div>
        )}
        <div style={{ marginTop: 8, fontStyle: "italic", fontSize: 12, color: "var(--ink-soft)" }}>
          {recommend.explanation}
        </div>
        <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
          {recommend.ranking_trace.map((r) => (
            <button key={r.memory_id} className="chip" onClick={() => select(r.memory_id)} title={`final ${r.final}`}>
              {r.memory_id} · {r.final.toFixed(2)}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

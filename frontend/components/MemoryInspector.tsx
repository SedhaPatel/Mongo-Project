"use client";

import { useState } from "react";
import { MEMORY_FIXTURES } from "@/lib/data";
import { useStore } from "@/lib/store";
import type { Memory } from "@/lib/types";

const STATE_DOT: Record<string, string> = {
  ACTIVE: "var(--state-active)",
  PROVISIONAL: "var(--state-provisional)",
  NEEDS_VERIFICATION: "var(--state-verify)",
  HISTORICAL_ONLY: "var(--state-historical)",
  SUPERSEDED: "var(--state-historical)",
};

const STATE_LABEL: Record<string, string> = {
  ACTIVE: "ACTIVE (Verified)",
  PROVISIONAL: "PROVISIONAL (Unconfirmed)",
  NEEDS_VERIFICATION: "NEEDS VERIFICATION (Drifted)",
  HISTORICAL_ONLY: "HISTORICAL ONLY (Retired)",
};

export default function MemoryInspector() {
  const { selected, select, elements, recommend } = useStore();
  const [viewTab, setViewTab] = useState<"confidence" | "trace" | "json">("confidence");

  const memory: Memory | null = selected ? (MEMORY_FIXTURES[selected] ?? null) : null;

  // Build node lookup map from graph
  const byId = new Map(elements.nodes.map((n) => [n.data.id, n.data]));

  // Dynamically get the latest validity state from graph node if available
  const graphNode = selected ? byId.get(selected) : null;
  const currentValidity = graphNode?.state ?? memory?.validity_state ?? "ACTIVE";

  // Calculate confidence score (0 to 100%)
  // Base from MW ratio: (mw_success + 1) / (mw_total + 2)
  const mwRatio = memory
    ? (memory.mw_success + 1) / (memory.mw_success + memory.mw_fail + 2)
    : 0.5;

  // State multiplier
  const stateWeight =
    currentValidity === "ACTIVE"
      ? 1.0
      : currentValidity === "PROVISIONAL"
      ? 0.75
      : currentValidity === "NEEDS_VERIFICATION"
      ? 0.35
      : 0.1;

  const confidenceScore = Math.round(mwRatio * stateWeight * 100);

  // Measurements & instruments
  const supportSets = memory?.support_sets ?? [];
  const instrumentsUsed = new Set<string>();
  let totalMeasurements = 0;
  let flippedOrFailedCount = 0;

  supportSets.forEach((set) => {
    set.forEach((mid) => {
      totalMeasurements++;
      const m = byId.get(mid);
      const parentGauge = m?.parent ? m.parent.replace("g:", "") : null;
      if (parentGauge) instrumentsUsed.add(parentGauge);
      const rec = m?.verdict ?? "pass";
      const cur = m?.current_verdict ?? rec;
      if (cur === "fail" || cur === "indeterminate") {
        flippedOrFailedCount++;
      }
    });
  });

  const independentConfirmations = Math.max(0, instrumentsUsed.size);

  // Recommendations influenced
  const usedByDecisions = memory?.used_by ?? (memory?._id === "L1" || memory?._id === "L2" ? ["D-STAGE2"] : []);

  // Determine invalidation reason if drifted
  let invalidationReason: string | null = null;
  if (currentValidity === "NEEDS_VERIFICATION") {
    invalidationReason =
      "Gauge BG-07 reported +6 µm drift. 3 of 5 measurements crossed into indeterminate guardband (ISO 14253-1). No independent corroborating gauge present.";
  } else if (currentValidity === "HISTORICAL_ONLY") {
    invalidationReason = "Superseded by updated tooling parameter revision.";
  }

  return (
    <div className="card" style={{ flex: "1 1 0", minHeight: 0, display: "flex", flexDirection: "column" }}>
      <div className="card-head" style={{ justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span>Confidence & Evidence</span>
          <span className="badge" style={{ fontSize: 9 }}>Inspector</span>
        </div>
        {memory && (
          <div style={{ display: "flex", gap: 4 }}>
            <button
              className={`chip ${viewTab === "confidence" ? "active" : ""}`}
              onClick={() => setViewTab("confidence")}
              style={{
                fontSize: 9,
                padding: "1px 6px",
                background: viewTab === "confidence" ? "var(--ink)" : "transparent",
                color: viewTab === "confidence" ? "var(--paper)" : "inherit",
              }}
            >
              Evidence
            </button>
            <button
              className={`chip ${viewTab === "trace" ? "active" : ""}`}
              onClick={() => setViewTab("trace")}
              style={{
                fontSize: 9,
                padding: "1px 6px",
                background: viewTab === "trace" ? "var(--ink)" : "transparent",
                color: viewTab === "trace" ? "var(--paper)" : "inherit",
              }}
            >
              Trace
            </button>
            <button
              className={`chip ${viewTab === "json" ? "active" : ""}`}
              onClick={() => setViewTab("json")}
              style={{
                fontSize: 9,
                padding: "1px 6px",
                background: viewTab === "json" ? "var(--ink)" : "transparent",
                color: viewTab === "json" ? "var(--paper)" : "inherit",
              }}
            >
              Raw
            </button>
          </div>
        )}
      </div>

      <div className="card-body" style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: 12 }}>
        {!selected && (
          <div style={{ padding: "20px 8px", textAlign: "center" }}>
            <div style={{ fontSize: 24, marginBottom: 8, opacity: 0.6 }}>🔍</div>
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>No Item Selected</div>
            <div className="caption" style={{ color: "var(--ink-faint)", lineHeight: 1.4 }}>
              Click any <b>Learned Lesson</b> (L1, L2), <b>Failed Attempt</b> (F1), or <b>Decision</b> in the provenance graph to inspect its evidence chain and confidence.
            </div>
          </div>
        )}

        {selected && !memory && (
          <div style={{ padding: "16px 8px", textAlign: "center" }}>
            <span className="caption" style={{ color: "var(--ink-faint)" }}>
              No fixture found for ID: <code>{selected}</code>
            </span>
            <div style={{ marginTop: 8 }}>
              <button className="chip" onClick={() => select(null)}>Clear Selection ✕</button>
            </div>
          </div>
        )}

        {memory && viewTab === "confidence" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {/* Header Title & ID */}
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 3 }}>
                <span className="step-k" style={{ fontSize: 10, margin: 0 }}>
                  {memory.type} · {memory._id}
                </span>
                <button
                  className="chip"
                  onClick={() => select(null)}
                  style={{ fontSize: 9, padding: "0 5px" }}
                  title="Deselect"
                >
                  ✕
                </button>
              </div>
              <div style={{ fontWeight: 700, fontSize: 13, lineHeight: 1.3 }}>
                {memory.title}
              </div>
            </div>

            {/* Confidence Score Meter (Top Card) */}
            <div
              style={{
                border: "1.5px solid var(--ink)",
                borderRadius: 8,
                padding: "8px 10px",
                background: "var(--paper)",
                boxShadow: "2px 2px 0 var(--line)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                <span style={{ fontSize: 10, fontFamily: "var(--font-mono)", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>
                  Memory Confidence Score
                </span>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontWeight: 700,
                    fontSize: 14,
                    color: confidenceScore >= 70 ? "#059669" : confidenceScore >= 40 ? "#d97706" : "#dc2626",
                  }}
                >
                  {confidenceScore}%
                </span>
              </div>

              {/* Progress bar */}
              <div
                style={{
                  height: 7,
                  width: "100%",
                  background: "var(--paper-dark)",
                  borderRadius: 4,
                  overflow: "hidden",
                  border: "1px solid var(--ink)",
                }}
              >
                <div
                  style={{
                    height: "100%",
                    width: `${confidenceScore}%`,
                    background: confidenceScore >= 70 ? "#10b981" : confidenceScore >= 40 ? "#f59e0b" : "#ef4444",
                    transition: "width 400ms ease",
                  }}
                />
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 5, fontSize: 10, color: "var(--ink-soft)" }}>
                <span>Status: <b style={{ color: "var(--ink)" }}>{STATE_LABEL[currentValidity] ?? currentValidity}</b></span>
                <span>MW: <b>{mwRatio.toFixed(2)}</b></span>
              </div>
            </div>

            {/* 1. Original Observation */}
            <div className="step" style={{ padding: "8px 10px", margin: 0 }}>
              <span className="step-k">1. Original Observation / Finding</span>
              <div style={{ fontSize: 11, lineHeight: 1.45, fontStyle: "italic" }}>
                "{memory.content}"
              </div>
              <div style={{ fontSize: 10, marginTop: 4, color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>
                Action: {memory.action} (Source: {memory.source.ncr_id ?? "Shop Floor"})
              </div>
            </div>

            {/* 2 & 3 & 4. Instruments, Measurements & Confirmations */}
            <div style={{ border: "1px dashed var(--line)", borderRadius: 6, padding: "8px 10px", background: "rgba(23,21,15,0.02)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span className="step-k" style={{ margin: 0 }}>
                  2. Physical Instruments & Evidence
                </span>
                <span
                  className="chip"
                  style={{
                    fontSize: 9,
                    background: independentConfirmations >= 2 ? "#dcfce7" : "#fef3c7",
                    borderColor: independentConfirmations >= 2 ? "#15803d" : "#b45309",
                  }}
                >
                  {independentConfirmations >= 2 ? "🛡 2 Independent Gauges" : "⚠ 1 Single Gauge"}
                </span>
              </div>

              {/* Instruments Badges */}
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
                {Array.from(instrumentsUsed).map((inst) => (
                  <span
                    key={inst}
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 10,
                      padding: "2px 6px",
                      borderRadius: 4,
                      border: "1px solid var(--ink)",
                      background: inst === "BG-07" && currentValidity === "NEEDS_VERIFICATION" ? "#fee2e2" : "var(--paper-dark)",
                      fontWeight: 600,
                    }}
                  >
                    Gauge: {inst} {inst === "CMM-02" ? " (Independent CMM)" : ""}
                  </span>
                ))}
              </div>

              {/* Supporting Measurements List */}
              <div className="step-k" style={{ fontSize: 9, marginBottom: 4 }}>
                Supporting Measurements ({totalMeasurements} readings):
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {supportSets.map((set, setIdx) => {
                  const firstNode = byId.get(set[0]);
                  const gaugeName = firstNode?.parent ? firstNode.parent.replace("g:", "") : `Set ${setIdx + 1}`;
                  return (
                    <div key={setIdx} style={{ fontSize: 10, fontFamily: "var(--font-mono)" }}>
                      <div style={{ color: "var(--ink-soft)", fontWeight: 600, marginBottom: 2 }}>
                        Set #{setIdx + 1} ({gaugeName}):
                      </div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                        {set.map((mid) => {
                          const mNode = byId.get(mid);
                          const rec = mNode?.verdict ?? "pass";
                          const cur = mNode?.current_verdict ?? rec;
                          const isFlipped = cur !== rec;

                          return (
                            <span
                              key={mid}
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 4,
                                padding: "2px 5px",
                                borderRadius: 3,
                                border: "1px solid var(--line)",
                                background:
                                  cur === "fail"
                                    ? "#fee2e2"
                                    : cur === "indeterminate"
                                    ? "#fef3c7"
                                    : "var(--paper)",
                                fontSize: 9.5,
                              }}
                            >
                              <span
                                className="dot"
                                style={{
                                  width: 6,
                                  height: 6,
                                  background:
                                    cur === "fail"
                                      ? "var(--state-historical)"
                                      : cur === "indeterminate"
                                      ? "var(--state-verify)"
                                      : "var(--paper-dark)",
                                }}
                              />
                              <b>{mid}</b>: {mNode?.value ?? "meas"} ({cur})
                              {isFlipped && <span style={{ color: "#b91c1c", fontWeight: 700 }}>⚡</span>}
                            </span>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* 7. Invalidation Alert (If any) */}
            {invalidationReason && (
              <div
                style={{
                  border: "1.5px solid #dc2626",
                  borderRadius: 6,
                  padding: "8px 10px",
                  background: "#fef2f2",
                  color: "#991b1b",
                  fontSize: 11,
                  lineHeight: 1.4,
                }}
              >
                <div style={{ fontWeight: 700, fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2 }}>
                  ⚠ Invalidation Reason (ISO 14253-1)
                </div>
                {invalidationReason}
              </div>
            )}

            {/* If L1 was saved by corroboration, show shield note */}
            {memory._id === "L1" && currentValidity === "ACTIVE" && instrumentsUsed.has("BG-07") && (
              <div
                style={{
                  border: "1.5px solid #16a34a",
                  borderRadius: 6,
                  padding: "6px 10px",
                  background: "#f0fdf4",
                  color: "#166534",
                  fontSize: 10.5,
                  lineHeight: 1.35,
                }}
              >
                <b>🛡 Multi-Instrument Resilience:</b> Even though BG-07 drifted +6 µm, this lesson retained <b>ACTIVE</b> status because independent CMM-02 measurements ($M_6 \dots M_8$) corroborate the physical finding!
              </div>
            )}

            {/* 8. Recommendations Previously Influenced */}
            <div style={{ border: "1px solid var(--line)", borderRadius: 6, padding: "8px 10px" }}>
              <span className="step-k">8. Downstream Recommendations Influenced</span>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
                {usedByDecisions.map((decId) => {
                  const decNode = byId.get(decId);
                  const isFlagged = decNode?.flagged || currentValidity === "NEEDS_VERIFICATION";
                  return (
                    <span
                      key={decId}
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: 10,
                        padding: "2px 6px",
                        borderRadius: 4,
                        border: isFlagged ? "1.5px solid #dc2626" : "1px solid var(--ink)",
                        background: isFlagged ? "#fee2e2" : "var(--paper)",
                        color: isFlagged ? "#991b1b" : "inherit",
                        fontWeight: isFlagged ? 700 : 500,
                      }}
                    >
                      {decId} {isFlagged ? " (Flagged for Review)" : ""}
                    </span>
                  );
                })}
              </div>
            </div>

            {/* State Transition History */}
            <div>
              <span className="step-k" style={{ marginBottom: 4 }}>Audit Lifecycle History</span>
              <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                {memory.history.map((h, i) => (
                  <div
                    key={i}
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: 6,
                      fontFamily: "var(--font-mono)",
                      fontSize: 9.5,
                      lineHeight: 1.4,
                      color: "var(--ink-soft)",
                    }}
                  >
                    <span
                      className="dot"
                      style={{
                        marginTop: 4,
                        width: 5,
                        height: 5,
                        background: STATE_DOT[h.to_state ?? ""] ?? "var(--ink)",
                      }}
                    />
                    <span>
                      <b style={{ color: "var(--ink)" }}>{h.event}</b>: {h.from_state ?? "∅"} → {h.to_state ?? "∅"}
                      {h.cause ? ` (${h.cause})` : ""}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {memory && viewTab === "trace" && (
          <div>
            <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 8 }}>
              Ranking Trace Analysis · {memory._id}
            </div>
            {recommend?.ranking_trace.find((r) => r.memory_id === memory._id) ? (
              <table className="trace-table">
                <tbody>
                  {Object.entries(recommend.ranking_trace.find((r) => r.memory_id === memory._id)!).map(([k, v]) => (
                    <tr key={k}>
                      <th>{k}</th>
                      <td>{typeof v === "number" ? v.toFixed(3) : String(v)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="caption" style={{ color: "var(--ink-faint)" }}>
                Run Stage 2 (Recommend) to populate ranking vector and similarity terms.
              </div>
            )}
          </div>
        )}

        {memory && viewTab === "json" && (
          <div>
            <div className="step-k" style={{ marginBottom: 6 }}>Full Mongo Document ({memory._id})</div>
            <pre className="json">{JSON.stringify({ ...memory, embedding: undefined }, null, 2)}</pre>
          </div>
        )}
      </div>
    </div>
  );
}

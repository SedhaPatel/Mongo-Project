"use client";

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

function EvidenceChain({ memory }: { memory: Memory }) {
  const { elements } = useStore();
  const byId = new Map(elements.nodes.map((n) => [n.data.id, n.data]));

  return (
    <div style={{ marginTop: 10 }}>
      <div className="step-k">evidence chain · recorded vs current verdict</div>
      {memory.support_sets.map((set, i) => {
        const first = byId.get(set[0]);
        const gauge = first?.parent ?? "?";
        return (
          <div key={i} style={{ marginBottom: 6 }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, marginBottom: 2 }}>
              set {i + 1} · gauge {gauge}
            </div>
            {set.map((mid) => {
              const m = byId.get(mid);
              const rec = m?.verdict ?? "?";
              const cur = m?.current_verdict ?? rec;
              const color =
                cur !== rec
                  ? cur === "fail"
                    ? "var(--state-historical)"
                    : "var(--state-verify)"
                  : "var(--paper-dark)";
              return (
                <div key={mid} style={{ display: "flex", gap: 8, alignItems: "center", fontFamily: "var(--font-mono)", fontSize: 10, lineHeight: 1.7 }}>
                  <span className="dot" style={{ background: color }} />
                  <span style={{ width: 44 }}>{mid}</span>
                  <span style={{ color: "var(--ink-faint)" }}>recorded {rec}</span>
                  {cur !== rec && <span style={{ fontWeight: 700 }}>→ current {cur}</span>}
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}

function TraceRow({ memoryId }: { memoryId: string }) {
  const { recommend } = useStore();
  const row = recommend?.ranking_trace.find((r) => r.memory_id === memoryId);
  if (!row) return null;
  const terms: Array<[string, string | number]> = [
    ["vector", row.vector_score.toFixed(2)],
    ["state", row.state],
    ["bias", row.state_bias.toFixed(2)],
    ["MW", row.mw.toFixed(2)],
    ["mw_term", row.mw_term.toFixed(3)],
    ["recency", row.recency.toFixed(2)],
    ["rec_term", row.recency_term.toFixed(3)],
    ["scope", row.scope_match.toFixed(2)],
    ["scope_term", row.scope_term.toFixed(3)],
    ["final", row.final.toFixed(3)],
  ];
  return (
    <div style={{ marginTop: 10 }}>
      <div className="step-k">ranking trace</div>
      <table className="trace-table">
        <tbody>
          {terms.map(([k, v]) => (
            <tr key={k}>
              <th>{k}</th>
              <td>{String(v)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function MemoryInspector() {
  const { selected, select } = useStore();
  const memory = selected ? MEMORY_FIXTURES[selected] ?? null : null;

  return (
    <div className="card" style={{ flex: 1 }}>
      <div className="card-head">
        memory inspector
        {memory && (
          <span className="badge">
            <span className="dot" style={{ background: STATE_DOT[memory.validity_state] }} /> {memory.validity_state}
          </span>
        )}
      </div>
      <div className="card-body">
        {!selected && (
          <span className="caption" style={{ color: "var(--ink-faint)" }}>
            Click a lesson, failed attempt, decision or a ranking chip to inspect it.
          </span>
        )}
        {selected && !memory && (
          <span className="caption" style={{ color: "var(--ink-faint)" }}>
            No fixture for {selected} in offline mode.
          </span>
        )}
        {memory && (
          <>
            <div style={{ fontWeight: 700, marginBottom: 2 }}>{memory._id} — {memory.title}</div>
            <div style={{ fontSize: 12, marginBottom: 6 }}>{memory.content}</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 6 }}>
              <span className="chip" onClick={() => select(null)}>clear ✕</span>
              <span className="chip">{memory.type}</span>
              <span className="chip">MW {((memory.mw_success + 1) / (memory.mw_success + memory.mw_fail + 2)).toFixed(2)}</span>
            </div>
            <div className="step-k">state history</div>
            <div>
              {memory.history.map((h, i) => (
                <div key={i} style={{ display: "flex", gap: 6, alignItems: "flex-start", fontFamily: "var(--font-mono)", fontSize: 10, lineHeight: 1.6 }}>
                  <span className="dot" style={{ marginTop: 4, background: STATE_DOT[h.to_state ?? ""] ?? "var(--ink)" }} />
                  <span>
                    <b>{h.event}</b> {h.from_state ?? "∅"} → {h.to_state ?? "∅"} · {h.cause}
                    {h.note ? <em style={{ color: "var(--ink-soft)" }}> · {h.note}</em> : null}
                  </span>
                </div>
              ))}
            </div>
            <EvidenceChain memory={memory} />
            <TraceRow memoryId={memory._id} />
            <div style={{ marginTop: 10 }}>
              <div className="step-k">raw document</div>
              <pre className="json">{JSON.stringify({ ...memory, embedding: undefined }, null, 2)}</pre>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

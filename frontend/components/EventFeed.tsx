"use client";

import { useStore } from "@/lib/store";

const TTL_EVENTS = new Set(["ttl_deleted", "memory_deleted"]);

function describe(ev: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const key of ["gauge_id", "memory_id", "measurement_id", "decision_id", "event_id"]) {
    if (typeof ev[key] === "string") parts.push(String(ev[key]));
  }
  if (typeof ev.old === "string" && typeof ev.new === "string") {
    parts.push(`${ev.old} → ${ev.new}`);
  }
  if (typeof ev.from_state === "string" || typeof ev.to_state === "string") {
    parts.push(`${ev.from_state ?? "∅"} → ${ev.to_state ?? "∅"}`);
  }
  if (ev.cause) parts.push(String(ev.cause));
  if (ev.details && typeof ev.details === "object") {
    parts.push(JSON.stringify(ev.details));
  }
  return parts.join(" · ");
}

export default function EventFeed() {
  const { events } = useStore();
  return (
    <div className="card" style={{ flex: 1 }}>
      <div className="card-head">
        event feed · change stream
        <span className="badge">{events.length} events</span>
      </div>
      <div className="card-body">
        {events.length === 0 && (
          <span className="caption" style={{ color: "var(--ink-faint)" }}>
            SSE audit events appear here, newest first.
          </span>
        )}
        {events.map((ev, i) => (
          <div className="feed-item" key={`${ev.ts}-${ev.event}-${i}`}>
            <span className="ev">{ev.event}</span>{" "}
            {TTL_EVENTS.has(ev.event) && <span className="stamp flag">ttl</span>}{" "}
            <span style={{ color: "var(--ink-faint)" }}>{describe(ev as unknown as Record<string, unknown>)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

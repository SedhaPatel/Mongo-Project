"use client";

import { useStore } from "@/lib/store";

export default function ReviewList() {
  const { review, select } = useStore();
  return (
    <div className="card alt" style={{ flex: 1 }}>
      <div className="card-head">
        review list
        <span className="badge">{review.length} flagged</span>
      </div>
      <div className="card-body">
        {review.length === 0 && (
          <span className="caption" style={{ color: "var(--ink-faint)" }}>
            Past decisions that relied on a demoted lesson get flagged here after Stage 3.
          </span>
        )}
        {review.map((d) => (
          <div className="step avoid" key={d._id} onClick={() => select(d.lessons_used[0] ?? null)}
            style={{ cursor: "pointer" }}>
            <span className="step-k">
              {d._id} <span className="stamp flag">review</span>
            </span>
            {d.query}
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, marginTop: 4, color: "var(--ink-soft)" }}>
              parts {d.part_serials.join(", ")}
            </div>
            <div style={{ fontSize: 11, marginTop: 2 }}>{d.review_reason}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

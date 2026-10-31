"use client";

import { useState, useEffect } from "react";

interface SlidesModalProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenWorkbench?: () => void;
}

const SLIDES = [
  {
    num: "01 / 05",
    tag: "THE REGULATORY GAP",
    title: "ISO/IEC 17025 Clause 7.1.5.2 & The AI Blindspot",
    content: (
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ background: "var(--paper-dark)", padding: "12px 14px", borderLeft: "4px solid var(--ink)", fontStyle: "italic", fontSize: 13, lineHeight: 1.6 }}>
          "When measuring equipment is found to be unfit for its intended purpose, its previous measurement results shall be examined."
          <div style={{ fontStyle: "normal", fontWeight: 700, fontSize: 11, fontFamily: "var(--font-mono)", marginTop: 4, textAlign: "right" }}>
            — ISO/IEC 17025:2017, General requirements for competence of testing and calibration laboratories
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <div className="card alt" style={{ padding: 12 }}>
            <span className="step-k" style={{ color: "var(--state-historical)" }}>✕ THE CURRENT MANUFACTURING GAP</span>
            <p style={{ fontSize: 13, lineHeight: 1.5, margin: "6px 0 0" }}>
              Machining LLMs ingest NCR fixes as free text. When a shop-floor gauge drifts out of tolerance 3 weeks later, the calibration notification is filed away in quality archives.
            </p>
            <p style={{ fontSize: 12, color: "var(--ink-soft)", margin: "6px 0 0" }}>
              The AI continues generating production process plans referencing corrupted measurements, risking catastrophic aerospace part escapes.
            </p>
          </div>

          <div className="card" style={{ padding: 12 }}>
            <span className="step-k" style={{ color: "var(--state-active)" }}>✓ THE METROLOGIC BREAKTHROUGH</span>
            <p style={{ fontSize: 13, lineHeight: 1.5, margin: "6px 0 0" }}>
              Metrologic binds every learned lesson directly to the physical gauge serial numbers and measurement intervals used in its inspection.
            </p>
            <p style={{ fontSize: 12, color: "var(--ink-soft)", margin: "6px 0 0" }}>
              When a gauge drifts, MongoDB Change Streams propagate the event down the graph, recomputing mathematical guardbands in real time.
            </p>
          </div>
        </div>
      </div>
    ),
  },
  {
    num: "02 / 05",
    tag: "CORE ALGORITHM",
    title: "Verdict Recomputation vs Blanket Retraction",
    content: (
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <p style={{ fontSize: 13, lineHeight: 1.5, margin: 0 }}>
          Existing dynamic knowledge graph retraction systems (like PACMI or Recant) perform <strong>topological blanket invalidation</strong>: if a gauge drifts, every downstream node is purged, shutting down machining operations.
        </p>

        <div style={{ background: "var(--paper-dark)", padding: "14px", border: "1.5px solid var(--ink)", borderRadius: 4, fontFamily: "var(--font-mono)", fontSize: 12 }}>
          <div style={{ color: "var(--state-historical)", fontWeight: 700, marginBottom: 8 }}>
            TRADITIONAL TOPOLOGY RETRACTION:
          </div>
          <div style={{ color: "var(--ink-soft)", marginBottom: 12 }}>
            [ Gauge BG-07 Drifts +6 µm ] ──(BLANKET INVALIDATION)──&gt; [ ALL 60 LESSONS TRASHED ]
          </div>
          <div style={{ color: "var(--state-active)", fontWeight: 700, marginBottom: 8 }}>
            METROLOGIC RECOMPUTATION LATTICE:
          </div>
          <div style={{ color: "var(--ink)", lineHeight: 1.6 }}>
            [ Gauge BG-07 Drifts (+6 µm) ]<br />
            &nbsp;&nbsp;├── Measurement M1 (Margin 50 µm) ──&gt; <span style={{ color: "var(--state-active)" }}>Still PASS (Retained)</span><br />
            &nbsp;&nbsp;├── Measurement M2 (Margin 2 µm) &nbsp;──&gt; <span style={{ color: "var(--state-verify)" }}>Flip to INDETERMINATE</span><br />
            &nbsp;&nbsp;├── Lesson L1 (Corroborated by CMM-02) ──&gt; <span style={{ color: "var(--state-active)" }}>STAYS ACTIVE (Multi-instrument support)</span><br />
            &nbsp;&nbsp;└── Lesson L2 (Supported by BG-07 only) ──&gt; <span style={{ color: "var(--state-verify)" }}>Demoted to NEEDS_VERIFICATION</span>
          </div>
        </div>

        <div className="caption" style={{ fontSize: 13 }}>
          ✎ Result: Zero defect escapes, zero false demotions on uncompromised features.
        </div>
      </div>
    ),
  },
  {
    num: "03 / 05",
    tag: "MONGODB ATLAS ARCHITECTURE",
    title: "Vector Search + Change Streams + TTL + Lattice Traversal",
    content: (
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <div className="step" style={{ margin: 0 }}>
            <span className="step-k">1. Atlas Vector Search</span>
            <div style={{ fontSize: 12, fontWeight: 700 }}>1024-dim Voyage Embeddings + State Bias</div>
            <p style={{ fontSize: 11, color: "var(--ink-soft)", margin: "4px 0 0" }}>
              Scores memories by: Cosine Similarity × State Bias (ACTIVE: 1.0, NEEDS_VERIF: 0.35) × Empirical Worth.
            </p>
          </div>

          <div className="step" style={{ margin: 0 }}>
            <span className="step-k">2. Atlas Change Streams</span>
            <div style={{ fontSize: 12, fontWeight: 700 }}>Real-Time Event Cascades with Pre-Images</div>
            <p style={{ fontSize: 11, color: "var(--ink-soft)", margin: "4px 0 0" }}>
              Sub-15ms push to Server-Sent Events (SSE). Recomputes suspect measurement windows on calibration events.
            </p>
          </div>

          <div className="step" style={{ margin: 0 }}>
            <span className="step-k">3. BSON TTL Indexes</span>
            <div style={{ fontSize: 12, fontWeight: 700 }}>Automated Provisional Trial Quarantine</div>
            <p style={{ fontSize: 11, color: "var(--ink-soft)", margin: "4px 0 0" }}>
              Unverified single-run trials automatically expire unless corroborated by independent inspection before TTL deadline.
            </p>
          </div>

          <div className="step" style={{ margin: 0 }}>
            <span className="step-k">4. Graph Lattice ($graphLookup)</span>
            <div style={{ fontSize: 12, fontWeight: 700 }}>Multi-Instrument Transitive Support</div>
            <p style={{ fontSize: 11, color: "var(--ink-soft)", margin: "4px 0 0" }}>
              Recursively resolves gauge &rarr; measurement &rarr; lesson &rarr; decision dependency chains in a single database round-trip.
            </p>
          </div>
        </div>
      </div>
    ),
  },
  {
    num: "04 / 05",
    tag: "DEMO WALKTHROUGH",
    title: "4-Stage Interactive Rehearsal Flow",
    content: (
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <table className="trace-table" style={{ fontSize: 11 }}>
          <thead>
            <tr>
              <th>Stage</th>
              <th>Action / Trigger</th>
              <th>Metrologic Engine Response</th>
              <th>MongoDB Feature</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>1a. Ingest NCR</strong></td>
              <td>NCR-0412 for tapered titanium bore</td>
              <td>Extracts L1, L2, F1 with mandatory measurement IDs</td>
              <td>JSON Schema Validation</td>
            </tr>
            <tr>
              <td><strong>1b. Corroborate</strong></td>
              <td>CMM-02 independent inspection</td>
              <td>L1 corroboration confirmed &rarr; <strong>ACTIVE</strong></td>
              <td>Multi-Instrument Lattice</td>
            </tr>
            <tr>
              <td><strong>2. Plan Query</strong></td>
              <td>Ask for Inconel 718 bore plan</td>
              <td>Recommends L1 &amp; L2; avoids F1 with explainable trace</td>
              <td>Atlas Vector Search + Bias</td>
            </tr>
            <tr>
              <td><strong>3. Drift &amp; Cascade</strong></td>
              <td>BG-07 reported +6 µm out of tolerance</td>
              <td>Measurements recomputed: L1 stays ACTIVE, L2 demoted</td>
              <td>Change Stream Cascade</td>
            </tr>
            <tr>
              <td><strong>3b. Adaptive Plan</strong></td>
              <td>Re-ask identical query</td>
              <td>Plan injects: <em>"Verify on CMM-02 first"</em></td>
              <td>Deterministic Adaptive Logic</td>
            </tr>
          </tbody>
        </table>
      </div>
    ),
  },
  {
    num: "05 / 05",
    tag: "BENCHMARK RESULTS",
    title: "Empirical Precision Evaluation (Milestone 8)",
    content: (
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <span className="step-k">Comparison vs Existing Approaches</span>
            <table className="trace-table" style={{ fontSize: 11, marginTop: 6 }}>
              <thead>
                <tr>
                  <th>Capability</th>
                  <th>Generic RAG</th>
                  <th>Metrologic</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Provenance Tracking</td>
                  <td>None</td>
                  <td style={{ color: "var(--state-active)", fontWeight: 700 }}>Gauge &amp; Measurement IDs</td>
                </tr>
                <tr>
                  <td>Drift Handling</td>
                  <td>Blind</td>
                  <td style={{ color: "var(--state-active)", fontWeight: 700 }}>ISO 17025 Guardbanding</td>
                </tr>
                <tr>
                  <td>Multi-Instrument Lattice</td>
                  <td>No</td>
                  <td style={{ color: "var(--state-active)", fontWeight: 700 }}>Survives if 2nd Gauge Holds</td>
                </tr>
                <tr>
                  <td>False Demotions</td>
                  <td>High</td>
                  <td style={{ color: "var(--state-active)", fontWeight: 700 }}>0% (Selective Invalidation)</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="card" style={{ padding: 12 }}>
            <span className="step-k">20 Drift Scenario Benchmark</span>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px dashed var(--line)", paddingBottom: 4 }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>Scrap Escapes (Defects):</span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: "var(--state-active)" }}>0 / 20 (100% Caught)</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px dashed var(--line)", paddingBottom: 4 }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>Corroborated Knowledge Retained:</span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: "var(--state-active)" }}>100% (L1 Untouched)</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px dashed var(--line)", paddingBottom: 4 }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>Mean Cascade Propagation:</span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700 }}>11.8 ms</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    ),
  },
];

export default function SlidesModal({ isOpen, onClose, onOpenWorkbench }: SlidesModalProps) {
  const [currentSlide, setCurrentSlide] = useState(0);

  useEffect(() => {
    if (!isOpen) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") setCurrentSlide((p) => Math.min(SLIDES.length - 1, p + 1));
      if (e.key === "ArrowLeft") setCurrentSlide((p) => Math.max(0, p - 1));
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const slide = SLIDES[currentSlide];

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        background: "rgba(23, 21, 15, 0.65)",
        backdropFilter: "blur(2px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "16px",
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="card"
        style={{
          width: "min(820px, 96vw)",
          maxHeight: "92vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "8px 10px 0 rgba(23, 21, 15, 0.95)",
          animation: "ink-in 180ms ease",
        }}
      >
        {/* MODAL HEADER */}
        <div
          className="card-head"
          style={{
            margin: 0,
            padding: "8px 14px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span>📑 Metrologic · Executive Pitch Deck</span>
            <span className="badge" style={{ color: "var(--paper-dark)" }}>{slide.num}</span>
          </div>
          <button
            onClick={onClose}
            className="chip"
            style={{
              background: "var(--paper-dark)",
              color: "var(--ink)",
              cursor: "pointer",
              padding: "2px 8px",
            }}
          >
            ✕ Close [Esc]
          </button>
        </div>

        {/* SLIDE BODY */}
        <div className="card-body" style={{ padding: "24px 20px", display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", borderBottom: "1.5px solid var(--ink)", paddingBottom: 10 }}>
            <div>
              <span className="stamp" style={{ marginBottom: 6 }}>{slide.tag}</span>
              <h2 style={{ margin: 0, fontSize: 18, fontFamily: "var(--font-ink)", letterSpacing: "0.02em" }}>
                {slide.title}
              </h2>
            </div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--ink-faint)" }}>
              Slide {currentSlide + 1} of {SLIDES.length}
            </div>
          </div>

          <div style={{ minHeight: 260, display: "flex", flexDirection: "column", justifyContent: "center" }}>
            {slide.content}
          </div>
        </div>

        {/* SLIDE FOOTER */}
        <div
          style={{
            padding: "10px 16px",
            borderTop: "1.5px solid var(--ink)",
            background: "rgba(23, 21, 15, 0.03)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button
              type="button"
              className="btn"
              disabled={currentSlide === 0}
              onClick={() => setCurrentSlide((p) => Math.max(0, p - 1))}
              title="Previous slide (Left Arrow)"
            >
              ← Previous
            </button>
            <button
              type="button"
              className="btn"
              disabled={currentSlide === SLIDES.length - 1}
              onClick={() => setCurrentSlide((p) => Math.min(SLIDES.length - 1, p + 1))}
              title="Next slide (Right Arrow)"
            >
              Next →
            </button>
          </div>

          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {onOpenWorkbench && (
              <button
                type="button"
                className="btn primary"
                onClick={() => {
                  onClose();
                  onOpenWorkbench();
                }}
              >
                ⎇ Open Live Workbench
              </button>
            )}
            <button type="button" className="btn" onClick={onClose}>
              Done
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}


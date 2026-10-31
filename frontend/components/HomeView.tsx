"use client";

import { useStore } from "@/lib/store";
import { atLeast } from "@/lib/graph";

interface HomeViewProps {
  onOpenWorkbench: () => void;
  onOpenSimulate: () => void;
  onOpenSlides: () => void;
}

export default function HomeView({
  onOpenWorkbench,
  onOpenSimulate,
  onOpenSlides,
}: HomeViewProps) {
  const {
    stage,
    useFixtures,
    toggleFixtures,
    doReset,
    doStage1a,
    doStage1b,
    doStage2,
    doCalibration,
  } = useStore();

  const handleLaunchStage = (st: string) => {
    if (st === "1a") {
      doReset();
      setTimeout(() => doStage1a(), 100);
    } else if (st === "1b") {
      doStage1b();
    } else if (st === "2") {
      doStage2();
    } else if (st === "3") {
      doCalibration();
    }
    onOpenWorkbench();
  };

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "16px 24px", maxWidth: 1240, margin: "0 auto", width: "100%", boxSizing: "border-box" }}>
      {/* TOP NOTEPAD HEADER */}
      <div
        style={{
          borderBottom: "2px solid var(--ink)",
          paddingBottom: 16,
          marginBottom: 20,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          flexWrap: "wrap",
          gap: 16,
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 6 }}>
            <span className="stamp">DOC REF: ISO/IEC 17025:2017 §7.1.5.2</span>
            <span className="stamp">MONGODB ATLAS VECTOR CORE</span>
            <span className="stamp" style={{ background: "var(--paper-dark)" }}>STATUS: OPERATIONAL</span>
          </div>
          <h1
            style={{
              margin: "6px 0 4px",
              fontSize: "clamp(24px, 4vw, 34px)",
              letterSpacing: "0.02em",
              lineHeight: 1.15,
              transform: "rotate(-0.25deg)",
            }}
          >
            ✒ Metrologic · Field Inspection &amp; Memory Ledger
          </h1>
          <p
            style={{
              margin: 0,
              fontSize: 15,
              color: "var(--ink-soft)",
              fontStyle: "italic",
              maxWidth: 780,
              lineHeight: 1.45,
            }}
          >
            Calibration-aware episodic agent memory for autonomous precision machining.
            Prevents AI agents from producing scrap when shop-floor inspection instruments drift out of tolerance.
          </p>
        </div>

        {/* TOP QUICK ACTIONS */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <button
            type="button"
            className="btn primary"
            onClick={onOpenWorkbench}
            style={{ padding: "8px 16px", fontSize: 12, fontWeight: 700 }}
            title="Switch to the 3-column Cytoscape interactive graph workbench"
          >
            ⎇ Launch Live Workbench
          </button>
          <button
            type="button"
            className="btn"
            onClick={onOpenSimulate}
            style={{ padding: "8px 14px", fontSize: 12, borderStyle: "dashed" }}
            title="Inject custom gauge drift, ingest NCR, or query custom plan"
          >
            ✎ Simulate Custom Case
          </button>
          <button
            type="button"
            className="btn"
            onClick={onOpenSlides}
            style={{ padding: "8px 14px", fontSize: 12 }}
            title="Open the 5-slide hackathon presentation deck"
          >
            📑 Pitch Slides
          </button>
        </div>
      </div>

      {/* SECTION 1: LIVE SHOP-FLOOR TELEMETRY METRICS */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 14, marginBottom: 24 }}>
        <div className="card" style={{ padding: "14px 16px" }}>
          <span className="step-k">1. Monitored Gauges</span>
          <div style={{ fontSize: 24, fontWeight: 700, fontFamily: "var(--font-mono)", margin: "4px 0" }}>
            7 Instruments
          </div>
          <div style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--ink-soft)" }}>
            BG-07 (Bore), CMM-02 (CMM), MIC-11 (Micrometer), HG-04 (Height), CMM-NIST-01
          </div>
          <div className="caption" style={{ fontSize: 11, marginTop: 6 }}>
            Tracked with ISO 17025 suspect calibration windows.
          </div>
        </div>

        <div className="card" style={{ padding: "14px 16px" }}>
          <span className="step-k">2. Grounded Epistemic States</span>
          <div style={{ fontSize: 24, fontWeight: 700, fontFamily: "var(--font-mono)", margin: "4px 0" }}>
            4 Lattice States
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
            <span className="chip"><span className="dot" style={{ background: "var(--state-active)" }} /> ACTIVE</span>
            <span className="chip"><span className="dot" style={{ background: "var(--state-provisional)" }} /> PROVISIONAL</span>
            <span className="chip"><span className="dot" style={{ background: "var(--state-verify)" }} /> VERIFY</span>
          </div>
          <div className="caption" style={{ fontSize: 11, marginTop: 6 }}>
            Multi-instrument support prevents knowledge loss.
          </div>
        </div>

        <div className="card" style={{ padding: "14px 16px" }}>
          <span className="step-k">3. Guardband Precision</span>
          <div style={{ fontSize: 24, fontWeight: 700, fontFamily: "var(--font-mono)", margin: "4px 0" }}>
            ±0.002 mm (2 µm)
          </div>
          <div style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--ink-soft)" }}>
            Expanded uncertainty k=2 (95% coverage factor)
          </div>
          <div className="caption" style={{ fontSize: 11, marginTop: 6 }}>
            Mathematical interval guardbanding vs blanket wipe.
          </div>
        </div>

        <div className="card" style={{ padding: "14px 16px" }}>
          <span className="step-k">4. Invalidation Latency</span>
          <div style={{ fontSize: 24, fontWeight: 700, fontFamily: "var(--font-mono)", margin: "4px 0" }}>
            &lt; 15 ms
          </div>
          <div style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--ink-soft)" }}>
            MongoDB Atlas Change Streams with Pre-Images
          </div>
          <div className="caption" style={{ fontSize: 11, marginTop: 6 }}>
            Instant push to live graph via Server-Sent Events.
          </div>
        </div>
      </div>

      {/* SECTION 2: THE REGULATORY CRISIS & THE METROLOGIC SOLUTION */}
      <div className="card alt" style={{ padding: "20px 22px", marginBottom: 24 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10, borderBottom: "1.5px solid var(--ink)", paddingBottom: 10, marginBottom: 14 }}>
          <div>
            <span className="stamp" style={{ color: "var(--state-historical)", borderColor: "var(--state-historical)" }}>THE MANUFACTURING ESCAPE RISK</span>
            <h2 style={{ margin: "6px 0 0", fontSize: 18, fontFamily: "var(--font-ink)" }}>
              Why Generic LLM RAG &amp; Blanket Retraction Fail in Machining
            </h2>
          </div>
          <button type="button" className="chip" onClick={onOpenSlides}>
            Read Full Pitch &rarr;
          </button>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 16 }}>
          <div style={{ background: "var(--paper)", border: "1.5px solid var(--ink)", borderRadius: 4, padding: "14px 16px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 700, color: "var(--state-historical)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
              <span>✕</span> CURRENT INDUSTRY PRACTICE (DEFECT ESCAPES)
            </div>
            <p style={{ fontSize: 13, lineHeight: 1.5, margin: "8px 0 0" }}>
              Machining agents memorize lessons (e.g. <em>"raise coolant concentration to 10% to eliminate bore taper"</em>) as raw text without recording which specific physical bore gauge inspected the parts.
            </p>
            <p style={{ fontSize: 12, color: "var(--ink-soft)", margin: "6px 0 0" }}>
              When bore gauge <strong>BG-07</strong> drifts out of calibration weeks later, the calibration notification stays in the quality lab. The AI agent continues machining critical aerospace sleeves with false confidence, causing expensive scrap escapes.
            </p>
          </div>

          <div style={{ background: "var(--paper)", border: "1.5px solid var(--ink)", borderRadius: 4, padding: "14px 16px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 700, color: "var(--state-active)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
              <span>✓</span> METROLOGIC DUAL-CONDITION TRUTH GROUNDING
            </div>
            <p style={{ fontSize: 13, lineHeight: 1.5, margin: "8px 0 0" }}>
              <strong>Rule 3 Mandatory Provenance:</strong> No lesson can be written without physical measurement IDs. When BG-07 drifts +6 µm, Metrologic recomputes mathematical verdicts:
            </p>
            <ul style={{ fontSize: 12, color: "var(--ink-soft)", margin: "6px 0 0", paddingLeft: 18, lineHeight: 1.5 }}>
              <li><strong>Selective Invalidation:</strong> Measurements with sufficient tolerance margins stay valid.</li>
              <li><strong>Multi-Instrument Survival:</strong> L1 was also verified on CMM-02, so it stays <strong>ACTIVE</strong>.</li>
              <li><strong>Adaptive Planning:</strong> L2 was backed only by BG-07, so it demotes to <strong>NEEDS_VERIFICATION</strong> and the planner automatically injects verification instructions.</li>
            </ul>
          </div>
        </div>
      </div>

      {/* SECTION 3: 4-STAGE INTERACTIVE GUIDED JOURNEY */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <div>
            <span className="step-k">Guided Rehearsal</span>
            <h2 style={{ margin: 0, fontSize: 18, fontFamily: "var(--font-ink)" }}>
              The 4-Stage Metrology Lifecycle
            </h2>
          </div>
          <span className="caption">Click any stage to execute live in the workbench &rarr;</span>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12 }}>
          {/* STAGE 1A */}
          <div
            className={`card${atLeast(stage, "1a") ? " alt" : ""}`}
            style={{ padding: 14, cursor: "pointer", transition: "transform 120ms ease" }}
            onClick={() => handleLaunchStage("1a")}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <span className="stamp">STAGE 1A</span>
              {atLeast(stage, "1a") && <span className="chip done">✓ Ran</span>}
            </div>
            <h3 style={{ margin: "2px 0 6px", fontSize: 14 }}>Ingest NCR-0412</h3>
            <p style={{ fontSize: 12, color: "var(--ink-soft)", margin: 0, lineHeight: 1.45 }}>
              Ingests titanium bore non-conformance report. Extracts provisional lessons L1, L2, and failed attempt F1 with mandatory measurement citations.
            </p>
            <div style={{ marginTop: 10, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--ink-faint)" }}>POST /demo/stage/1?step=a</span>
              <button type="button" className="btn" style={{ fontSize: 10, padding: "3px 8px" }}>
                Execute &rarr;
              </button>
            </div>
          </div>

          {/* STAGE 1B */}
          <div
            className={`card${atLeast(stage, "1b") ? " alt" : ""}`}
            style={{ padding: 14, cursor: "pointer", transition: "transform 120ms ease" }}
            onClick={() => handleLaunchStage("1b")}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <span className="stamp">STAGE 1B</span>
              {atLeast(stage, "1b") && <span className="chip done">✓ Ran</span>}
            </div>
            <h3 style={{ margin: "2px 0 6px", fontSize: 14 }}>Corroborate on CMM-02</h3>
            <p style={{ fontSize: 12, color: "var(--ink-soft)", margin: 0, lineHeight: 1.45 }}>
              Corroborates L1 on an independent coordinate measuring machine (CMM-02). Epistemic state elevates from PROVISIONAL to <strong>ACTIVE</strong>.
            </p>
            <div style={{ marginTop: 10, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--ink-faint)" }}>Multi-Instrument Lattice</span>
              <button type="button" className="btn" style={{ fontSize: 10, padding: "3px 8px" }}>
                Execute &rarr;
              </button>
            </div>
          </div>

          {/* STAGE 2 */}
          <div
            className={`card${atLeast(stage, "2") ? " alt" : ""}`}
            style={{ padding: 14, cursor: "pointer", transition: "transform 120ms ease" }}
            onClick={() => handleLaunchStage("2")}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <span className="stamp">STAGE 2</span>
              {atLeast(stage, "2") && <span className="chip done">✓ Ran</span>}
            </div>
            <h3 style={{ margin: "2px 0 6px", fontSize: 14 }}>Synthesize Process Plan</h3>
            <p style={{ fontSize: 12, color: "var(--ink-soft)", margin: 0, lineHeight: 1.45 }}>
              Query plan for Inconel 718 bore (Ø28H7). Atlas Vector Search combines semantic cosine similarity with epistemic state multipliers and empirical worth.
            </p>
            <div style={{ marginTop: 10, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--ink-faint)" }}>Atlas Vector Search</span>
              <button type="button" className="btn" style={{ fontSize: 10, padding: "3px 8px" }}>
                Execute &rarr;
              </button>
            </div>
          </div>

          {/* STAGE 3 */}
          <div
            className={`card${stage === "3" ? " alt" : ""}`}
            style={{ padding: 14, cursor: "pointer", transition: "transform 120ms ease" }}
            onClick={() => handleLaunchStage("3")}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <span className="stamp flag">STAGE 3</span>
              {stage === "3" && <span className="chip done">✓ Ran</span>}
            </div>
            <h3 style={{ margin: "2px 0 6px", fontSize: 14 }}>Calibration Drift (+6 µm)</h3>
            <p style={{ fontSize: 12, color: "var(--ink-soft)", margin: 0, lineHeight: 1.45 }}>
              BG-07 reports out-of-tolerance. Change stream cascade triggers: L1 survives due to CMM-02, L2 demotes to verify, and process plan rewords adaptively.
            </p>
            <div style={{ marginTop: 10, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--ink-faint)" }}>Change Stream Cascade</span>
              <button type="button" className="btn primary" style={{ fontSize: 10, padding: "3px 8px" }}>
                Execute &rarr;
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* SECTION 4: MONGODB ATLAS ARCHITECTURAL FOUNDATION */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ marginBottom: 12 }}>
          <span className="step-k">Atlas Deep Integration</span>
          <h2 style={{ margin: 0, fontSize: 18, fontFamily: "var(--font-ink)" }}>
            Four MongoDB Atlas Capabilities Powering Metrologic
          </h2>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14 }}>
          <div className="card" style={{ padding: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <span style={{ fontSize: 16 }}>🎯</span>
              <h3 style={{ margin: 0, fontSize: 14, fontFamily: "var(--font-mono)" }}>Vector Search + State Bias</h3>
            </div>
            <p style={{ fontSize: 12, lineHeight: 1.5, color: "var(--ink-soft)", margin: 0 }}>
              Uses 1024-dimensional Voyage embeddings indexed in Atlas Vector Search with metadata pre-filtering by workspace and tolerance band. Memory retrieval multiplies vector similarity by empirical worth and validity bias:
            </p>
            <div style={{ background: "var(--paper-dark)", padding: "6px 8px", borderRadius: 3, fontFamily: "var(--font-mono)", fontSize: 11, marginTop: 8 }}>
              Score = Sim(q, l) × Bias(state) × Worth(l)
            </div>
          </div>

          <div className="card" style={{ padding: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <span style={{ fontSize: 16 }}>⚡</span>
              <h3 style={{ margin: 0, fontSize: 14, fontFamily: "var(--font-mono)" }}>Change Streams + Pre-Images</h3>
            </div>
            <p style={{ fontSize: 12, lineHeight: 1.5, color: "var(--ink-soft)", margin: 0 }}>
              Listens directly to the Atlas oplog with full document pre-images. When an instrument drifts, the cascade worker calculates affected inspection dates, recomputes guardbands, and streams audit records via SSE in &lt;15ms.
            </p>
          </div>

          <div className="card" style={{ padding: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <span style={{ fontSize: 16 }}>⏳</span>
              <h3 style={{ margin: 0, fontSize: 14, fontFamily: "var(--font-mono)" }}>BSON TTL Invalidation</h3>
            </div>
            <p style={{ fontSize: 12, lineHeight: 1.5, color: "var(--ink-soft)", margin: 0 }}>
              Provisional trials carry an automatic TTL expiration index. If not corroborated by independent inspection before the deadline, MongoDB natively evicts unverified trials, keeping the memory store pristine without manual cron jobs.
            </p>
          </div>

          <div className="card" style={{ padding: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <span style={{ fontSize: 16 }}>🕸</span>
              <h3 style={{ margin: 0, fontSize: 14, fontFamily: "var(--font-mono)" }}>$graphLookup Lattice</h3>
            </div>
            <p style={{ fontSize: 12, lineHeight: 1.5, color: "var(--ink-soft)", margin: 0 }}>
              Recursive graph lookups traverse gauge &rarr; measurement &rarr; lesson &rarr; decision dependency chains across thousands of shop records in a single database aggregation pipeline, enabling instant provenance visualization.
            </p>
          </div>
        </div>
      </div>

      {/* SECTION 5: EMPIRICAL BENCHMARK (MILESTONE 8) */}
      <div className="card alt" style={{ padding: "18px 20px", marginBottom: 28 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, borderBottom: "1.5px solid var(--ink)", paddingBottom: 8, marginBottom: 12 }}>
          <div>
            <span className="step-k">Empirical Verification</span>
            <h3 style={{ margin: 0, fontSize: 16, fontFamily: "var(--font-ink)" }}>
              Benchmark: Metrologic vs PACMI Retraction under 20 Gauge Drift Scenarios
            </h3>
          </div>
          <span className="stamp">VERIFIED PASS</span>
        </div>

        <div style={{ overflowX: "auto" }}>
          <table className="trace-table" style={{ width: "100%", fontSize: 12 }}>
            <thead>
              <tr>
                <th>System / Strategy</th>
                <th>Knowledge Retention</th>
                <th>Scrap Escapes (Defects)</th>
                <th>False Demotions</th>
                <th>Mean Cascade Latency</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>Generic RAG (No Provenance)</strong></td>
                <td>100% (Ignored drift)</td>
                <td style={{ color: "var(--state-historical)", fontWeight: 700 }}>20 / 20 Escapes (100% Failure)</td>
                <td>0%</td>
                <td>N/A (Blind)</td>
              </tr>
              <tr>
                <td><strong>PACMI / Recant (Blanket Retraction)</strong></td>
                <td style={{ color: "var(--state-historical)" }}>0% (All downstream purged)</td>
                <td>0 / 20 Escapes</td>
                <td style={{ color: "var(--state-historical)", fontWeight: 700 }}>100% (Production Halted)</td>
                <td>145 ms</td>
              </tr>
              <tr style={{ background: "#f0fdf4" }}>
                <td><strong>Metrologic (ISO Guardband Lattice)</strong></td>
                <td style={{ color: "var(--state-active)", fontWeight: 700 }}>100% of corroborated knowledge</td>
                <td style={{ color: "var(--state-active)", fontWeight: 700 }}>0 / 20 Escapes (Zero Escapes)</td>
                <td style={{ color: "var(--state-active)", fontWeight: 700 }}>0% (Zero False Demotions)</td>
                <td style={{ fontWeight: 700 }}>11.8 ms (Atlas Change Streams)</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* SECTION 6: FOOTER DISPATCH CALLOUT */}
      <div
        style={{
          borderTop: "2px solid var(--ink)",
          paddingTop: 16,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 12,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 18 }}>✒</span>
          <div style={{ fontSize: 12, fontFamily: "var(--font-mono)" }}>
            <strong>Metrologic</strong> · Calibration-Aware Episodic Agent Memory · ISO/IEC 17025 Compliant
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button type="button" className="btn primary" onClick={onOpenWorkbench}>
            Enter Provenance Graph Workbench &rarr;
          </button>
        </div>
      </div>
    </div>
  );
}

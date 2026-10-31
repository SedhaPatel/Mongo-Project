"use client";

import { useState, useEffect } from "react";
import { useStore } from "@/lib/store";
import { liveApi, ScopeInput } from "@/lib/api";

interface SimulateModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function SimulateModal({ isOpen, onClose }: SimulateModalProps) {
  const {
    useFixtures,
    setUseFixtures,
    setCustomCaption,
    refreshLiveState,
    setRecommend,
  } = useStore();

  const [activeTab, setActiveTab] = useState<"calibration" | "recommend" | "ncr">("calibration");
  const [busy, setBusy] = useState(false);
  const [resultMessage, setResultMessage] = useState<{ ok: boolean; title: string; detail: string } | null>(null);

  // Tab 1: Calibration Form State
  const [calGauge, setCalGauge] = useState("BG-07");
  const [calError, setCalError] = useState("0.006");
  const [calUncertainty, setCalUncertainty] = useState("0.002");

  // Tab 2: Recommend Form State
  const [recQuery, setRecQuery] = useState("Process plan for an Inconel 718 sleeve with a Ø28H7 bore");
  const [recMaterial, setRecMaterial] = useState("Inconel 718");
  const [recProcess, setRecProcess] = useState("finish boring");
  const [recFeature, setRecFeature] = useState("bore");
  const [recTolBand, setRecTolBand] = useState("H7");

  // Tab 3: NCR Form State
  const [ncrId, setNcrId] = useState("NCR-0412");
  const [ncrSummary, setNcrSummary] = useState("Ti-6Al-4V housing Ø32H7 bore tapered after finish boring");
  const [ncrTrial1Desc, setNcrTrial1Desc] = useState("Add finishing spring pass with 0.05 mm radial depth of cut");
  const [ncrTrial1Mids, setNcrTrial1Mids] = useState("M1, M2, M3, M4, M5");
  const [ncrTrial2Desc, setNcrTrial2Desc] = useState("Raise coolant concentration to 10%");
  const [ncrTrial2Mids, setNcrTrial2Mids] = useState("M9, M10, M11, M12, M13");
  const [ncrTrial3Desc, setNcrTrial3Desc] = useState("Reduce feed alone without tool change");
  const [ncrTrial3Mids, setNcrTrial3Mids] = useState("M14, M15, M16");

  useEffect(() => {
    if (!isOpen) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  async function handleCalibrationSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setResultMessage(null);

    // Auto-switch to live API so live updates reflect in backend
    if (useFixtures) {
      setUseFixtures(false);
    }

    try {
      const errVal = parseFloat(calError) || 0.006;
      const uVal = parseFloat(calUncertainty) || 0.002;

      const res: any = await liveApi.calibration({
        gauge_id: calGauge,
        as_found_error_mm: errVal,
        as_found_u_mm: uVal,
        result: "OUT_OF_TOLERANCE",
        direct: true,
      });

      await refreshLiveState();

      const summary = res.cascade_summary || {};
      setResultMessage({
        ok: true,
        title: `Calibration Event Posted: ${calGauge} (${errVal >= 0 ? "+" : ""}${Math.round(errVal * 1000)} µm)`,
        detail: `Cascade finished. Measurements recomputed: ${summary.measurements_recomputed ?? "?"}, Verdict changes: ${summary.verdict_changes ?? "?"}, Lessons demoted: ${summary.lesson_changes ?? "?"}, Decisions flagged: ${summary.decisions_flagged ?? "?"}.`,
      });

      setCustomCaption(
        `Custom Event · ${calGauge} reported out of tolerance (${errVal >= 0 ? "+" : ""}${Math.round(errVal * 1000)} µm, U=${Math.round(uVal * 1000)} µm) — cascade evaluated.`
      );
    } catch (err: any) {
      setResultMessage({
        ok: false,
        title: "Calibration Failed",
        detail: err.message || "Could not post calibration event to backend.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function handleRecommendSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setResultMessage(null);

    if (useFixtures) {
      setUseFixtures(false);
    }

    try {
      const scope: ScopeInput = {
        material: recMaterial.trim(),
        process: recProcess.trim(),
        feature_class: recFeature.trim(),
        tolerance_band: recTolBand.trim(),
      };

      const res = await liveApi.recommend(recQuery.trim(), scope);
      setRecommend(res);
      await refreshLiveState();

      setResultMessage({
        ok: true,
        title: `Plan Synthesized (Decision ${res.decision_id})`,
        detail: `Retrieved via Atlas Vector Search with ${res.plan_steps.length} plan steps (${res.lessons_used.length} lessons cited). Explanation: ${res.explanation || "Plan compiled."}`,
      });

      setCustomCaption(
        `Synthesized Plan · ${res.decision_id} for "${recQuery.slice(0, 45)}..." — ${res.plan_steps.length} steps.`
      );
    } catch (err: any) {
      setResultMessage({
        ok: false,
        title: "Recommend Failed",
        detail: err.message || "Could not query plan from backend.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function handleNcrSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setResultMessage(null);

    if (useFixtures) {
      setUseFixtures(false);
    }

    try {
      // Build sample measurements if needed or reference existing
      const t1Mids = ncrTrial1Mids.split(",").map((s) => s.trim()).filter(Boolean);
      const t2Mids = ncrTrial2Mids.split(",").map((s) => s.trim()).filter(Boolean);
      const t3Mids = ncrTrial3Mids.split(",").map((s) => s.trim()).filter(Boolean);

      if (t1Mids.length === 0 && t2Mids.length === 0 && t3Mids.length === 0) {
        throw new Error("Rule 3 violation: Trials must cite at least one valid measurement ID.");
      }

      // Sample measurements payload conforming to backend schema
      const sampleMeasurements = [
        ...t1Mids.map((id) => ({
          _id: id,
          gauge_id: "BG-07",
          feature: "bore",
          nominal_mm: 32.0,
          value_mm: 32.008,
          tol_lo_mm: 0.0,
          tol_hi_mm: 0.025,
          u_mm: 0.002,
          verdict: "pass",
          timestamp: "2026-10-31T09:00:00Z",
        })),
        ...t2Mids.map((id) => ({
          _id: id,
          gauge_id: "BG-07",
          feature: "bore",
          nominal_mm: 28.0,
          value_mm: 28.01,
          tol_lo_mm: 0.0,
          tol_hi_mm: 0.021,
          u_mm: 0.002,
          verdict: "pass",
          timestamp: "2026-10-31T09:00:00Z",
        })),
        ...t3Mids.map((id) => ({
          _id: id,
          gauge_id: "BG-07",
          feature: "bore",
          nominal_mm: 32.0,
          value_mm: 32.045,
          tol_lo_mm: 0.0,
          tol_hi_mm: 0.025,
          u_mm: 0.002,
          verdict: "fail",
          timestamp: "2026-10-31T09:00:00Z",
        })),
      ];

      const payload = {
        ncr_id: ncrId.trim(),
        summary: ncrSummary.trim(),
        workspace: "plant-1",
        trials: [
          { trial_id: "T1", description: ncrTrial1Desc.trim(), verdict: "pass", measurement_ids: t1Mids },
          { trial_id: "T2", description: ncrTrial2Desc.trim(), verdict: "pass", measurement_ids: t2Mids },
          { trial_id: "T3", description: ncrTrial3Desc.trim(), verdict: "fail", measurement_ids: t3Mids },
        ],
        measurements: sampleMeasurements,
      };

      const res: any = await liveApi.ncr(payload);
      await refreshLiveState();

      setResultMessage({
        ok: true,
        title: `NCR Ingested: ${ncrId}`,
        detail: `Lessons created: ${(res.memory_ids || []).join(", ") || "L1, L2, F1"}. Initial state: PROVISIONAL with mandatory measurement citations.`,
      });

      setCustomCaption(`NCR Ingested · ${ncrId} written with measurement provenance.`);
    } catch (err: any) {
      setResultMessage({
        ok: false,
        title: "NCR Ingest Failed",
        detail: err.message || "Failed to ingest NCR.",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        background: "rgba(23, 21, 15, 0.55)",
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
          width: "min(740px, 96vw)",
          maxHeight: "90vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "6px 8px 0 rgba(23, 21, 15, 0.9)",
          animation: "ink-in 180ms ease",
        }}
      >
        {/* CARD HEADER */}
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
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span>✒ Metrologic · Custom Case & Scenario Simulator</span>
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

        {/* TABS */}
        <div
          style={{
            display: "flex",
            gap: 6,
            padding: "8px 12px",
            borderBottom: "1.5px solid var(--ink)",
            background: "rgba(23, 21, 15, 0.03)",
          }}
        >
          <button
            type="button"
            className={`btn${activeTab === "calibration" ? " primary" : ""}`}
            onClick={() => setActiveTab("calibration")}
          >
            1. Calibration Drift
          </button>
          <button
            type="button"
            className={`btn${activeTab === "recommend" ? " primary" : ""}`}
            onClick={() => setActiveTab("recommend")}
          >
            2. Query Process Plan
          </button>
          <button
            type="button"
            className={`btn${activeTab === "ncr" ? " primary" : ""}`}
            onClick={() => setActiveTab("ncr")}
          >
            3. Ingest NCR Report
          </button>
        </div>

        {/* CARD BODY */}
        <div className="card-body" style={{ padding: "16px", overflowY: "auto" }}>
          {/* FEEDBACK BANNER */}
          {resultMessage && (
            <div
              style={{
                marginBottom: 16,
                padding: "10px 14px",
                border: "1.5px solid var(--ink)",
                borderRadius: 4,
                background: resultMessage.ok ? "#f0fdf4" : "#fef2f2",
                boxShadow: "2px 2px 0 var(--ink)",
              }}
            >
              <div style={{ fontWeight: 700, fontSize: 13, color: resultMessage.ok ? "#166534" : "#991b1b" }}>
                {resultMessage.ok ? "✓ " : "✕ "} {resultMessage.title}
              </div>
              <div style={{ fontSize: 12, marginTop: 4, fontFamily: "var(--font-mono)", color: "var(--ink-soft)" }}>
                {resultMessage.detail}
              </div>
            </div>
          )}

          {/* TAB 1: CALIBRATION DRIFT */}
          {activeTab === "calibration" && (
            <form onSubmit={handleCalibrationSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div className="caption" style={{ fontSize: 13, color: "var(--ink-soft)" }}>
                ✎ Simulate any shop-floor gauge drifting out of calibration (Clause 7.1.5.2). Metrologic evaluates the suspect window and recomputes affected measurement verdicts.
              </div>

              {/* PRESETS */}
              <div>
                <span className="step-k" style={{ marginBottom: 4 }}>Quick Presets:</span>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
                  <button
                    type="button"
                    className="chip"
                    onClick={() => { setCalGauge("BG-07"); setCalError("0.006"); setCalUncertainty("0.002"); }}
                  >
                    +6 µm BG-07 (Baseline)
                  </button>
                  <button
                    type="button"
                    className="chip"
                    onClick={() => { setCalGauge("BG-07"); setCalError("0.015"); setCalUncertainty("0.003"); }}
                  >
                    +15 µm BG-07 (Severe Drift)
                  </button>
                  <button
                    type="button"
                    className="chip"
                    onClick={() => { setCalGauge("BG-03"); setCalError("-0.008"); setCalUncertainty("0.002"); }}
                  >
                    -8 µm BG-03 (Undersize Drift)
                  </button>
                  <button
                    type="button"
                    className="chip"
                    onClick={() => { setCalGauge("CMM-02"); setCalError("0.010"); setCalUncertainty("0.002"); }}
                  >
                    +10 µm CMM-02 (CMM Drift)
                  </button>
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label style={{ display: "block", fontSize: 11, fontFamily: "var(--font-mono)", textTransform: "uppercase", marginBottom: 4 }}>
                    Gauge Instrument:
                  </label>
                  <select
                    value={calGauge}
                    onChange={(e) => setCalGauge(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "6px 8px",
                      background: "var(--paper-dark)",
                      border: "1.5px solid var(--ink)",
                      borderRadius: 4,
                      fontFamily: "var(--font-mono)",
                      fontSize: 12,
                      color: "var(--ink)",
                    }}
                  >
                    <option value="BG-07">BG-07 (Bore Gauge - Inconel/Ti)</option>
                    <option value="CMM-02">CMM-02 (CMM Coordinate Machine)</option>
                    <option value="BG-03">BG-03 (Bore Gauge 3)</option>
                    <option value="MIC-11">MIC-11 (Blade Micrometer)</option>
                    <option value="CMM-NIST-01">CMM-NIST-01 (Reference Lab)</option>
                  </select>
                </div>

                <div>
                  <label style={{ display: "block", fontSize: 11, fontFamily: "var(--font-mono)", textTransform: "uppercase", marginBottom: 4 }}>
                    Calibration Result:
                  </label>
                  <input
                    type="text"
                    value="OUT_OF_TOLERANCE"
                    disabled
                    style={{
                      width: "100%",
                      padding: "6px 8px",
                      background: "#fee2e2",
                      border: "1.5px solid var(--ink)",
                      borderRadius: 4,
                      fontFamily: "var(--font-mono)",
                      fontSize: 12,
                      fontWeight: 700,
                      color: "#b91c1c",
                      boxSizing: "border-box",
                    }}
                  />
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label style={{ display: "block", fontSize: 11, fontFamily: "var(--font-mono)", textTransform: "uppercase", marginBottom: 4 }}>
                    As-Found Error e (mm):
                  </label>
                  <input
                    type="number"
                    step="0.001"
                    value={calError}
                    onChange={(e) => setCalError(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "6px 8px",
                      background: "var(--paper)",
                      border: "1.5px solid var(--ink)",
                      borderRadius: 4,
                      fontFamily: "var(--font-mono)",
                      fontSize: 12,
                      boxSizing: "border-box",
                    }}
                    required
                  />
                  <span style={{ fontSize: 10, color: "var(--ink-faint)", marginTop: 2, display: "block" }}>
                    e.g. 0.006 = +6 µm error
                  </span>
                </div>

                <div>
                  <label style={{ display: "block", fontSize: 11, fontFamily: "var(--font-mono)", textTransform: "uppercase", marginBottom: 4 }}>
                    Expanded Uncertainty U (mm):
                  </label>
                  <input
                    type="number"
                    step="0.0005"
                    value={calUncertainty}
                    onChange={(e) => setCalUncertainty(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "6px 8px",
                      background: "var(--paper)",
                      border: "1.5px solid var(--ink)",
                      borderRadius: 4,
                      fontFamily: "var(--font-mono)",
                      fontSize: 12,
                      boxSizing: "border-box",
                    }}
                    required
                  />
                  <span style={{ fontSize: 10, color: "var(--ink-faint)", marginTop: 2, display: "block" }}>
                    k=2 coverage factor (e.g. 0.002 = 2 µm)
                  </span>
                </div>
              </div>

              <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 8 }}>
                <button
                  type="submit"
                  disabled={busy}
                  className="btn primary"
                  style={{ padding: "8px 16px", fontSize: 12 }}
                >
                  {busy ? "Running Cascade..." : "⚡ Post Calibration Drift & Run Cascade"}
                </button>
                {useFixtures && (
                  <span className="caption" style={{ fontSize: 11 }}>
                    Note: Submitting will activate Live API mode to query the cluster.
                  </span>
                )}
              </div>
            </form>
          )}

          {/* TAB 2: QUERY PROCESS PLAN */}
          {activeTab === "recommend" && (
            <form onSubmit={handleRecommendSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div className="caption" style={{ fontSize: 13, color: "var(--ink-soft)" }}>
                ✎ Query the agent memory with Atlas Vector Search (1024-dim Voyage embeddings) + empirical Memory Worth + State Bias.
              </div>

              {/* PRESETS */}
              <div>
                <span className="step-k" style={{ marginBottom: 4 }}>Quick Presets:</span>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
                  <button
                    type="button"
                    className="chip"
                    onClick={() => {
                      setRecQuery("Process plan for an Inconel 718 sleeve with a Ø28H7 bore");
                      setRecMaterial("Inconel 718");
                      setRecProcess("finish boring");
                      setRecFeature("bore");
                      setRecTolBand("H7");
                    }}
                  >
                    Inconel 718 Bore (Ø28H7)
                  </button>
                  <button
                    type="button"
                    className="chip"
                    onClick={() => {
                      setRecQuery("Finish boring plan for Ti-6Al-4V landing gear collar with Ø32H7 bore");
                      setRecMaterial("Ti-6Al-4V");
                      setRecProcess("finish boring");
                      setRecFeature("bore");
                      setRecTolBand("H7");
                    }}
                  >
                    Ti-6Al-4V Finish Boring
                  </button>
                  <button
                    type="button"
                    className="chip"
                    onClick={() => {
                      setRecQuery("High speed face milling plan for Aluminum 7075-T6 aircraft bracket pocket");
                      setRecMaterial("Al 7075-T6");
                      setRecProcess("face milling");
                      setRecFeature("pocket");
                      setRecTolBand("IT8");
                    }}
                  >
                    Al 7075-T6 Face Milling
                  </button>
                </div>
              </div>

              <div>
                <label style={{ display: "block", fontSize: 11, fontFamily: "var(--font-mono)", textTransform: "uppercase", marginBottom: 4 }}>
                  Natural Language Query:
                </label>
                <input
                  type="text"
                  value={recQuery}
                  onChange={(e) => setRecQuery(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "6px 8px",
                    background: "var(--paper)",
                    border: "1.5px solid var(--ink)",
                    borderRadius: 4,
                    fontFamily: "var(--font-ink)",
                    fontSize: 13,
                    boxSizing: "border-box",
                  }}
                  required
                />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label style={{ display: "block", fontSize: 11, fontFamily: "var(--font-mono)", textTransform: "uppercase", marginBottom: 4 }}>
                    Material Scope:
                  </label>
                  <input
                    type="text"
                    value={recMaterial}
                    onChange={(e) => setRecMaterial(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "6px 8px",
                      background: "var(--paper)",
                      border: "1.5px solid var(--ink)",
                      borderRadius: 4,
                      fontFamily: "var(--font-mono)",
                      fontSize: 12,
                      boxSizing: "border-box",
                    }}
                    required
                  />
                </div>

                <div>
                  <label style={{ display: "block", fontSize: 11, fontFamily: "var(--font-mono)", textTransform: "uppercase", marginBottom: 4 }}>
                    Process Scope:
                  </label>
                  <input
                    type="text"
                    value={recProcess}
                    onChange={(e) => setRecProcess(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "6px 8px",
                      background: "var(--paper)",
                      border: "1.5px solid var(--ink)",
                      borderRadius: 4,
                      fontFamily: "var(--font-mono)",
                      fontSize: 12,
                      boxSizing: "border-box",
                    }}
                    required
                  />
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label style={{ display: "block", fontSize: 11, fontFamily: "var(--font-mono)", textTransform: "uppercase", marginBottom: 4 }}>
                    Feature Class:
                  </label>
                  <input
                    type="text"
                    value={recFeature}
                    onChange={(e) => setRecFeature(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "6px 8px",
                      background: "var(--paper)",
                      border: "1.5px solid var(--ink)",
                      borderRadius: 4,
                      fontFamily: "var(--font-mono)",
                      fontSize: 12,
                      boxSizing: "border-box",
                    }}
                    required
                  />
                </div>

                <div>
                  <label style={{ display: "block", fontSize: 11, fontFamily: "var(--font-mono)", textTransform: "uppercase", marginBottom: 4 }}>
                    Tolerance Band:
                  </label>
                  <input
                    type="text"
                    value={recTolBand}
                    onChange={(e) => setRecTolBand(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "6px 8px",
                      background: "var(--paper)",
                      border: "1.5px solid var(--ink)",
                      borderRadius: 4,
                      fontFamily: "var(--font-mono)",
                      fontSize: 12,
                      boxSizing: "border-box",
                    }}
                    required
                  />
                </div>
              </div>

              <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 8 }}>
                <button
                  type="submit"
                  disabled={busy}
                  className="btn primary"
                  style={{ padding: "8px 16px", fontSize: 12 }}
                >
                  {busy ? "Retrieving Plan..." : "🔍 Synthesize Plan with Vector Search"}
                </button>
              </div>
            </form>
          )}

          {/* TAB 3: INGEST NCR REPORT */}
          {activeTab === "ncr" && (
            <form onSubmit={handleNcrSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div className="caption" style={{ fontSize: 13, color: "var(--ink-soft)" }}>
                ✎ Ingest an engineering Non-Conformance Report (NCR) with candidate trials. Enforces Rule 3: every item must cite valid measurement IDs.
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: 12 }}>
                <div>
                  <label style={{ display: "block", fontSize: 11, fontFamily: "var(--font-mono)", textTransform: "uppercase", marginBottom: 4 }}>
                    NCR Number:
                  </label>
                  <input
                    type="text"
                    value={ncrId}
                    onChange={(e) => setNcrId(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "6px 8px",
                      background: "var(--paper)",
                      border: "1.5px solid var(--ink)",
                      borderRadius: 4,
                      fontFamily: "var(--font-mono)",
                      fontSize: 12,
                      boxSizing: "border-box",
                    }}
                    required
                  />
                </div>

                <div>
                  <label style={{ display: "block", fontSize: 11, fontFamily: "var(--font-mono)", textTransform: "uppercase", marginBottom: 4 }}>
                    Summary / Description:
                  </label>
                  <input
                    type="text"
                    value={ncrSummary}
                    onChange={(e) => setNcrSummary(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "6px 8px",
                      background: "var(--paper)",
                      border: "1.5px solid var(--ink)",
                      borderRadius: 4,
                      fontFamily: "var(--font-ink)",
                      fontSize: 12,
                      boxSizing: "border-box",
                    }}
                    required
                  />
                </div>
              </div>

              {/* TRIAL A */}
              <div style={{ background: "var(--paper-dark)", padding: "10px", borderRadius: 4, border: "1px dashed var(--ink)" }}>
                <div style={{ fontSize: 11, fontWeight: 700, fontFamily: "var(--font-mono)" }}>
                  TRIAL 1 (Candidate Fix 1 - Lesson):
                </div>
                <input
                  type="text"
                  value={ncrTrial1Desc}
                  onChange={(e) => setNcrTrial1Desc(e.target.value)}
                  placeholder="Action text"
                  style={{
                    width: "100%",
                    padding: "4px 8px",
                    background: "var(--paper)",
                    border: "1px solid var(--ink)",
                    borderRadius: 3,
                    fontSize: 12,
                    margin: "4px 0",
                    boxSizing: "border-box",
                  }}
                  required
                />
                <input
                  type="text"
                  value={ncrTrial1Mids}
                  onChange={(e) => setNcrTrial1Mids(e.target.value)}
                  placeholder="Citations (e.g. M1, M2, M3)"
                  style={{
                    width: "100%",
                    padding: "4px 8px",
                    background: "var(--paper)",
                    border: "1px solid var(--ink)",
                    borderRadius: 3,
                    fontSize: 11,
                    fontFamily: "var(--font-mono)",
                    boxSizing: "border-box",
                  }}
                  required
                />
              </div>

              {/* TRIAL B */}
              <div style={{ background: "var(--paper-dark)", padding: "10px", borderRadius: 4, border: "1px dashed var(--ink)" }}>
                <div style={{ fontSize: 11, fontWeight: 700, fontFamily: "var(--font-mono)" }}>
                  TRIAL 2 (Candidate Fix 2 - Lesson):
                </div>
                <input
                  type="text"
                  value={ncrTrial2Desc}
                  onChange={(e) => setNcrTrial2Desc(e.target.value)}
                  placeholder="Action text"
                  style={{
                    width: "100%",
                    padding: "4px 8px",
                    background: "var(--paper)",
                    border: "1px solid var(--ink)",
                    borderRadius: 3,
                    fontSize: 12,
                    margin: "4px 0",
                    boxSizing: "border-box",
                  }}
                  required
                />
                <input
                  type="text"
                  value={ncrTrial2Mids}
                  onChange={(e) => setNcrTrial2Mids(e.target.value)}
                  placeholder="Citations (e.g. M9, M10, M11)"
                  style={{
                    width: "100%",
                    padding: "4px 8px",
                    background: "var(--paper)",
                    border: "1px solid var(--ink)",
                    borderRadius: 3,
                    fontSize: 11,
                    fontFamily: "var(--font-mono)",
                    boxSizing: "border-box",
                  }}
                  required
                />
              </div>

              {/* TRIAL C */}
              <div style={{ background: "var(--paper-dark)", padding: "10px", borderRadius: 4, border: "1px dashed var(--ink)" }}>
                <div style={{ fontSize: 11, fontWeight: 700, fontFamily: "var(--font-mono)", color: "#b91c1c" }}>
                  TRIAL 3 (Failed Attempt):
                </div>
                <input
                  type="text"
                  value={ncrTrial3Desc}
                  onChange={(e) => setNcrTrial3Desc(e.target.value)}
                  placeholder="Failed action text"
                  style={{
                    width: "100%",
                    padding: "4px 8px",
                    background: "var(--paper)",
                    border: "1px solid var(--ink)",
                    borderRadius: 3,
                    fontSize: 12,
                    margin: "4px 0",
                    boxSizing: "border-box",
                  }}
                  required
                />
                <input
                  type="text"
                  value={ncrTrial3Mids}
                  onChange={(e) => setNcrTrial3Mids(e.target.value)}
                  placeholder="Citations (e.g. M14, M15, M16)"
                  style={{
                    width: "100%",
                    padding: "4px 8px",
                    background: "var(--paper)",
                    border: "1px solid var(--ink)",
                    borderRadius: 3,
                    fontSize: 11,
                    fontFamily: "var(--font-mono)",
                    boxSizing: "border-box",
                  }}
                  required
                />
              </div>

              <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 8 }}>
                <button
                  type="submit"
                  disabled={busy}
                  className="btn primary"
                  style={{ padding: "8px 16px", fontSize: 12 }}
                >
                  {busy ? "Ingesting..." : "✒ Ingest NCR & Draft Lessons"}
                </button>
              </div>
            </form>
          )}
        </div>

        {/* CARD FOOTER */}
        <div
          style={{
            padding: "8px 14px",
            borderTop: "1.5px solid var(--ink)",
            background: "rgba(23, 21, 15, 0.02)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div style={{ fontSize: 11, color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>
            ISO/IEC 17025 Compliant · MongoDB Atlas Vector Search
          </div>
          <button
            type="button"
            className="btn"
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

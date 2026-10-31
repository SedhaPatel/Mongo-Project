"use client";

import { useState } from "react";
import { useStore } from "@/lib/store";
import { atLeast } from "@/lib/graph";
import SimulateModal from "@/components/SimulateModal";

export default function ControlBar() {
  const {
    stage, busy, doReset, doStage1a, doStage1b, doStage2,
    doArmTTL, doCalibration, doReAsk, doReplayTTL,
  } = useStore();
  const [isSimulateOpen, setIsSimulateOpen] = useState(false);

  return (
    <div
      style={{
        display: "flex",
        gap: 8,
        padding: "6px 12px",
        borderBlock: "1.5px solid var(--ink)",
        flexWrap: "wrap",
        alignItems: "center",
        background: "linear-gradient(180deg, rgba(23,21,15,0.03), transparent)",
      }}
    >
      <button className={`btn${stage === "reset" ? "" : " done"}`} onClick={doReset} disabled={busy}>
        Reset
      </button>
      <button className={`btn${atLeast(stage, "1a") ? " done" : ""}`} onClick={doStage1a}
        disabled={busy || stage !== "reset"} title="POST /demo/stage/1?step=a — ingest NCR-0412">
        Stage 1a · ingest NCR
      </button>
      <button className={`btn${atLeast(stage, "1b") ? " done" : ""}`} onClick={doStage1b}
        disabled={busy || stage !== "1a"} title="POST /demo/stage/1?step=b — corroborate L1 on CMM-02">
        Stage 1b · corroborate L1
      </button>
      <button className={`btn primary${atLeast(stage, "2") ? " done" : ""}`} onClick={doStage2}
        disabled={busy || stage !== "1b"} title="POST /demo/stage/2 — recommend + persist decision">
        Stage 2 · ask for plan
      </button>
      <button className={`btn${stage === "2-arm" ? " done" : ""}`} onClick={doArmTTL}
        disabled={busy || !(stage === "2")} title="POST /demo/stage/3?step=arm — 30 s TTL trial T1">
        Arm TTL
      </button>
      <button className={`btn primary`} onClick={doCalibration}
        disabled={busy || !(stage === "2" || stage === "2-arm")}
        title="POST /calibration — BG-07 as-found +6 µm, U 2 µm">
        Post calibration: BG-07 +6 µm
      </button>
      <button className={`btn${stage === "3" ? " done" : ""}`} onClick={doReAsk}
        disabled={busy || stage !== "3"} title="Re-run POST /recommend for the same query">
        Re-ask plan
      </button>
      <button className="btn" onClick={doReplayTTL}
        disabled={busy || stage !== "3"} title="Fallback if the TTL delete was missed">
        Replay TTL event
      </button>
      {busy && <span className="stamp">working…</span>}

      <button
        type="button"
        className="btn"
        onClick={() => setIsSimulateOpen(true)}
        style={{
          marginLeft: "auto",
          borderStyle: "dashed",
          fontWeight: 700,
          background: "var(--paper-dark)",
          display: "inline-flex",
          alignItems: "center",
          gap: 4,
        }}
        title="Simulate custom calibration drift, ingest new NCR, or query custom plan"
      >
        <span>✎</span> Simulate Custom Case / NCR
      </button>

      <SimulateModal isOpen={isSimulateOpen} onClose={() => setIsSimulateOpen(false)} />
    </div>
  );
}

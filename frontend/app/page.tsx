"use client";

import dynamic from "next/dynamic";
import { MetroProvider, useStore } from "@/lib/store";
import ControlBar from "@/components/ControlBar";
import RecommendationPanel from "@/components/RecommendationPanel";
import ReviewList from "@/components/ReviewList";
import MemoryInspector from "@/components/MemoryInspector";
import EventFeed from "@/components/EventFeed";

// cytoscape needs the DOM SSR is not allowed to touch
const ProvenanceGraph = dynamic(() => import("@/components/ProvenanceGraph"), {
  ssr: false,
});

function Header() {
  const { useFixtures, toggleFixtures, stage } = useStore();
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "6px 10px 2px" }}>
      <h1 style={{ margin: 0, fontSize: 19, letterSpacing: "0.06em", transform: "rotate(-0.4deg)" }}>
        ✒ Metrologic
      </h1>
      <span className="stamp">calibration-aware agent memory</span>
      <button
        type="button"
        onClick={toggleFixtures}
        className="chip"
        title={
          useFixtures
            ? "Running offline with fixtures. Click to switch to LIVE API."
            : "Connected to live API backend. Click to switch to offline fixtures."
        }
        style={{
          marginLeft: 8,
          cursor: "pointer",
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
          background: useFixtures ? "var(--paper-dark)" : "#dbeafe",
          color: "var(--ink)",
          border: "1.5px solid var(--ink)",
          fontFamily: "var(--font-mono)",
          fontSize: 11,
          letterSpacing: "0.08em",
          padding: "1px 8px",
          borderRadius: 999,
          boxShadow: "1.5px 2px 0 var(--ink)",
        }}
      >
        <span
          className="dot"
          style={{
            background: useFixtures ? "var(--ink-faint)" : "var(--state-active)",
          }}
        />
        {useFixtures ? "FIXTURES · offline" : "LIVE API"}
      </button>
      <span className="chip">stage {stage === "reset" ? "—" : stage}</span>
    </div>
  );
}

function Legend() {
  const items: Array<[string, string]> = [
    ["ACTIVE", "var(--state-active)"],
    ["PROVISIONAL", "var(--state-provisional)"],
    ["NEEDS_VERIFICATION", "var(--state-verify)"],
    ["HISTORICAL_ONLY", "var(--state-historical)"],
  ];
  return (
    <div style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
      {items.map(([label, color]) => (
        <span className="legend-item" key={label}>
          <span className="dot" style={{ background: color }} /> {label}
        </span>
      ))}
      <span className="legend-item">
        <span className="dot" style={{ background: "var(--paper-dark)" }} /> pass
      </span>
      <span className="legend-item">
        <span className="dot" style={{ background: "var(--state-verify)" }} /> indeterminate
      </span>
      <span className="legend-item">
        <span className="dot" style={{ background: "var(--state-historical)" }} /> fail / flipped
      </span>
    </div>
  );
}

function CaptionBar() {
  const { caption } = useStore();
  return (
    <div style={{ padding: "4px 12px 8px", borderTop: "1.5px solid var(--ink)", display: "flex", alignItems: "center", gap: 24 }}>
      <span className="caption">✎ {caption}</span>
      <Legend />
    </div>
  );
}

const GRID: React.CSSProperties = {
  flex: 1,
  minHeight: 0,
  display: "grid",
  gridTemplateColumns: "340px 1fr 330px",
  gridTemplateRows: "1fr 1fr",
  gap: 10,
  padding: "8px 10px",
};

function Panels() {
  return (
    <div style={GRID}>
      {/* left column */}
      <div style={{ gridColumn: 1, gridRow: "1 / span 2", display: "flex", flexDirection: "column", gap: 10, minHeight: 0 }}>
        <RecommendationPanel />
        <ReviewList />
      </div>
      {/* centre: graph spans both rows */}
      <div style={{ gridColumn: 2, gridRow: "1 / span 2", minHeight: 0, display: "flex" }}>
        <ProvenanceGraph />
      </div>
      {/* right column */}
      <div style={{ gridColumn: 3, gridRow: "1 / span 2", display: "flex", flexDirection: "column", gap: 10, minHeight: 0 }}>
        <MemoryInspector />
        <EventFeed />
      </div>
    </div>
  );
}

export default function Home() {
  return (
    <MetroProvider>
      <main style={{ height: "100vh", display: "flex", flexDirection: "column" }}>
        <Header />
        <ControlBar />
        <Panels />
        <CaptionBar />
      </main>
    </MetroProvider>
  );
}

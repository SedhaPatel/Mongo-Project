"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import { MetroProvider, useStore } from "@/lib/store";
import ControlBar from "@/components/ControlBar";
import RecommendationPanel from "@/components/RecommendationPanel";
import ReviewList from "@/components/ReviewList";
import MemoryInspector from "@/components/MemoryInspector";
import EventFeed from "@/components/EventFeed";
import HomeView from "@/components/HomeView";
import SimulateModal from "@/components/SimulateModal";
import SlidesModal from "@/components/SlidesModal";

// cytoscape needs the DOM SSR is not allowed to touch
const ProvenanceGraph = dynamic(() => import("@/components/ProvenanceGraph"), {
  ssr: false,
  loading: () => (
    <div
      className="card"
      style={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        minHeight: 300,
        background: "var(--paper)",
      }}
    >
      <div style={{ textAlign: "center" }}>
        <span className="stamp" style={{ marginBottom: 6 }}>CYTOSCAPE CANVAS</span>
        <div className="caption" style={{ fontSize: 13, marginTop: 4 }}>
          ✎ Initializing interactive provenance graph…
        </div>
      </div>
    </div>
  ),
});

function Header({
  view,
  setView,
  onOpenSimulate,
  onOpenSlides,
}: {
  view: "home" | "workbench";
  setView: (v: "home" | "workbench") => void;
  onOpenSimulate: () => void;
  onOpenSlides: () => void;
}) {
  const { useFixtures, toggleFixtures, stage } = useStore();
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
        padding: "6px 14px",
        borderBottom: "1.5px solid var(--ink)",
        background: "var(--paper)",
        flexWrap: "wrap",
        zIndex: 10,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <h1
          style={{
            margin: 0,
            fontSize: 19,
            letterSpacing: "0.06em",
            transform: "rotate(-0.4deg)",
            cursor: "pointer",
            userSelect: "none",
          }}
          onClick={() => setView("home")}
          title="Click to go to Metrologic Home"
        >
          ✒ Metrologic
        </h1>
        <span className="stamp">calibration-aware agent memory</span>

        {/* VIEW NAVIGATION TABS */}
        <div
          style={{
            display: "inline-flex",
            gap: 4,
            background: "rgba(23,21,15,0.06)",
            padding: "2px 4px",
            borderRadius: 6,
            border: "1px solid var(--ink)",
          }}
        >
          <button
            type="button"
            className={`btn${view === "home" ? " primary" : ""}`}
            style={{
              padding: "3px 10px",
              fontSize: 11,
              border: "none",
              boxShadow: "none",
              cursor: "pointer",
            }}
            onClick={() => setView("home")}
          >
            ⌂ Home / Ledger
          </button>
          <button
            type="button"
            className={`btn${view === "workbench" ? " primary" : ""}`}
            style={{
              padding: "3px 10px",
              fontSize: 11,
              border: "none",
              boxShadow: "none",
              cursor: "pointer",
            }}
            onClick={() => setView("workbench")}
          >
            ⎇ Provenance Workbench
          </button>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <button
          type="button"
          onClick={onOpenSimulate}
          className="chip"
          style={{
            background: "var(--paper-dark)",
            padding: "2px 8px",
            fontFamily: "var(--font-mono)",
            fontSize: 11,
          }}
          title="Simulate custom calibration drift, ingest new NCR, or query custom plan"
        >
          ✎ Simulate Case
        </button>

        <button
          type="button"
          onClick={onOpenSlides}
          className="chip"
          style={{
            background: "var(--paper-dark)",
            padding: "2px 8px",
            fontFamily: "var(--font-mono)",
            fontSize: 11,
          }}
          title="Open 5-Slide Executive Pitch Deck"
        >
          📑 Pitch Slides
        </button>

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
  const [view, setView] = useState<"home" | "workbench">("home");
  const [isSimulateOpen, setIsSimulateOpen] = useState(false);
  const [isSlidesOpen, setIsSlidesOpen] = useState(false);

  return (
    <MetroProvider>
      <main style={{ height: "100vh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <Header
          view={view}
          setView={setView}
          onOpenSimulate={() => setIsSimulateOpen(true)}
          onOpenSlides={() => setIsSlidesOpen(true)}
        />

        <div
          style={{
            display: view === "home" ? "flex" : "none",
            flex: 1,
            overflowY: "auto",
            minHeight: 0,
            flexDirection: "column",
          }}
        >
          <HomeView
            onOpenWorkbench={() => setView("workbench")}
            onOpenSimulate={() => setIsSimulateOpen(true)}
            onOpenSlides={() => setIsSlidesOpen(true)}
          />
        </div>

        <div
          style={{
            display: view === "workbench" ? "flex" : "none",
            flex: 1,
            overflow: "hidden",
            minHeight: 0,
            flexDirection: "column",
          }}
        >
          <ControlBar />
          <Panels />
          <CaptionBar />
        </div>

        <SimulateModal isOpen={isSimulateOpen} onClose={() => setIsSimulateOpen(false)} />
        <SlidesModal
          isOpen={isSlidesOpen}
          onClose={() => setIsSlidesOpen(false)}
          onOpenWorkbench={() => setView("workbench")}
        />
      </main>
    </MetroProvider>
  );
}

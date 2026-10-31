"use client";

import { useEffect, useRef, useState } from "react";
import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import { useStore } from "@/lib/store";

const INK = "#17150f";
const PAPER = "#f2efe7";
const PAPER_DARK = "#e7e2d4";

const stylesheet: cytoscape.StylesheetJson = [
  {
    selector: "node",
    style: {
      label: "data(label)",
      color: INK,
      "font-family": "Cascadia Mono, Courier New, monospace",
      "font-size": 7.5,
      "text-wrap": "wrap",
      "text-max-width": 115,
      "transition-property": "background-color, border-color, border-width, width, height",
      "transition-duration": 400,
    } as unknown as cytoscape.Css.Node,
  },
  {
    selector: "node[kind = 'gauge']",
    style: {
      shape: "round-rectangle",
      "background-color": PAPER_DARK,
      "border-width": 2,
      "border-style": "dashed",
      "border-color": INK,
      padding: "26px",
      "min-width": "190px",
      "min-height": "85px",
      "text-valign": "top",
      "text-halign": "center",
      "text-margin-y": 14,
      "font-size": 10,
      "font-weight": "bold",
      "text-max-width": 180,
      "background-opacity": 0.75,
    } as unknown as cytoscape.Css.Node,
  },
  {
    selector: "node[kind = 'gauge'][status = 'OUT_OF_TOLERANCE']",
    style: {
      "border-color": "#dc2626",
      "border-width": 2.5,
      "background-color": "#fecaca",
      "background-opacity": 0.85,
    } as unknown as cytoscape.Css.Node,
  },
  {
    selector: "node[kind = 'measurement'], node[kind = 'measurement_group']",
    style: {
      shape: "round-rectangle",
      width: 106,
      height: 32,
      "background-color": PAPER_DARK,
      "background-opacity": 1,
      "border-width": 1.5,
      "border-color": INK,
      "font-size": 8,
      "text-valign": "center",
      "text-halign": "center",
      "text-wrap": "wrap",
      "text-max-width": 98,
      padding: "4px",
    } as unknown as cytoscape.Css.Node,
  },
  {
    selector: 'node[current_verdict = "indeterminate"]',
    style: {
      "background-color": "#fef08a",
      "border-color": "#ca8a04",
      "border-width": 2,
    } as unknown as cytoscape.Css.Node,
  },
  {
    selector: 'node[current_verdict = "fail"]',
    style: {
      "background-color": "#fca5a5",
      "border-color": "#dc2626",
      "border-width": 2,
    } as unknown as cytoscape.Css.Node,
  },
  {
    selector: "node[kind = 'lesson'], node[kind = 'failed_attempt']",
    style: {
      shape: "round-rectangle",
      width: 130,
      height: 58,
      "border-width": 2.5,
      "border-color": INK,
      "font-size": 8.5,
      "text-wrap": "wrap",
      "text-max-width": 122,
      "text-valign": "center",
      "text-halign": "center",
      padding: "6px",
    } as unknown as cytoscape.Css.Node,
  },
  {
    selector: "node[kind = 'failed_attempt']",
    style: { "border-style": "dashed" } as unknown as cytoscape.Css.Node,
  },
  // validity-state fills (muted to sit inside the paper theme)
  { selector: "node[state = 'ACTIVE']", style: { "background-color": "#bbf7d0", "border-color": "#166534" } as unknown as cytoscape.Css.Node },
  { selector: "node[state = 'PROVISIONAL']", style: { "background-color": "#e2e8f0", "border-color": "#475569" } as unknown as cytoscape.Css.Node },
  { selector: "node[state = 'NEEDS_VERIFICATION']", style: { "background-color": "#fef08a", "border-color": "#ca8a04", "border-width": 3 } as unknown as cytoscape.Css.Node },
  { selector: "node[state = 'HISTORICAL_ONLY']", style: { "background-color": "#fecaca", "border-color": "#991b1b" } as unknown as cytoscape.Css.Node },
  {
    selector: "node[kind = 'decision']",
    style: {
      shape: "diamond",
      width: 72,
      height: 44,
      "background-color": PAPER,
      "border-width": 2,
      "border-color": INK,
      "font-size": 7.5,
      "text-wrap": "wrap",
      "text-max-width": 62,
      "text-valign": "center",
      "text-halign": "center",
    } as unknown as cytoscape.Css.Node,
  },
  {
    selector: "node[flagged]",
    style: {
      "border-color": "#dc2626",
      "border-width": 3,
      "background-color": "#fee2e2",
    } as unknown as cytoscape.Css.Node,
  },
  {
    selector: "edge",
    style: {
      width: 1.5,
      "line-color": "rgba(23,21,15,0.45)",
      "curve-style": "bezier",
      "target-arrow-shape": "triangle",
      "target-arrow-color": "rgba(23,21,15,0.45)",
      "arrow-scale": 0.8,
      "transition-property": "line-color, width, target-arrow-color",
      "transition-duration": 400,
    } as unknown as cytoscape.Css.Edge,
  },
  {
    selector: "edge.pulse-drift",
    style: {
      "line-color": "#ef4444",
      "target-arrow-color": "#ef4444",
      width: 2.8,
    } as unknown as cytoscape.Css.Edge,
  },
];

export default function ProvenanceGraph() {
  const { elements, select, pulse, stage } = useStore();
  const holder = useRef<HTMLDivElement | null>(null);
  const cy = useRef<Core | null>(null);
  const layoutKey = useRef("");
  const fitTimer = useRef<NodeJS.Timeout | null>(null);

  // Graph size & view controls state
  const [isMaximized, setIsMaximized] = useState(false);
  const [spacing, setSpacing] = useState<"compact" | "normal" | "spacious">("normal");

  // Build once
  useEffect(() => {
    if (!holder.current || cy.current) return;
    const c = cytoscape({
      container: holder.current,
      elements: [] as ElementDefinition[],
      style: stylesheet,
      wheelSensitivity: 0.25,
      minZoom: 0.2,
      maxZoom: 3.5,
    });
    cy.current = c;
    c.on("tap", "node", (evt) => {
      const d = evt.target.data();
      if (d.kind === "lesson" || d.kind === "failed_attempt" || d.kind === "decision") {
        select(d.id);
      }
    });

    const ro = new ResizeObserver(() => {
      if (cy.current && !cy.current.destroyed()) {
        try {
          cy.current.resize();
        } catch {}
      }
    });
    ro.observe(holder.current);

    return () => {
      ro.disconnect();
      if (fitTimer.current) {
        clearTimeout(fitTimer.current);
        fitTimer.current = null;
      }
      try {
        const currentCy = cy.current;
        if (currentCy && !currentCy.destroyed()) {
          currentCy.stop(true);
          currentCy.removeAllListeners();
          currentCy.destroy();
        }
      } catch {
        // suppress benign cytoscape internal teardown errors
      }
      cy.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keyboard shortcut: Esc to exit maximized mode
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isMaximized) {
        setIsMaximized(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isMaximized]);

  // When toggling maximized state, re-fit and resize smoothly
  useEffect(() => {
    const timer = setTimeout(() => {
      if (cy.current && !cy.current.destroyed()) {
        try {
          cy.current.resize();
          cy.current.fit(undefined, isMaximized ? 40 : 30);
        } catch {}
      }
    }, 150);
    return () => clearTimeout(timer);
  }, [isMaximized]);

  // Diff elements by id (idempotent patch)
  useEffect(() => {
    const c = cy.current;
    if (!c || c.destroyed()) return;
    try {
      const wantedNode = new Map(elements.nodes.map((n) => [n.data.id, n.data]));
      const wantedEdge = new Map(elements.edges.map((e) => [e.data.id, e.data]));

      c.nodes().forEach((n) => {
        const id = n.id();
        if (!wantedNode.has(id)) n.remove();
        else n.data(wantedNode.get(id) as cytoscape.NodeDataDefinition);
      });
      c.edges().forEach((e) => {
        const id = e.id();
        if (!wantedEdge.has(id)) e.remove();
        else e.data(wantedEdge.get(id) as cytoscape.EdgeDataDefinition);
      });
      for (const data of elements.nodes.map((n) => n.data)) {
        if (!c.$id(data.id).nonempty()) c.add({ group: "nodes", data });
      }
      for (const data of elements.edges.map((e) => e.data)) {
        if (!c.$id(data.id).nonempty()) c.add({ group: "edges", data });
      }

      // re-layout only when the graph grows or the stage changes
      const key = `${stage}|${elements.nodes.length}|${elements.edges.length}|${spacing}`;
      if (key !== layoutKey.current) {
        layoutKey.current = key;
        if (elements.nodes.length > 0) {
          const edgeLength = spacing === "compact" ? 65 : spacing === "spacious" ? 150 : 105;
          try {
            c.layout({
              name: "cose",
              animate: true,
              animationDuration: 400,
              padding: 35,
              idealEdgeLength: edgeLength,
              randomize: false,
            }).run();
          } catch {}

          if (fitTimer.current) {
            clearTimeout(fitTimer.current);
          }
          fitTimer.current = setTimeout(() => {
            if (cy.current && !cy.current.destroyed()) {
              try {
                cy.current.resize();
                cy.current.fit(undefined, 35);
              } catch {}
            }
          }, 320);
        }
      }
    } catch (err) {
      console.warn("[ProvenanceGraph elements patch]", err);
    }
  }, [elements, stage, spacing]);

  // Run layout on demand when spacing changes
  const handleSpacingChange = (newSpacing: "compact" | "normal" | "spacious") => {
    setSpacing(newSpacing);
    const c = cy.current;
    if (!c || c.destroyed() || elements.nodes.length === 0) return;
    const edgeLength = newSpacing === "compact" ? 65 : newSpacing === "spacious" ? 150 : 105;
    try {
      c.layout({
        name: "cose",
        animate: true,
        animationDuration: 350,
        padding: 35,
        idealEdgeLength: edgeLength,
        randomize: false,
      }).run();
    } catch {}

    setTimeout(() => {
      if (c && !c.destroyed()) {
        try {
          c.resize();
          c.fit(undefined, 30);
        } catch {}
      }
    }, 250);
  };

  // Zoom controls
  const handleZoomIn = () => {
    const c = cy.current;
    if (!c || c.destroyed()) return;
    try {
      const center = { x: c.width() / 2, y: c.height() / 2 };
      c.zoom({ level: c.zoom() * 1.25, renderedPosition: center });
    } catch {}
  };

  const handleZoomOut = () => {
    const c = cy.current;
    if (!c || c.destroyed()) return;
    try {
      const center = { x: c.width() / 2, y: c.height() / 2 };
      c.zoom({ level: c.zoom() * 0.8, renderedPosition: center });
    } catch {}
  };

  const handleFit = () => {
    const c = cy.current;
    if (!c || c.destroyed()) return;
    try {
      c.fit(undefined, 30);
    } catch {}
  };

  // pulse on audit events (300 ms colour/width flash, cascade along downstream edges)
  useEffect(() => {
    const c = cy.current;
    if (!c || !pulse.id || c.destroyed()) return;
    try {
      const node = c.nodes().filter((n) => n.id() === pulse.id);
      if (!node.empty()) {
        // flash the node
        void node
          .animate({ style: { "border-width": 6 } }, { duration: 150 })
          .animate({ style: { "border-width": 2.5 } }, { duration: 300 });

        // If it's a gauge drift event or flipped measurement, ripple along downstream edges
        const connectedEdges = node.connectedEdges();
        if (!connectedEdges.empty()) {
          connectedEdges.addClass("pulse-drift");
          setTimeout(() => {
            if (cy.current && !cy.current.destroyed()) {
              try {
                connectedEdges.removeClass("pulse-drift");
              } catch {}
            }
          }, 600);
        }
      }
    } catch {}
  }, [pulse]);

  return (
    <>
      {/* Dimmed backdrop when maximized */}
      {isMaximized && (
        <div
          onClick={() => setIsMaximized(false)}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(23, 21, 15, 0.65)",
            zIndex: 9998,
            backdropFilter: "blur(2px)",
          }}
        />
      )}

      <div
        className="card"
        style={
          isMaximized
            ? {
                position: "fixed",
                top: 16,
                left: 16,
                right: 16,
                bottom: 16,
                zIndex: 9999,
                display: "flex",
                flexDirection: "column",
                boxShadow: "0 16px 48px rgba(0,0,0,0.45)",
                background: "var(--paper)",
                border: "2.5px solid var(--ink)",
                borderRadius: 12,
                overflow: "hidden",
                transition: "all 200ms ease",
              }
            : {
                width: "100%",
                height: "100%",
                display: "flex",
                flexDirection: "column",
                minHeight: 0,
              }
        }
      >
        <div
          className="card-head"
          style={{
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 6,
            padding: "8px 12px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span>provenance graph</span>
            <span className="badge" style={{ fontSize: 9 }}>
              Measurement → Lesson → Recommendation → Outcome
            </span>
            <span style={{ fontSize: 9.5, color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>
              ({elements.nodes.length} nodes)
            </span>
          </div>

          {/* GRAPH SIZE & VIEW CONTROLS */}
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
            {/* Zoom Controls */}
            <div style={{ display: "inline-flex", gap: 2 }}>
              <button
                type="button"
                className="chip"
                onClick={handleZoomOut}
                title="Zoom Out (−)"
                style={{ padding: "1px 6px", fontWeight: 700, fontSize: 12, minWidth: 22, justifyContent: "center" }}
              >
                −
              </button>
              <button
                type="button"
                className="chip"
                onClick={handleZoomIn}
                title="Zoom In (+)"
                style={{ padding: "1px 6px", fontWeight: 700, fontSize: 12, minWidth: 22, justifyContent: "center" }}
              >
                +
              </button>
              <button
                type="button"
                className="chip"
                onClick={handleFit}
                title="Center & Fit All Nodes (⛶)"
                style={{ padding: "1px 7px", fontSize: 10 }}
              >
                ⛶ Fit
              </button>
            </div>

            {/* Layout Spacing / Spread Selector */}
            <div
              style={{
                display: "inline-flex",
                border: "1.5px solid var(--ink)",
                borderRadius: 6,
                overflow: "hidden",
                background: "var(--paper)",
              }}
              title="Graph Spread / Layout Spacing"
            >
              <button
                type="button"
                onClick={() => handleSpacingChange("compact")}
                style={{
                  padding: "1px 6px",
                  fontSize: 9.5,
                  border: "none",
                  cursor: "pointer",
                  background: spacing === "compact" ? "var(--ink)" : "transparent",
                  color: spacing === "compact" ? "var(--paper)" : "var(--ink)",
                  fontFamily: "var(--font-mono)",
                  fontWeight: spacing === "compact" ? 700 : 400,
                }}
                title="Compact spacing"
              >
                Compact
              </button>
              <button
                type="button"
                onClick={() => handleSpacingChange("normal")}
                style={{
                  padding: "1px 6px",
                  fontSize: 9.5,
                  borderLeft: "1px solid var(--ink)",
                  borderRight: "1px solid var(--ink)",
                  borderTop: "none",
                  borderBottom: "none",
                  cursor: "pointer",
                  background: spacing === "normal" ? "var(--ink)" : "transparent",
                  color: spacing === "normal" ? "var(--paper)" : "var(--ink)",
                  fontFamily: "var(--font-mono)",
                  fontWeight: spacing === "normal" ? 700 : 400,
                }}
                title="Normal spacing"
              >
                Normal
              </button>
              <button
                type="button"
                onClick={() => handleSpacingChange("spacious")}
                style={{
                  padding: "1px 6px",
                  fontSize: 9.5,
                  border: "none",
                  cursor: "pointer",
                  background: spacing === "spacious" ? "var(--ink)" : "transparent",
                  color: spacing === "spacious" ? "var(--paper)" : "var(--ink)",
                  fontFamily: "var(--font-mono)",
                  fontWeight: spacing === "spacious" ? 700 : 400,
                }}
                title="Spacious / Wide spacing"
              >
                Wide
              </button>
            </div>

            {/* Expand / Maximize Toggle */}
            <button
              type="button"
              className="chip"
              onClick={() => setIsMaximized(!isMaximized)}
              title={isMaximized ? "Restore view (Press Esc)" : "Expand graph to full screen"}
              style={{
                padding: "2px 8px",
                fontSize: 10,
                background: isMaximized ? "var(--ink)" : "var(--paper)",
                color: isMaximized ? "var(--paper)" : "var(--ink)",
                fontWeight: 600,
                border: "1.5px solid var(--ink)",
              }}
            >
              {isMaximized ? "⤡ Restore (Esc)" : "⤢ Expand"}
            </button>
          </div>
        </div>

        <div className="card-body" style={{ padding: 0, flex: 1, minHeight: 0, position: "relative", overflow: "hidden" }}>
          <div
            className="cy-holder"
            ref={holder}
            style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0, width: "100%", height: "100%" }}
          />
        </div>
      </div>
    </>
  );
}

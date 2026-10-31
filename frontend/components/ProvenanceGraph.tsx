"use client";

import { useEffect, useRef } from "react";
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
      padding: "20px",
      "min-width": "180px",
      "min-height": "80px",
      "text-valign": "top",
      "text-halign": "center",
      "font-size": 11,
      "text-max-width": 160,
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
      shape: "rectangle",
      width: 38,
      height: 25,
      "background-color": PAPER_DARK,
      "background-opacity": 1,
      "border-width": 1.5,
      "border-color": INK,
      "font-size": 8,
      "text-max-width": 90,
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
      width: 96,
      height: 48,
      "border-width": 2.5,
      "border-color": INK,
      "font-size": 9,
      "text-max-width": 115,
      "text-valign": "center",
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
      width: 54,
      height: 32,
      "background-color": PAPER,
      "border-width": 2,
      "border-color": INK,
      "font-size": 8,
      "text-max-width": 110,
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

  // build once
  useEffect(() => {
    if (!holder.current || cy.current) return;
    const c = cytoscape({
      container: holder.current,
      elements: [] as ElementDefinition[],
      style: stylesheet,
      wheelSensitivity: 0.25,
      minZoom: 0.2,
      maxZoom: 3,
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

  // diff elements by id (idempotent patch)
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
      const key = `${stage}|${elements.nodes.length}|${elements.edges.length}`;
      if (key !== layoutKey.current) {
        layoutKey.current = key;
        if (elements.nodes.length > 0) {
          try {
            c.layout({
              name: "cose",
              animate: true,
              animationDuration: 400,
              padding: 30,
              idealEdgeLength: 90,
              randomize: true,
            }).run();
          } catch {}

          if (fitTimer.current) {
            clearTimeout(fitTimer.current);
          }
          fitTimer.current = setTimeout(() => {
            if (cy.current && !cy.current.destroyed()) {
              try {
                cy.current.resize();
                cy.current.fit(undefined, 30);
              } catch {}
            }
          }, 300);
        }
      }
    } catch (err) {
      console.warn("[ProvenanceGraph elements patch]", err);
    }
  }, [elements, stage]);

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
    <div className="card" style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", minHeight: 0 }}>
      <div className="card-head" style={{ justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span>provenance graph</span>
          <span className="badge" style={{ fontSize: 9 }}>
            Measurement → Lesson → Recommendation → Outcome
          </span>
        </div>
        <div style={{ fontSize: 9.5, color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>
          {elements.nodes.length} nodes · {elements.edges.length} edges
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
  );
}

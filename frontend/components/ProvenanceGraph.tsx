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
      "font-size": 7,
      "text-wrap": "wrap",
      "text-max-width": 110,
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
      "text-valign": "top",
      "text-halign": "center",
      "font-size": 11,
      "text-max-width": 160,
      "background-opacity": 0.75,
    } as unknown as cytoscape.Css.Node,
  },
  {
    selector: "node[kind = 'measurement'], node[kind = 'measurement_group']",
    style: {
      shape: "rectangle",
      width: 36,
      height: 24,
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
    style: { "background-color": "#f9d976", "border-color": INK } as unknown as cytoscape.Css.Node,
  },
  {
    selector: 'node[current_verdict = "fail"]',
    style: { "background-color": "#f1a69e", "border-color": INK } as unknown as cytoscape.Css.Node,
  },
  {
    selector: "node[kind = 'lesson'], node[kind = 'failed_attempt']",
    style: {
      shape: "round-rectangle",
      width: 88,
      height: 44,
      "border-width": 2.5,
      "border-color": INK,
      "font-size": 9,
      "text-max-width": 110,
      "text-valign": "center",
    } as unknown as cytoscape.Css.Node,
  },
  {
    selector: "node[kind = 'failed_attempt']",
    style: { "border-style": "dashed" } as unknown as cytoscape.Css.Node,
  },
  // validity-state fills (muted to sit inside the paper theme)
  { selector: "node[state = 'ACTIVE']", style: { "background-color": "#a7cdb2" } as unknown as cytoscape.Css.Node },
  { selector: "node[state = 'PROVISIONAL']", style: { "background-color": "#dcd9cf" } as unknown as cytoscape.Css.Node },
  { selector: "node[state = 'NEEDS_VERIFICATION']", style: { "background-color": "#f4d489" } as unknown as cytoscape.Css.Node },
  { selector: "node[state = 'HISTORICAL_ONLY']", style: { "background-color": "#e9b1a8" } as unknown as cytoscape.Css.Node },
  {
    selector: "node[kind = 'decision']",
    style: {
      shape: "diamond",
      width: 52,
      height: 30,
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
      "border-width": 2.5,
      "background-color": PAPER,
    } as unknown as cytoscape.Css.Node,
  },
  {
    selector: "edge",
    style: {
      width: 1.2,
      "line-color": "rgba(23,21,15,0.55)",
      "curve-style": "bezier",
      "target-arrow-shape": "none",
    } as unknown as cytoscape.Css.Edge,
  },
];

export default function ProvenanceGraph() {
  const { elements, select, pulse, stage } = useStore();
  const holder = useRef<HTMLDivElement | null>(null);
  const cy = useRef<Core | null>(null);
  const layoutKey = useRef("");

  // build once
  useEffect(() => {
    if (!holder.current || cy.current) return;
    cy.current = cytoscape({
      container: holder.current,
      elements: [] as ElementDefinition[],
      style: stylesheet,
    });
    cy.current.on("tap", "node", (evt) => {
      const d = evt.target.data();
      if (d.kind === "lesson" || d.kind === "failed_attempt" || d.kind === "decision") {
        select(d.id);
      }
    });
    return () => {
      cy.current?.stop(true);
      cy.current?.destroy();
      cy.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // diff elements by id (idempotent patch)
  useEffect(() => {
    const c = cy.current;
    if (!c) return;
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
        void c.layout({
          name: "cose",
          animate: true,
          animationDuration: 400,
          padding: 30,
          idealEdgeLength: 90,
          randomize: true,
        }).run();
        const cyAtLayout = c;
        setTimeout(() => {
          if (cy.current && !cyAtLayout.destroyed()) cyAtLayout.fit(undefined, 30);
        }, 500);
      }
    }
  }, [elements, stage]);

  // pulse on audit events (300 ms colour/width flash, then settle)
  useEffect(() => {
    const c = cy.current;
    if (!c || !pulse.id || c.destroyed()) return;
    const node = c.nodes().filter((n) => n.id() === pulse.id);
    if (!node.empty()) {
      void node
        .animate({ style: { "border-width": 6 } }, { duration: 150 })
        .animate({ style: { "border-width": 2 } }, { duration: 300 });
    }
  }, [pulse]);

  return (
    <div className="card" style={{ width: "100%" }}>
      <div className="card-head">
        provenance graph
        <span className="badge">gauge → measurement → lesson → decision</span>
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        <div className="cy-holder" ref={holder} />
      </div>
    </div>
  );
}

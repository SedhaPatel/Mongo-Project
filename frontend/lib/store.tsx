"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { USE_FIXTURES } from "./config";
import { liveApi, connectEvents } from "./api";
import {
  EVENTS_STAGE1A,
  EVENTS_STAGE1B,
  MEMORY_FIXTURES,
  RECOMMEND_FIXTURES,
  REVIEW_FIXTURE,
} from "./data";
import {
  applyEventToGraph,
  armTTL,
  atLeast,
  baseGraph,
  emptyGraph,
  EVENTS_STAGE3_MAIN,
  STAGE_CAPTIONS,
  TTL_EVENT,
  type Stage,
} from "./graph";
import type { AuditEvent, GraphElements, RecommendResult, ReviewDecision } from "./types";

export interface Pulse {
  id: string;
  n: number;
}

export interface Store {
  stage: Stage;
  caption: string;
  events: AuditEvent[];
  elements: GraphElements;
  recommend: RecommendResult | null;
  prevRecommend: RecommendResult | null;
  showDiff: boolean;
  review: ReviewDecision[];
  selected: string | null;
  pulse: Pulse;
  busy: boolean;
  useFixtures: boolean;
  toggleFixtures: () => void;
  setUseFixtures: (v: boolean) => void;
  setCustomCaption: (c: string | null) => void;
  setRecommend: (r: RecommendResult | null) => void;
  refreshLiveState: () => Promise<void>;
  select: (id: string | null) => void;
  doReset: () => void;
  doStage1a: () => void;
  doStage1b: () => void;
  doStage2: () => void;
  doArmTTL: () => void;
  doCalibration: () => void;
  doReAsk: () => void;
  doReplayTTL: () => void;
}

const Ctx = createContext<Store | null>(null);

export function useStore(): Store {
  const s = useContext(Ctx);
  if (!s) throw new Error("useStore outside provider");
  return s;
}

export function MetroProvider({ children }: { children: React.ReactNode }) {
  const [stage, setStage] = useState<Stage>("reset");
  const [customCaption, setCustomCaption] = useState<string | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [elements, setElements] = useState<GraphElements>(emptyGraph);
  const [recommend, setRecommend] = useState<RecommendResult | null>(null);
  const [prevRecommend, setPrevRecommend] = useState<RecommendResult | null>(null);
  const [showDiff, setShowDiff] = useState(false);
  const [review, setReview] = useState<ReviewDecision[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [pulse, setPulse] = useState<Pulse>({ id: "", n: 0 });
  const [busy, setBusy] = useState(false);
  const [useFixtures, setUseFixtures] = useState<boolean>(USE_FIXTURES);

  const useFixturesRef = useRef(useFixtures);
  useFixturesRef.current = useFixtures;

  const stageRef = useRef(stage);
  stageRef.current = stage;
  const recommendRef = useRef<RecommendResult | null>(null);
  recommendRef.current = recommend;

  const toggleFixtures = useCallback(() => {
    setUseFixtures((prev) => !prev);
  }, []);

  const stream = useCallback(
    async (list: AuditEvent[], apply: (ev: AuditEvent) => void, delay = 420) => {
      for (const ev of list) {
        apply(ev);
        await new Promise((r) => setTimeout(r, delay));
      }
    },
    [],
  );

  const elementsRef = useRef<GraphElements>(emptyGraph());
  const applyFixtureEvent = useCallback((ev: AuditEvent) => {
    const g = {
      nodes: elementsRef.current.nodes.map((n) => ({ data: { ...n.data } })),
      edges: elementsRef.current.edges.map((e) => ({ data: { ...e.data } })),
    };
    const pulses = applyEventToGraph(g, ev);
    elementsRef.current = g;
    setElements(g);
    setEvents((prev) => [ev, ...prev]);
    const last = pulses[pulses.length - 1];
    if (last) setPulse((p) => ({ id: last, n: p.n + 1 }));
  }, []);

  const refreshLiveState = useCallback(async () => {
    try {
      const [g, rev] = await Promise.all([liveApi.graph(), liveApi.review()]);
      if (g && g.nodes) {
        elementsRef.current = g;
        setElements(g);
      }
      if (Array.isArray(rev)) {
        setReview(rev);
      }
    } catch (err) {
      console.warn("[refreshLiveState]", err);
    }
  }, []);

  const doReset = useCallback(() => {
    if (!useFixturesRef.current) {
      liveApi.reset().catch((e) => console.warn("[liveApi.reset]", e));
    }
    setStage("reset");
    setCustomCaption(null);
    setEvents([]);
    elementsRef.current = emptyGraph();
    setElements(emptyGraph());
    setRecommend(null);
    setPrevRecommend(null);
    setShowDiff(false);
    setReview([]);
    setSelected(null);
  }, []);

  const setGraph = useCallback((g: GraphElements) => {
    elementsRef.current = g;
    setElements(g);
  }, []);

  const doStage1a = useCallback(async () => {
    if (stageRef.current !== "reset" || busy) return;
    setBusy(true);
    setStage("1a");
    setCustomCaption(null);
    setGraph(baseGraph("1a"));
    if (!useFixturesRef.current) {
      try {
        await liveApi.stage({ n: 1, step: "a" });
      } catch (err) {
        console.warn("[liveApi.stage 1a]", err);
      }
    }
    await stream(EVENTS_STAGE1A, applyFixtureEvent);
    setBusy(false);
  }, [applyFixtureEvent, busy, setGraph, stream]);

  const doStage1b = useCallback(async () => {
    if (stageRef.current !== "1a" || busy) return;
    setBusy(true);
    setStage("1b");
    setCustomCaption(null);
    setGraph(baseGraph("1b"));
    if (!useFixturesRef.current) {
      try {
        await liveApi.stage({ n: 1, step: "b" });
      } catch (err) {
        console.warn("[liveApi.stage 1b]", err);
      }
    }
    await stream(EVENTS_STAGE1B, applyFixtureEvent);
    setBusy(false);
  }, [applyFixtureEvent, busy, setGraph, stream]);

  const doStage2 = useCallback(async () => {
    if (stageRef.current !== "1b" || busy) return;
    setBusy(true);
    setStage("2");
    setCustomCaption(null);
    setGraph(baseGraph("2"));
    let rec: RecommendResult | null = null;
    if (!useFixturesRef.current) {
      try {
        rec = await liveApi.recommend(RECOMMEND_FIXTURES["2"].query);
      } catch (err) {
        console.warn("[liveApi.recommend stage 2]", err);
      }
    }
    setPrevRecommend(null);
    setShowDiff(false);
    setRecommend(rec || RECOMMEND_FIXTURES["2"]);
    setBusy(false);
  }, [busy, setGraph]);

  const doArmTTL = useCallback(() => {
    if (!atLeast(stageRef.current, "2") || stageRef.current === "3" || busy) return;
    setStage("2-arm");
    setCustomCaption(null);
    const g = {
      nodes: elementsRef.current.nodes.map((n) => ({ data: { ...n.data } })),
      edges: elementsRef.current.edges.map((e) => ({ data: { ...e.data } })),
    };
    setGraph(armTTL(g));
    if (!useFixturesRef.current) {
      liveApi.stage({ n: 3, step: "arm" }).catch((e) => console.warn("[liveApi.stage 3 arm]", e));
    }
  }, [busy, setGraph]);

  const doCalibration = useCallback(async () => {
    if (!atLeast(stageRef.current, "2") || busy) return;
    setBusy(true);
    setStage("3");
    setCustomCaption(null);
    if (!useFixturesRef.current) {
      try {
        await liveApi.calibration();
      } catch (err) {
        console.warn("[liveApi.calibration]", err);
      }
    }
    await stream(EVENTS_STAGE3_MAIN(), applyFixtureEvent, 380);
    setReview(REVIEW_FIXTURE);
    setBusy(false);
    setTimeout(() => {
      if (stageRef.current === "3") applyFixtureEvent(TTL_EVENT());
    }, 6000);
  }, [applyFixtureEvent, busy, stream]);

  const doReAsk = useCallback(async () => {
    if (stageRef.current !== "3" || busy) return;
    setBusy(true);
    setCustomCaption(null);
    let nextRec = RECOMMEND_FIXTURES["3"];
    if (!useFixturesRef.current) {
      try {
        nextRec = await liveApi.recommend(RECOMMEND_FIXTURES["3"].query);
      } catch (err) {
        console.warn("[liveApi.recommend stage 3]", err);
      }
    }
    const current = recommendRef.current;
    if (!current || current.decision_id !== nextRec.decision_id) {
      setPrevRecommend(current);
      setRecommend(nextRec);
    }
    setShowDiff(true);
    setBusy(false);
  }, [busy]);

  const doReplayTTL = useCallback(() => {
    if (stageRef.current !== "3") return;
    applyFixtureEvent(TTL_EVENT());
  }, [applyFixtureEvent]);

  // live mode: subscribe to SSE and let backend events patch the graph
  useEffect(() => {
    if (useFixtures) return;
    return connectEvents((ev) => applyFixtureEvent(ev));
  }, [useFixtures, applyFixtureEvent]);

  const value: Store = {
    stage,
    caption: customCaption || STAGE_CAPTIONS[stage],
    events,
    elements,
    recommend,
    prevRecommend,
    showDiff,
    review,
    selected,
    pulse,
    busy,
    useFixtures,
    toggleFixtures,
    setUseFixtures,
    setCustomCaption,
    setRecommend,
    refreshLiveState,
    select: setSelected,
    doReset,
    doStage1a,
    doStage1b,
    doStage2,
    doArmTTL,
    doCalibration,
    doReAsk,
    doReplayTTL,
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

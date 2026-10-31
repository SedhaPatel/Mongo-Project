# Architecture & Design Decisions

This document records decisions made where the initial requirements or specification had ambiguities or tradeoffs, in accordance with Rule 4 and Rule 7 of `AGENTS.md`.

## 1. Support sets members may be memory IDs
`support_sets` is a list of lists of IDs (`List[List[str]]`). Inner elements are typically measurement IDs (`M1`..`M16`), but may also be memory IDs (`L1`, `F1`, `B1`). This allows the lattice to handle lessons built on prior lessons (transitive demotion).

## 2. Evidence for F1 (failed attempt)
F1 represents the failed feed-only reduction trial. Its evidence uses `M14` to `M16` (recorded fails with large out-of-tolerance margin) rather than `M1` to `M5`. This ensures F1's evidence demonstrably survives the BG-07 cascade intact ("everything else unchanged").

## 3. Flagged decisions count in Stage 3
The Stage 3 cascade flags 3 decisions: past decisions `D1` and `D2` (seeded), plus the new Stage 2 decision created by `POST /recommend` with `persist=true` which also used `L2`. This provides a stronger pitch moment ("the plan produced 2 minutes ago is now flagged for review").

## 4. Initial validity states for L1 and L2
Both `L1` and `L2` start as `PROVISIONAL` (grey) after Stage 1a ingestion of NCR-0412. In Stage 1b, only `L1` is corroborated with `CMM-02` measurements and promoted to `ACTIVE` (green). `L2` remains `PROVISIONAL` with only `BG-07` evidence until the calibration event demotes it to `NEEDS_VERIFICATION` (amber).

## 5. Scope fields in retrieval
`material` and `process` are scored as part of `scope_match` in ranking, not enforced as rigid hard filters in `$vectorSearch`. This allows cross-material retrieval (e.g. an Inconel query still retrieves titanium lesson `L1` with lower scope match score).

## 6. Added fields in data contract
- Memories: `title`, `action`, `owner`, `source`, `version`, `valid_from`, `invalid_at`.
- Measurements: `current_verdict` (starts equal to `verdict`; updated by cascade while preserving `verdict`), `feature`.
- Stream state: `stream_state` collection tracks resume tokens for change streams.

## 7. Handling of SUPERSEDED state
`SUPERSEDED` is treated with maximum severity like `HISTORICAL_ONLY` (ranking bias -0.22) and excluded from default retrieval.

## 8. Uncertainty used in verdict recomputation
The calibration event's expanded uncertainty `U` (`as_found_u_mm`) is used for recomputation. The measurement's own recorded `u_mm` represents standard measurement uncertainty at time of capture and is retained for provenance display.

## 9. UI design language is monochrome ink-and-paper
The reference design supplied for Member 3's work is a monochrome hand-drawn sketch composition. The frontend uses a warm-paper + near-black-ink theme (sketchy card borders, stamp shadows) instead of a generic dashboard look. The plan's state colours (Section 11) survive only as small dots/accents and muted node fills, so the demo colour states stay legible without breaking the monochrome aesthetic.

## 10. Fixture stage machine drives panels offline (Track C)
The frontend builds stage graphs by deriving from `graph.stage1/2/3.json` (Stage 1a hides CMM-02/M6–M8 and shows L1 PROVISIONAL; Stage 1b reveals them). Fixture audit events (`events.stage1/3.jsonl`) stream with a small delay and patch node state idempotently, so the demo animates like the live SSE flow. The T1 TTL delete auto-plays ~6 s after Stage 3 when the trial was armed, with the Replay TTL event button as manual fallback — matching the demo script without backend change feeds. A temporary URL-driven auto-demo used for verification was removed after validation.

## 11. T1 inspector entry is a local fixture
Stage 3-arm's T1 memory does not exist in the static fixtures, so the inspector synthesises a minimal T1 document locally; in live mode the inspector should read `GET /memories/T1` instead.


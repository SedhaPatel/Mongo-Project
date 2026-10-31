# Project Progress

## Milestone 0: Database Capability Spike (Section 4)

- **Status:** COMPLETE (ALL 7 CHECKS PASSED)
- **Database Engine:** MongoDB Atlas Local (`mongodb/mongodb-atlas-local:latest`)
- **Connection URI:** `mongodb://127.0.0.1:27017/?directConnection=true`
- **Execution Environment:** Python 3.12 (WSL2 Ubuntu 24.04 environment with PyMongo 4.19.0) / Windows host

---

### 1. Spike Execution Output

Command executed:
```bash
python3 -u backend/spike.py mongodb://127.0.0.1:27017/?directConnection=true
```

Output:
```text
============================================================
Metrologic M0 Spike – MongoDB capability check
============================================================

Connecting to 'mongodb://127.0.0.1:27017/?directConnection=true'...
  Connected.

--- CHECK 1: Pre-images ---
  [PASS] 1_preimages_collMod: collMod accepted changeStreamPreAndPostImages

--- CHECK 2: TTL index ---
  [PASS] 2_ttl_index_creation: TTL index created

--- CHECKS 3, 4, 5, 7: Change stream ---
  [PASS] 3_change_stream_open: Change stream opened

--- CHECK 7: Update event ---
  [PASS] 7_update_event_updatedFields: updatedFields received: {'val': 2}

--- CHECKS 4+5: TTL delete event (slow – waits up to 120 s) ---
  Inserted TTL doc expire_at=2026-10-30T22:18:17.098184+00:00Z  (waiting up to 120s)...
  [PASS] 5_ttl_delete_event: Delete event arrived after ~48s
  [PASS] 4_fullDocumentBeforeChange: fullDocumentBeforeChange present: ['_id', 'expire_at', 'label']

--- CHECK 6: Vector search ---
  Vector index creation requested. Waiting up to 120s for READY...
    Index status: PENDING – waiting...
  [PASS] 6_vector_search: $vectorSearch returned 1 result(s), score=1.0

============================================================
SUMMARY
============================================================
  PASS  1_preimages_collMod
  PASS  2_ttl_index_creation
  PASS  3_change_stream_open
  PASS  4_fullDocumentBeforeChange
  PASS  5_ttl_delete_event
  PASS  6_vector_search
  PASS  7_update_event_updatedFields

Overall: ALL PASS
```

---

### 2. Capabilities & Acceptance Summary

| # | Check | Target Feature | Actual Result | Error / Note | Status |
|---|-------|----------------|---------------|--------------|--------|
| 1 | `1_preimages_collMod` | Change Stream Pre/Post Images | Pre-images enabled via `collMod` | None | **PASS** |
| 2 | `2_ttl_index_creation` | TTL Index (`expireAfterSeconds=0`) | Index created & verified in `list_indexes()` | None | **PASS** |
| 3 | `3_change_stream_open` | Real-time Change Stream Cursor | Cursor established with `updateLookup` and `whenAvailable` | None | **PASS** |
| 4 | `4_fullDocumentBeforeChange` | Pre-image Document in Delete Event | Delivered in event (`_id`, `expire_at`, `label`) | None | **PASS** |
| 5 | `5_ttl_delete_event` | TTL Deletion via Background Monitor | Actual TTL delete event captured after 48s | None | **PASS** |
| 6 | `6_vector_search` | SearchIndexModel & `$vectorSearch` | Search index created, transitioned to `READY`, query returned score=1.0 | None | **PASS** |
| 7 | `7_update_event_updatedFields` | Change Stream Update Event | Event received with populated `updateDescription.updatedFields` | None | **PASS** |

---

### 3. Fallback Decisions and Readiness

Although all checks passed natively on Atlas Local, the defined fallbacks from Section 4 are locked into the system design:

1. **Pre-images unavailable:**
   - *Fallback:* Maintain prior state in `history[]` and `audit_log`; UI uses its own cache. (Not triggered - native pre-images verified).
2. **TTL delete event missed/delayed:**
   - *Fallback:* "Replay TTL event" button triggers rehearsed event from `seed/fixtures/ttl_delete_event.json`. (Fallback retained for demo reliability).
3. **Change stream unavailable:**
   - *Fallback:* Endpoint parameter `POST /calibration?direct=true` triggers inline cascade execution. (Fallback retained for isolated testing).
4. **Vector search unavailable on tier:**
   - *Fallback:* Atlas Local container on demo laptop used directly. (Verified working with full vector search capability).

---

### 4. Configuration and Credentials Status

- **Database:** Local MongoDB Atlas container running on `mongodb://127.0.0.1:27017/?directConnection=true`.
- **Still required for subsequent milestones:**
  - `ANTHROPIC_API_KEY`: Needed for Stage 1 NCR drafting and Stage 3 plan rewording (M4+), or disk fixtures if offline.
  - `VOYAGE_API_KEY`: Needed for real-time embedding generation (M3+), or precomputed embeddings in `fixtures/embeddings.json` if offline.



---

## Milestone 1: Contracts and Scaffolding (All Members)

- **Status:** COMPLETE
- **Deliverables:**
  - `backend/app/models.py`: Data Contract v1 implementing `ValidityState`, `Verdict`, `MemoryType`, `Scope`, `Memory`, `Measurement`, `Gauge`, `Decision`, `AuditLog`, `StreamState`.
  - `backend/app/config.py`: Environment variables and default configuration.
  - `backend/app/db.py`: Idempotent bootstrap for collections, pre-images, TTL, standard indexes, and Vector Search.
  - `docs/DECISIONS.md`: Records design decisions 1–8 per Section 16 of PLAN.md.
  - `frontend/fixtures/`: Exported sample JSON (`memory.L1.json`, `memory.L2.json`, `review.json`, `recommend.stage2.json`, `recommend.stage3.json`, `graph.stage1.json`, `graph.stage2.json`, `graph.stage3.json`, `events.stage1.jsonl`, `events.stage3.jsonl`).
  - `Makefile`: Commands for `up`, `seed`, `api`, `test`, `web`.
  - `.env.example`: Configuration template committed.

---

## Milestone 2: Validity Engine (Pure Code) (Member B / Metrology)

- **Status:** COMPLETE (ALL 18 ACCEPTANCE CHECKS PASSED)
- **Deliverables:**
  - `backend/app/validity/metrology.py`: Decimal interval guard-band formula ($x' = x - e$, interval $[x' - U, x' + U]$ against $[lo, hi]$).
  - `backend/app/validity/lattice.py`: Support-set status evaluation (`holds`, `weakened`, `broken`), monotonic severity resolution (`SEVERITY`), and multi-instrument independent support checking.
  - `backend/tests/test_metrology.py`: Exhaustive table-driven test suite covering all values from Section 6.2 (including boundary cases and negative $e$).
  - `backend/tests/test_lattice.py`: Multi-instrument lattice tests including L1 independent-support survival, L2 demotion, all-broken case, and transitive demotion.

### Acceptance Check Command Output:
```bash
uv run pytest backend/tests/test_metrology.py backend/tests/test_lattice.py -q
```
```text
..................                                                       [100%]
18 passed in 0.13s
```

---

## Milestone 3 & 5 Progress: Calibration Cascade & Synthetic Seed (Member B)

- **Status:** VALIDATED
- **Deliverables:**
  - `backend/seed/scenario.yaml`: 6 gauges, NCR-0412 trials, measurements M1–M16, M-old, demo memories L1, L2, F1, decisions D1, D2.
  - `backend/seed/generate.py`: ~193 filler measurements, 13 background lessons, precomputed 1024-dim unit vectors in `fixtures/embeddings.json`.
  - `backend/seed/reset.py`: Drops and reloads demo data under 10s.
  - `backend/seed/stages.py`: Step-by-step stage runners (1a, 1b, 2, 3-arm, 3).
  - `backend/app/validity/cascade.py`: Suspect window selection ($last\_good\_cal < timestamp \le event\_time$), verdict recomputation, support-set lattice demotion, $graphLookup transitive demotion, decision review flagging, and strict idempotency.
  - `backend/app/streams/gauge_watcher.py`: Change stream watcher with resume token persistence and direct execution fallback.
  - `backend/app/events.py`: Thread-safe audit log recorder with 200-event circular replay buffer.
  - `backend/tests/test_cascade.py` & `backend/tests/test_stages.py`: Comprehensive test suites proving M-old untouched, Section 9.5 expected outcome table, strict idempotency, and full stage progression.

### Full Test Suite Execution Output:
```bash
uv run pytest
```
```text
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.2.0, pluggy-1.7.0
rootdir: D:\CODING\Mongo-Project
configfile: pyproject.toml
testpaths: backend/tests, tests
plugins: anyio-4.15.1
collected 22 items

backend\tests\test_cascade.py ...                                        [ 13%]
backend\tests\test_lattice.py .......                                    [ 45%]
backend\tests\test_metrology.py ...........                              [ 95%]
backend\tests\test_stages.py .                                           [100%]

============================= 22 passed in 0.49s ==============================
```

---

## Milestone 7: UI (Track C / Member 3)

- **Status:** COMPLETE (fixtures-first, offline)
- **Design language:** Monochrome ink-and-paper theme (hand-drawn sketch borders, warm paper background, near-black ink, stamp-style shadows), per the supplied reference image. The plan's state colours (Section 11) are kept as function dots/accents only, so the demo stays legible without breaking the monochrome aesthetic.
- **Deliverables:**
  - `frontend/` Next.js 15 (App Router) + TypeScript + Tailwind v4 + Cytoscape.js.
  - `frontend/app/page.tsx` — three-panel layout + demo control bar: recommendation panel (with plan diff), provenance graph (spans full height), memory inspector, event feed, review list.
  - `frontend/components/ControlBar.tsx` — Reset, Stage 1a, Stage 1b, Stage 2, Arm TTL, Post calibration BG-07 +6 µm, Re-ask plan, Replay TTL event. Buttons are stage-gated (sequential demo flow) and mark completed stages.
  - `frontend/components/ProvenanceGraph.tsx` — Cytoscape graph: compound gauge parents, measurement children, lesson/failed-attempt nodes coloured by validity state, decision diamonds stamped red when flagged; idempotent element diffing by id; 300 ms pulse animation on audit events; `cose` re-layout with fit on stage change.
  - `frontend/components/RecommendationPanel.tsx` — plan steps (`apply` / `verify on <instrument>` highlighted / `avoid`), lesson chips coloured by state, and the Stage-2 vs Stage-3 plan diff with the inserted verify step outlined.
  - `frontend/components/MemoryInspector.tsx` — raw document JSON, state-history timeline, evidence chain (recorded vs current verdict per measurement, grouped by gauge/support set), per-memory ranking trace table (one column per score term).
  - `frontend/components/EventFeed.tsx` — SSE audit events newest-first, TTL deletions stamped.
  - `frontend/components/ReviewList.tsx` — flagged decisions with part serials and `review_reason`.
  - `frontend/lib/store.tsx` — fixtures stage machine: reset → 1a → 1b → 2 → 2-arm → 3; streams fixture audit events with timed release and patches the graph idempotently (measurement verdict flips, L2 → NEEDS_VERIFICATION, L1 saved-by-CMM-02 note, decision flagging, T1 TTL deletion, auto-played TTL delete ~6 s after calibration with manual Replay fallback).
  - `frontend/lib/api.ts` + `frontend/lib/config.ts` — live-API bridge: `NEXT_PUBLIC_USE_FIXTURES=0` switches to `NEXT_PUBLIC_API_BASE` REST calls + SSE subscription; fixture mode never waits for the backend.
  - `.env.example` — added `NEXT_PUBLIC_USE_FIXTURES`, `NEXT_PUBLIC_API_BASE`.
- **Verification performed:**
  - `npm run build` — compiled and typechecked clean (`Next.js 15.5.28`, standalone output, apps `index.html` and static chunks produced).
  - Headless-Chrome walkthrough of the full reset → Stage 3 sequence (control-bar actions + timed fixture event streaming): plan diff view, 3 flagged review decisions, 17-event feed including `ttl_deleted` T1, gauge status OUT_OF_TOLERANCE, recomputed verdicts and amber L2 all rendered on screen.
  - Browser console cleaned of cytoscape style warnings (invalid shape name, boolean selector syntax, stray CSS property, wheel sensitivity) and unmount races guarded.
- **Notes / limitations:**
  - M14–M16 are not in the graph fixtures, so failed-attempt F1's evidence chain renders from the graph where available; adding them to `graph.*.json` would fill that gap.
  - One benign teardown-only cytoscape console error (`notify` on destroy) can appear when a page closes mid-layout; not reproducible in normal use.
  - Live-API mode is wired but unexercised: Track A endpoints (`main.py`, ingestion/recall) are not implemented yet; fixtures mode is the default and demo path.
  - A temporary `?autodemo=1` harness used for screenshot verification was removed after verification; the shipped UI drives all stages from the control bar.

---

## Milestone 3 (Track A): Lesson writer and corroboration (PLAN 7.2, 7.4)

- **Status:** COMPLETE
- **Deliverables:**
  - `backend/app/memory/writer.py`: `ProvenanceError`, `write_lesson()` (provenance enforced, evidence grouped by gauge into `support_sets`, 30-day BSON `expire_at`, contract-validated via `Memory`), `corroborate()` (merges evidence by instrument, promotes only with an independent holding set, unsets `expire_at`), `set_statuses()` (reuses `validity/lattice.py`).
  - `backend/app/embeddings.py`: optional offline resolution through `backend/seed/fixtures/text_embeddings.json` after cache and before Voyage. Exact-text only; a miss with `OFFLINE=1` still raises.
  - `backend/seed/text_embeddings.py` + `backend/seed/fixtures/text_embeddings.json`: deterministic 1024-dim fixture vectors for the demo texts (synthetic data, not a Voyage substitute).
  - `backend/tests/test_writer.py`: 11 tests (empty/unknown provenance refused, grouping, 30-day TTL, ID allocation, corroboration merge/promotion/same-gauge case).
- **VERIFY – Voyage model/dimension:** `voyage-3-large` exists and defaults to 1024 dims (source: https://docs.voyageai.com/docs/embeddings, checked 2026-10-31). No live API call was possible without a key; the fixture path is what makes the suite pass offline.

### Check command output
```bash
python -m pytest backend/tests/test_writer.py -q
```
```text
...........                                                              [100%]
11 passed in 0.59s
```

```bash
python -m pytest -q
```
```text
..................................                                       [100%]
34 passed in 1.20s
```

---

## Milestone 3 (Track A): Ranking and retrieval (PLAN 7.5)

- **Status:** COMPLETE
- **Deliverables:**
  - `backend/app/memory/ranking.py`: `memory_worth`, `recency_factor`, `scope_match`, `score_memory`, `rank_memories`, `traces`; the weight constants and state-bias table are exported so tests assert them.
  - `backend/app/memory/retrieval.py`: `$vectorSearch` pipeline with workspace/type/state pre-filters, `history=true` drops the state filter, optional `scope_filter` for material/process, `search_memories` response shape for `GET /memories/search`.
  - **Fallback:** when the deployment cannot serve `$vectorSearch` (standalone MongoDB here; `tests/mock_db.py` in tests) the same filter is applied with `find` plus in-process cosine. The fallback is only selected when the aggregation cannot produce `vector_score`, so Atlas always uses the index. Recorded in DECISIONS 15.
  - `backend/tests/test_ranking.py`: 17 tests covering the weight/bias table, MW formula, recency, scope share, every trace term, deterministic ordering, history mode and scope filtering.
- **Ranking trace on the seed (Stage 2 query, top 5):**
```text
 L2 final=0.5325 vec=0.3426 state=PROVISIONAL        bias=+0.04 mw=0.500 scope=1.0
 L1 final=0.3375 vec=0.1676 state=PROVISIONAL        bias=+0.04 mw=0.500 scope=0.8
 F1 final=0.3370 vec=0.1671 state=PROVISIONAL        bias=+0.04 mw=0.500 scope=0.8
 B1 final=0.2538 vec=0.0145 state=ACTIVE             bias=+0.12 mw=0.889 scope=0.2
 B4 final=0.2498 vec=0.0276 state=ACTIVE             bias=+0.12 mw=0.800 scope=0.2
```

### Check command output
```bash
python -m pytest backend/tests/test_ranking.py -q
```
```text
.................                                                        [100%]
17 passed in 1.01s
```

---

## Milestone 3 (Track A): LLM wrapper and NCR ingest (PLAN 7.3)

- **Status:** COMPLETE
- **Deliverables:**
  - `backend/app/agent/llm.py`: `draft_lessons` / `reword_plan` with a single forced `tool_choice`, disk cache via `cache.py` keyed by `(model, tool, system, input, attempt)`, and `LLMUnavailable` when there is no key / `OFFLINE=1` miss / transport error. Transport is the Anthropic Messages REST API through `httpx` (DECISIONS 17); `tool_choice={"type":"tool","name":...}` is sent exactly as the SDK would.
  - `backend/app/agent/ingest.py`: validates and upserts measurements through the frozen `Measurement` contract (`current_verdict = verdict`, empty `verdict_history`), calls the forced tool, validates every returned ID against the input IDs and every item's shape, retries once, then uses `seed/fixtures/ncr_0412_lessons.json`. The fallback is itself validated and only used for the NCR it describes. Every accepted draft goes through `write_lesson` (so provenance is still enforced).
  - `backend/seed/fixtures/ncr_0412_lessons.json`: committed offline draft (L1, L2, F1 order) used by the demo.
  - `backend/tests/test_ingest.py`: 9 tests — L1/L2/F1 order and support sets, unknown-citation rejection + fallback, retry-once acceptance, cached draft, non-matching NCR refused, invalid body refused, scope field cleanup.
- **Determinism:** the fallback draft is written to the disk cache under the same key, so a later `POST /ncr` for NCR-0412 replays the identical draft with `draft_source="cache"` and no network.
- **Not touched:** `validity/`, `streams/gauge_watcher.py`, `seed/scenario.yaml`, `seed/stages.py`, the frontend.

### Check command output
```bash
python -m pytest backend/tests/test_ingest.py -q
```
```text
.........                                                                [100%]
9 passed in 1.21s
```

```bash
python -m pytest -q
```
```text
............................................................             [100%]
60 passed in 2.23s
```

---

## Milestone 3 (Track A): Plan building and rewording (PLAN 7.7)

- **Status:** COMPLETE
- **Deliverables:**
  - `backend/app/agent/recommend.py`: `build_plan_steps` (apply / verify / avoid built by code in rank order), `pick_verify_instrument` (OK gauges only, excludes every gauge in a weakened/broken support set, prefers `type == "cmm"`, then alphabetical), `build_explanation` (deterministic sentence grounded in `history[]`), `validate_reword` (same count, order, `kind`, `lesson_ids`; wording only), decision persistence (`D<next integer>`, ignores `D-STAGE2`-style demo IDs), `$addToSet used_by`, `decision_created` event.
  - `backend/tests/mock_db.py`: added `$addToSet` support so the `used_by` assertion exercises the real update.
  - `backend/tests/test_recommend.py`: 9 tests — Stage 2 apply L1/L2 + avoid F1, full trace, Stage 3 verify on CMM-02 with L1 unchanged, CMM preference and alphabetical fallback, weakened-gauge exclusion, reword count/id/kind guard, retry once, valid wording applied with `verify_instrument` preserved, history-only lessons skipped.
- **LLM behaviour offline:** forced rewording is unavailable without a key, so `reword_source="code"` and the code-built text ships. A valid cached reply is used when present; any shape change is rejected and the code text is kept.
- **Trace (corroborated L1, then BG-07 +0.006 mm / U 0.002 mm):**
```text
STAGE 2 D3 code
  apply ['L2'] | Apply: Raise coolant concentration to 10% before finish boring Inconel 718 bores
  apply ['L1'] | Apply: Add a finishing spring pass with 0.05 mm radial depth of cut on Ø32H7 titanium finish boring
  avoid ['F1'] | Do not attempt feed reduction alone on Ø32H7 titanium finish boring; ...
  apply ['B1'] | Apply: Apply calibrated feed rate of 0.12 mm/tooth for Al 7075-T6 face milling
  apply ['B4'] | Apply: Apply calibrated feed rate of 0.12 mm/tooth for Inconel 718 thread milling
  trace: [('L2', 0.5325), ('L1', 0.4175), ('F1', 0.337), ('B1', 0.2538), ('B4', 0.2498)]
STAGE 3 re-ask code
  apply ['L1'] | Apply: Add a finishing spring pass with 0.05 mm radial depth of cut on Ø32H7 titanium finish boring
  verify ['L2'] CMM-02 | Verify on CMM-02 before adopting: Raise coolant concentration to 10% before finish boring Inconel 718 bores
  avoid ['F1'] | Do not attempt feed reduction alone on Ø32H7 titanium finish boring; ...
  trace: [('L1', 'ACTIVE', 0.4175), ('L2', 'NEEDS_VERIFICATION', 0.3925), ('F1', 'PROVISIONAL', 0.337), ...]
  explanation: L2 is now NEEDS_VERIFICATION after BG-07 out of tolerance, event ev-bg07-demo, so the plan verifies it on CMM-02 before it is applied.
  review: ['D1', 'D2', 'D3']
```

### Check command output
```bash
python -m pytest backend/tests/test_recommend.py -q
```
```text
.........                                                                [100%]
9 passed in 1.46s
```

```bash
python -m pytest -q
```
```text
.....................................................................    [100%]
69 passed in 2.87s
```

---

## Milestone 3 (Track A): API, SSE and demo endpoints (PLAN 8, 8.1, 10)

- **Status:** COMPLETE
- **Environment note:** `uv` is not on PATH here, so every check is run with `python -m pytest` (Python 3.14.6, pymongo 4.19, standalone MongoDB at `mongodb://127.0.0.1:27017`). `$vectorSearch` and `$changeStream` are unavailable on this deployment; the retrieval fallback (DECISIONS 15) and the inline cascade (DECISIONS 23) are exercised by the live run below.
- **Deliverables (`backend/app/main.py`):**
  1. `GET /events` subscribes to the live `backend.app.events` bus inside the response generator and unsubscribes in its `finally` block (the previous code leaked one queue per connection).
  2. `POST /demo/stage/{stage_n}` takes the `?step=` query parameter: stage 1 defaults to `a` (NCR ingest), `step=b` corroborates L1 on CMM-02; stage 2 persists `D-STAGE2`; stage 3 supports `step=arm` and the default calibration run.
  3. `GET /decisions/review` is sorted newest first instead of relying on collection order.
  4. `/memories/search` is registered before `/memories/{memory_id}` and is not shadowed.
  5. The database handle is lazy (`get_db_handle()`), so importing `main`/`create_app()` needs no MongoDB; tests inject `main._db`.
  - Endpoints added: `POST /ncr`, `POST /lessons/{id}/corroborate`, `POST /recommend`, `GET /memories/search`, `GET /memories/{id}` (memory + evidence chain with live `gauge_cal_status`), `GET /graph` (Cytoscape elements, 36 nodes), `POST /calibration`, `GET /decisions/review`, `POST /demo/reset`.
  - `backend/app/events.py`: `clear_events()` so `/demo/reset` empties the SSE replay buffer as well as the collections.
  - `backend/app/streams/memory_watcher.py`: removed the unused `UpdateOptions` import that pymongo 4.19 does not export (DECISIONS 22).
  - `backend/app/cache.py`: cache keys/writes accept BSON dates via `default=str` (DECISIONS 25).
  - `backend/tests/test_api.py`: 10 tests over `TestClient` + `MockDatabase` — full stage flow, `?direct=true`, corroborate merge, 404/400 paths, SSE replay + generator-owned unsubscribe, event-bus broadcast, graph budget and search ordering.
- **SSE test note:** `TestClient` cannot cleanly close an endless event stream, so the test drives `main._sse_stream(replay=1)`'s body iterator directly: one replay chunk, then `aclose()`, asserting `_SUBSCRIBERS` is empty afterwards.

### Check command output
```bash
python -m pytest backend/tests/test_api.py -q
```
```text
..........                                                               [100%]
10 passed in 4.09s
```

```bash
python -m pytest -q
```
```text
........................................................................ [ 91%]
.......                                                                  [100%]
79 passed in 14.62s
```

### Live acceptance on the local MongoDB (no API key)

Reset -> Stage 1a -> Stage 1b -> Stage 2 -> `POST /calibration?direct=true` -> `POST /recommend` -> review/graph/search:

```text
POST /demo/reset -> 200
{"gauges": 6, "background_lessons": 13, "measurements": 193, "decisions": 2}

POST /demo/stage/1?step=a -> 200
draft_source: cache
memory_ids: ["L1", "L2", "F1"]
L1 lesson          PROVISIONAL  support_sets [["M1","M2","M3","M4","M5"]]
L2 lesson          PROVISIONAL  support_sets [["M9","M10","M11","M12","M13"]]
F1 failed_attempt  PROVISIONAL  support_sets [["M14","M15","M16"]]

POST /demo/stage/1?step=b -> 200
memory_id: L1, new_state: ACTIVE
support_sets: [["M1","M2","M3","M4","M5"], ["M6","M7","M8"]]

POST /demo/stage/2 -> 200 (decision D-STAGE2, reword_source code)
  apply ["L2"] | Apply: Raise coolant concentration to 10% before finish boring Inconel 718 bores
  apply ["L1"] | Apply: Add a finishing spring pass with 0.05 mm radial depth of cut on Ø32H7 titanium finish boring
  avoid ["F1"] | Do not attempt feed reduction alone on Ø32H7 titanium finish boring; ... Failed on a prior job (F1)
  trace: L2 0.5326, L1 0.4176, F1 0.3371, B1 0.2538, B4 0.2499

POST /calibration?direct=true -> 200
{"event_id": "ev-bg07-live", "direct": true,
 "cascade_summary": {"measurements_recomputed": 53, "verdict_changes": 4,
                     "lesson_changes": 1, "decisions_flagged": 3}}

POST /recommend (after cascade) -> 200 (decision D3)
  apply  ["L1"]          | Apply: Add a finishing spring pass with 0.05 mm radial depth of cut ...
  verify ["L2"] CMM-02   | Verify on CMM-02 before adopting: Raise coolant concentration to 10% ...
  avoid  ["F1"]          | Do not attempt feed reduction alone ...
  explanation: L2 is now NEEDS_VERIFICATION after BG-07 out of tolerance, event ev-bg07-live,
               so the plan verifies it on CMM-02 before it is applied.
  trace: L1 ACTIVE 0.4176, L2 NEEDS_VERIFICATION 0.3926, F1 PROVISIONAL 0.3371, ...

GET /memories/L1 -> flat memory document + evidence: state ACTIVE, living on BG-07 + CMM-02
GET /memories/L2 -> flat memory document + evidence: state NEEDS_VERIFICATION, M10 and M12 now indeterminate
GET /decisions/review -> 3 flagged, newest first: D-STAGE2, D2, D1
  review_reason: "Used L2, now NEEDS_VERIFICATION after BG-07 calibration event ev-bg07-live"
GET /graph -> {"elements": {"nodes": 36, "edges": 24}} (gauge 6, measurement 16,
              measurement_group 6, lesson 2, failed_attempt 1, lesson_group 1,
              decision 4) — under 40
GET /memories/search -> 200, 5 hits: L2 NEEDS_VERIFICATION, L1 ACTIVE, B4 ACTIVE, F1 PROVISIONAL, B9 ACTIVE
```

**DONE WHEN:** the three demo stages match the checklist: L1/L2/F1 PROVISIONAL after `/ncr`, L1 ACTIVE after CMM-02 corroboration, Stage 2 applies L1+L2 and avoids F1 with a full ranking trace, and after `BG-07 +0.006 mm / U 0.002 mm` the re-ask verifies L2 on CMM-02 while L1 stays ACTIVE.

### Live event feed and TTL fields (same run, persisted `audit_log`)

`GET /events` replays `backend.app.events._REPLAY_BUFFER`, which receives the same documents `log_event()` writes to `audit_log`. The inline cascade published the whole sequence for `ev-bg07-live` in order:

```text
calibration_posted
cascade_started
measurement_recomputed x4   (M10, M12, plus the two other BG-07 verdict changes)
lesson_saved_by_independent_support   (L1, "saved by independent support on CMM-02")
lesson_state_changed          (L2 -> NEEDS_VERIFICATION)
decision_flagged x3           (D-STAGE2, D2, D1)
cascade_finished
```

The unit test `test_events_replays_and_unsubscribes_in_generator` proves the SSE generator subscribes, replays, and unsubscribes; `test_event_bus_broadcasts_to_active_subscribers` proves a live subscriber queue receives the same dict.

TTL/provenance fields on the live documents: `L2` is still PROVISIONAL and carries a 1024-float `embedding` and a BSON `expire_at` of `2026-11-30T06:04:27Z` (30 days after creation). `L1` was promoted to ACTIVE by corroboration, so `write_lesson`'s `expire_at` was unset by `corroborate()` (PLAN 7.4); its history is `created -> corroborated by CMM-02 (NCR-0419) -> saved by independent support on CMM-02`. `POST /demo/reset` took 0.26 s (budget: 10 s).

Expected local noise: `bootstrap()` prints `Notice: vector search index creation ... SearchNotEnabled` twice on the standalone server; the exception is caught, and retrieval uses the in-process cosine fallback (DECISIONS 15).

### Public endpoints on a scratch database

Reset -> `POST /ncr` (the public endpoint, not the demo runner) -> `POST /calibration` **without** the flag, on a scratch DB that is dropped afterwards:

```text
POST /ncr -> 200 cache ['L1', 'L2', 'F1']
states: [('L1', 'PROVISIONAL'), ('L2', 'PROVISIONAL'), ('F1', 'PROVISIONAL')]
POST /calibration (no flag) -> 200 direct: True
cascade_summary: {"measurements_recomputed": 53, "verdict_changes": 4,
                  "lesson_changes": 2, "decisions_flagged": 2}
L2: NEEDS_VERIFICATION L1: HISTORICAL_ONLY
POST /ncr (empty measurements) -> 400 measurements must contain at least one document
```

`L1` is HISTORICAL_ONLY here because this scratch flow skips Stage 1b: without the CMM-02 set, its only evidence is on BG-07. That is the lattice working as specified and is exactly why the demo corroborates L1 before the calibration. The missing `?direct` flag also proves the standalone fallback in DECISIONS 23.





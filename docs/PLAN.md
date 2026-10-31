# Metrologic: Detailed Implementation Plan

Calibration-aware agent memory for a machining / additive-manufacturing shop.
MongoDB Student Hackathon, Track 1 (Agentic Memory).

This document is written for a coding agent (and for the humans supervising it). It replaces the 12-hour sketch with exact contracts, algorithms, file-by-file specs, test cases and acceptance checks.

---

## 0. Rules for the coding agent (put this section in your rules file, e.g. AGENTS.md)

1. Build milestone by milestone (Section 14). Do not start milestone N+1 until every acceptance check of milestone N passes. Run the check commands and paste the output into `docs/PROGRESS.md`.
2. **Validity is decided by deterministic Python, never by the LLM.** The LLM only (a) drafts lessons from NCR text and (b) rewords plan steps that code has already built.
3. **A lesson may never be written without measurement IDs.** `write_lesson()` must raise if they are missing or unknown.
4. Never change the data contract (Section 5) or `models.py` after Milestone 1 without writing the reason in `docs/DECISIONS.md`.
5. Every function in Sections 6 and 7 must be importable and testable without a running API server, and without the LLM (use the disk cache, Section 7.6).
6. All data is synthetic. Store feature class and tolerance band only. Never store drawings, customer names or operator names.
7. When this document is silent, pick the simplest option and record it in `docs/DECISIONS.md`. Do not add features that are not listed here.
8. Anything marked **VERIFY** is a claim about an external service that must be tested, not assumed.

**Never cut:** mandatory provenance on lesson writes, verdict recomputation, the independent-support save of L1, the review list, and the visible plan change in Stage 3.

---

## 1. What we are building (one paragraph)

An agent that learns machining lessons from non-conformance reports (NCRs). Each lesson stores which measurements justified it and which gauge took them. When a calibration lab reports a gauge out of tolerance, the system recomputes each affected measurement's pass/fail verdict using the gauge's as-found error and uncertainty, then demotes only the lessons whose evidence no longer holds. The agent's next plan changes from "apply the lesson" to "verify on an independent instrument first", and a review list shows past decisions that relied on the demoted lesson.

One-line pitch: *Generic retraction demotes everything downstream of the gauge. Metrologic recomputes the verdicts, so it demotes only what lost its evidence.*

---

## 2. Stack and environment

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, uvicorn, PyMongo (sync driver), pydantic v2, pytest |
| LLM | Anthropic SDK, model `claude-sonnet-5-5`, tool calling |
| Embeddings | Voyage AI, 1024 dimensions (**VERIFY**: model name `voyage-3-large` returns 1024 dims by default; set `EMBED_MODEL` in `.env`) |
| Database | MongoDB Atlas (M10 if credits allow, else M0/Flex) plus Atlas Local in Docker for offline work |
| Frontend | Next.js (App Router), TypeScript, Tailwind, Cytoscape.js |
| Not used | LangGraph, LangChain. A plain tool-calling loop is enough. |

`.env.example` (commit this, never commit `.env`):

```
MONGODB_URI=mongodb+srv://<user>:<pass>@<cluster>/?retryWrites=true&w=majority
MONGODB_DB=metrologic
ANTHROPIC_API_KEY=
VOYAGE_API_KEY=
LLM_MODEL=claude-sonnet-5-5
EMBED_MODEL=voyage-3-large
CACHE_DIR=.cache
OFFLINE=0            # 1 = use disk caches only, never call LLM/Voyage
WORKSPACE=plant-1
```

Atlas Local for offline work:

```
docker run -d --name metrologic-mongo -p 27017:27017 mongodb/mongodb-atlas-local
# MONGODB_URI=mongodb://localhost:27017/?directConnection=true
```

Makefile targets to create: `make up` (docker), `make seed`, `make api` (`uvicorn app.main:app --reload --port 8000` from `backend/`), `make test` (`pytest -q`), `make web` (`npm run dev` in `frontend/`).

CORS: allow `http://localhost:3000`.

---

## 3. Repo layout

```
metrologic/
  backend/
    app/
      main.py            # FastAPI app, lifespan starts the two watchers
      config.py          # env loading
      db.py              # collections, indexes, pre-images (idempotent bootstrap)
      models.py          # Pydantic models = the data contract (frozen after M1)
      events.py          # thread-safe event bus + log_event()
      cache.py           # disk cache keyed by input hash (LLM and Voyage)
      agent/
        llm.py           # Claude calls (draft_lessons, explain_plan)
        ingest.py        # POST /ncr
        recommend.py     # POST /recommend
        prompts/         # prompt text files
      memory/
        writer.py        # write_lesson, corroborate
        retrieval.py     # $vectorSearch
        ranking.py       # scoring + ranking_trace
      validity/
        metrology.py     # recompute_verdict
        lattice.py       # support-set status, lesson state
        cascade.py       # run_cascade
      streams/
        gauge_watcher.py # change stream on gauges
        memory_watcher.py# change stream on memories (pre-images)
        sse.py           # GET /events
    seed/
      scenario.yaml      # the demo scenario (Section 9)
      generate.py        # filler data
      reset.py
      fixtures/          # cached LLM/Voyage outputs, TTL event rehearsal log
    tests/
  frontend/              # Next.js app, fixtures/ for offline UI work
  docs/
    DECISIONS.md  PROGRESS.md  demo-script.md  slides/
  Makefile  .env.example
```

Ownership if you run three agents in parallel: **Track A** = `db.py, events.py, cache.py, memory/, agent/, main.py, streams/memory_watcher.py, streams/sse.py`. **Track B** = `validity/, streams/gauge_watcher.py, seed/, tests/`. **Track C** = `frontend/, docs/`. The only shared file is `models.py`.

---

## 4. Milestone 0 spike: confirm the database tier (do this first)

Three demo moments depend on features that may behave differently on free tiers. Test them before writing anything else and record results in `docs/PROGRESS.md`.

Spike script `backend/spike.py`:

1. Create collection `spike`. Enable pre-images:
   `db.command({"collMod": "spike", "changeStreamPreAndPostImages": {"enabled": True}})`
2. Create a TTL index: `db.spike.create_index("expire_at", expireAfterSeconds=0)`.
3. Open a change stream: `db.spike.watch(full_document_before_change="whenAvailable")` in a thread.
4. Insert `{"_id": "t1", "expire_at": now + 30s}` (must be a BSON date, a Python `datetime`).
5. Wait up to 120 seconds. **Expected:** a `delete` event arrives, with `fullDocumentBeforeChange` populated. (TTL monitor runs about every 60 s, so deletion happens 30 to 90 s after insert. **VERIFY** delete events from TTL appear on your tier.)
6. Create a small vector search index with `SearchIndexModel(..., type="vectorSearch")`, insert a vector, run `$vectorSearch`. **VERIFY** index-ready latency (can take 30 to 60 s).
7. Test an update on a field and confirm an `update` event with `updateDescription.updatedFields` arrives.

Fallbacks if a check fails (decide now, not at demo time):

| Failed check | Fallback |
|---|---|
| `collMod` pre-images not allowed | Keep prior state in `history[]` and `audit_log`; the UI never needs the before-image |
| TTL delete event does not arrive | Show the rehearsed event from `seed/fixtures/ttl_delete_event.json` via a "Replay TTL event" button |
| Change stream unavailable | `POST /calibration?direct=true` runs the cascade inline |
| Vector search unavailable on tier | Use Atlas Local for the demo laptop |

**Acceptance:** `PROGRESS.md` lists pass/fail for each of the seven checks.

---

## 5. Data contract (final, v1)

Fields marked ★ are additions to the original brief. Freeze these as Pydantic models in `models.py` and export sample JSON to `frontend/fixtures/`.

IDs are short strings: measurements `M1`..; lessons `L1`..; failed attempts `F1`..; decisions `D1`..; background lessons `B1`... Gauge IDs are names such as `BG-07`.

### 5.1 `memories`

```json
{
  "_id": "L2",
  "workspace": "plant-1",
  "owner": "role:process-engineer",
  "type": "lesson",
  "title": "Raise coolant concentration for Inconel 718 finish boring",
  "content": "Chatter on Inconel 718 bores cleared when coolant concentration rose from 8% to 10%.",
  "action": "Raise coolant concentration to 10% before finish boring Inconel 718 bores",
  "scope": {"material": "Inconel 718", "process": "finish boring", "machine": "VF-4",
            "feature_class": "bore", "tolerance_band": "H7"},
  "source": {"ncr_id": "NCR-0412", "author_role": "manufacturing-engineer", "session_id": "s-001"},
  "support_sets": [["M9", "M10", "M11", "M12", "M13"]],
  "derived_from": ["M9", "M10", "M11", "M12", "M13"],
  "supports": [],
  "used_by": [],
  "validity_state": "PROVISIONAL",
  "mw_success": 0,
  "mw_fail": 0,
  "embedding": [ "... 1024 floats ..." ],
  "created_at": "2026-10-31T09:00:00Z",
  "valid_from": "2026-10-31T09:00:00Z",
  "invalid_at": null,
  "expire_at": "2026-11-30T09:00:00Z",
  "version": 1,
  "history": [
    {"ts": "2026-10-31T09:00:00Z", "event": "created", "from_state": null,
     "to_state": "PROVISIONAL", "cause": "ingest NCR-0412", "event_id": null, "note": ""}
  ]
}
```

- `type` is one of `episode | lesson | failed_attempt | decision_note | constraint | feedback`. The demo uses `lesson` and `failed_attempt`.
- `validity_state` is one of `ACTIVE | PROVISIONAL | NEEDS_VERIFICATION | HISTORICAL_ONLY | SUPERSEDED`.
- ★ `title` and `action` (lesson format: title, description, actionable step). ★ `owner`.
- `support_sets` is a list of lists of IDs. Each inner list is the evidence from **one independent instrument**. Members starting with `M` are measurement IDs. Members starting with `L`, `F` or `B` are memory IDs (a lesson built on another lesson; used by the lattice for transitive demotion).
- `derived_from` is the flat union of the measurement IDs in `support_sets` (used for fast lookup).
- `supports` lists IDs of memories that depend on this one (outgoing edges, used by `$graphLookup`).
- `used_by` is informational (decision IDs, `$addToSet` when a decision is persisted). The cascade uses `decisions.lessons_used`, not this field.
- `expire_at` is set on PROVISIONAL memories (30 days) and unset on corroboration. Must be a BSON date.

### 5.2 `measurements`

```json
{
  "_id": "M3", "gauge_id": "BG-07", "part_serial": "SN-2204",
  "value_mm": 32.003, "nominal_mm": 32.000, "tol_lo_mm": 32.000, "tol_hi_mm": 32.025,
  "u_mm": 0.002, "timestamp": "2026-09-14T09:30:00Z",
  "feature": "Ø32H7 bore",
  "verdict": "pass",
  "current_verdict": "pass",
  "verdict_history": []
}
```

- `verdict` is the **recorded** verdict and is never overwritten.
- ★ `current_verdict` starts equal to `verdict`; the cascade updates it.
- `verdict_history` entries: `{"event_id", "old", "new", "e_mm", "u_mm", "ts"}`.

### 5.3 `gauges`

```json
{"_id": "BG-07", "type": "bore_gauge", "cal_status": "OK",
 "last_good_cal": "2026-08-01T00:00:00Z",
 "as_found_error_mm": null, "as_found_u_mm": null,
 "event_id": null, "event_time": null}
```

After a calibration event: `cal_status = "OUT_OF_TOLERANCE"`, `as_found_error_mm = 0.006`, `as_found_u_mm = 0.002`, `event_id = <uuid>`, `event_time = <datetime>`.

### 5.4 `decisions`

```json
{"_id": "D1", "query": "...", "scope": {}, "plan_steps": [], "lessons_used": ["L2"],
 "ranking_trace": [], "part_serials": ["SN-2208", "SN-2211"],
 "created_at": "...", "review_flag": false, "review_reason": null}
```

### 5.5 `audit_log`

```json
{"ts": "...", "event": "lesson_state_changed", "memory_id": "L2",
 "from_state": "PROVISIONAL", "to_state": "NEEDS_VERIFICATION",
 "cause": "BG-07 out of tolerance, event <event_id>", "event_id": "<uuid>"}
```

Event names: `calibration_posted, cascade_started, measurement_recomputed, lesson_state_changed, lesson_saved_by_independent_support, decision_flagged, ttl_deleted, memory_deleted, cascade_finished`.

### 5.6 ★ `stream_state`

`{"_id": "gauge_watcher", "resume_token": {...}}`. Stores the change stream resume token so a restart does not miss the calibration event.

### 5.7 Indexes (all created idempotently by `db.py`)

| Collection | Index |
|---|---|
| `memories` | Atlas Vector Search index `memories_vec` (below) |
| `memories` | TTL: `create_index("expire_at", expireAfterSeconds=0)` |
| `memories` | Pre-images: `collMod` with `changeStreamPreAndPostImages: {enabled: true}` |
| `measurements` | `{gauge_id: 1, timestamp: 1}` |
| `decisions` | `{lessons_used: 1}` |
| `audit_log` | `{ts: 1}` |

Vector index definition:

```python
SearchIndexModel(
  name="memories_vec", type="vectorSearch",
  definition={"fields": [
    {"type": "vector", "path": "embedding", "numDimensions": 1024, "similarity": "cosine"},
    {"type": "filter", "path": "workspace"},
    {"type": "filter", "path": "type"},
    {"type": "filter", "path": "validity_state"},
    {"type": "filter", "path": "scope.material"},
    {"type": "filter", "path": "scope.process"}]})
```

`db.py` must check whether the index already exists (`list_search_indexes`) before creating it, and expose `wait_for_index_ready()`.

---

## 6. Validity engine (the research contribution)

All code in `backend/app/validity/`. Pure functions where possible, fully unit-tested.

### 6.1 Suspect window

A calibration event on gauge `G` at time `T` selects measurements where `gauge_id == G` and `gauge.last_good_cal < timestamp <= T`. Measurements outside this window are untouched. (The seed includes one BG-07 measurement dated before `last_good_cal` that would flip if wrongly included; a test asserts it is untouched.)

### 6.2 Verdict recomputation (`metrology.py`)

Sign convention: `e` = as-found error = reading minus true value, so `true = reading - e`. A gauge that "reads high by 0.006" has `e = +0.006`.

```
x' = x - e
v(m) = pass            if [x' - U, x' + U] is inside   [lo, hi]
       fail            if [x' - U, x' + U] is disjoint from [lo, hi]
       indeterminate   otherwise
```

Use `Decimal` (built from `str(value)`) to avoid floating-point errors at boundaries:

```python
from decimal import Decimal as D

def recompute_verdict(value, lo, hi, e, U) -> str:
    x = D(str(value)) - D(str(e))
    u, lo, hi = D(str(U)), D(str(lo)), D(str(hi))
    low, high = x - u, x + u
    if low >= lo and high <= hi:
        return "pass"
    if high < lo or low > hi:
        return "fail"
    return "indeterminate"
```

Boundaries are inclusive for "pass" (interval touching the limit from inside is pass) and an interval that merely touches a limit from outside is `indeterminate` (not `fail`).

**Required unit tests** (`tests/test_metrology.py`, table-driven). Ø32H7: `lo=32.000, hi=32.025`, `e=0.006, U=0.002`:

| value | corrected interval | expected |
|---|---|---|
| 32.012 | 32.004 to 32.008 | pass |
| 32.007 | 31.999 to 32.003 | indeterminate |
| 32.003 | 31.995 to 31.999 | fail |
| 32.008 | 32.000 to 32.004 | pass (low == lo) |
| 32.0079 | 31.9999 to 32.0039 | indeterminate |
| 32.004 | 31.996 to 32.000 | indeterminate (high == lo, touches) |
| 32.0039 | 31.9959 to 31.9999 | fail |
| 32.040 | 32.032 to 32.036 | fail (above hi, unchanged) |
| 32.024 | 32.016 to 32.020 | pass |

Also test `e = -0.006` (gauge reads low): value 32.002 gives interval 32.006 to 32.010, expected pass.

### 6.3 Support-set status (`lattice.py`)

A support set is the evidence from one independent instrument. For a set, look at each member:

- A measurement member: **flipped** if `verdict` and `current_verdict` are different and both in `{pass, fail}`; **weakened** if `current_verdict == "indeterminate"` and `verdict != "indeterminate"`; otherwise **unchanged**.
- A memory member: its current state ACTIVE or PROVISIONAL counts as unchanged; NEEDS_VERIFICATION counts as weakened; HISTORICAL_ONLY or SUPERSEDED counts as flipped.

Set status:

- `broken` if any member is flipped
- `weakened` if no member is flipped and any is weakened
- `holds` otherwise

### 6.4 Lesson state (`lattice.py`)

```python
SEVERITY = {"ACTIVE": 0, "PROVISIONAL": 1, "NEEDS_VERIFICATION": 2,
            "HISTORICAL_ONLY": 3, "SUPERSEDED": 4}

def lesson_state(old_state, set_statuses):
    if not set_statuses:
        return old_state
    if "holds" in set_statuses:      computed = "ACTIVE"
    elif "weakened" in set_statuses: computed = "NEEDS_VERIFICATION"
    else:                            computed = "HISTORICAL_ONLY"
    # a cascade never promotes: keep the more severe of old and computed
    return max(old_state, computed, key=SEVERITY.get)
```

Consequences to test:

- ACTIVE lesson, one set broken, another set holds: stays ACTIVE. Log `lesson_saved_by_independent_support` naming the surviving instrument.
- PROVISIONAL lesson, only set weakened: becomes NEEDS_VERIFICATION.
- PROVISIONAL lesson, all sets hold: stays PROVISIONAL (cascade never promotes).
- NEEDS_VERIFICATION lesson hit by a second event where all sets hold: stays NEEDS_VERIFICATION.
- All sets broken: HISTORICAL_ONLY.
- A lesson with a memory member that gets demoted inherits the weakened/broken status (test with a synthetic L3 built on L2; this is not in the demo seed).

Promotion happens only in `corroborate()` (Section 7.4).

### 6.5 Cascade (`cascade.py`)

```python
def run_cascade(db, gauge_id: str, event_id: str, e: float, U: float, event_time) -> CascadeResult
```

Steps:

1. If `audit_log` already has `cascade_finished` with this `event_id`, return the stored result (idempotency shortcut). Otherwise continue; all steps below are also individually idempotent.
2. `log_event("cascade_started")`.
3. Select the suspect window (6.1).
4. For each measurement: `new = recompute_verdict(value_mm, tol_lo_mm, tol_hi_mm, e, U)`. If `verdict_history` already has an entry with this `event_id`, skip. Otherwise append `{event_id, old: current_verdict, new, e_mm, u_mm, ts}`, set `current_verdict = new`. If `new != old`, `log_event("measurement_recomputed", ...)`.
5. Find affected memories: `memories.find({"derived_from": {"$in": affected_ids}, "type": {"$in": ["lesson", "failed_attempt"]}})`.
6. For each, compute set statuses using current measurement verdicts, then `lesson_state(...)`. If the state changed: update `validity_state`, set `invalid_at = now` for HISTORICAL_ONLY, bump `version`, append to `history[]`, `log_event("lesson_state_changed")`. If the state is ACTIVE but at least one set was not `holds`, append a history entry with note `"saved by independent support on <GAUGE>"` and `log_event("lesson_saved_by_independent_support")`.
7. **Transitive step:** for each demoted memory `D`, run `$graphLookup` over `supports`:
   ```python
   db.memories.aggregate([
     {"$match": {"_id": D}},
     {"$graphLookup": {"from": "memories", "startWith": "$supports",
        "connectFromField": "supports", "connectToField": "_id",
        "maxDepth": 3, "as": "dependents"}}])
   ```
   Re-evaluate each dependent with its own support sets (step 6). Repeat until no state changes (maximum 4 iterations).
8. Flag decisions: for every demoted memory, `decisions.update_many({"lessons_used": id, "review_flag": {"$ne": True}}, {"$set": {"review_flag": True, "review_reason": f"Used {id}, now {state} after {gauge_id} calibration event {event_id}"}})`; `log_event("decision_flagged")` for each.
9. `log_event("cascade_finished", payload=summary)` with `measurements_recomputed`, `verdict_changes`, `lesson_changes`, `decisions_flagged`.

**Idempotency test:** call `run_cascade` twice with the same arguments. Assert the second call writes zero new `audit_log` rows, zero new `verdict_history` entries, zero new `history[]` entries, and changes no state.

### 6.6 Illustrative-rule disclaimer

The guard-band rule above is a simplified decision rule, not a GUM uncertainty budget. State this on one slide and in the README.

---

## 7. Memory and agent layer

### 7.1 `events.py` (event bus)

- `log_event(db, event, **fields)` inserts into `audit_log` and publishes the same dict to the bus.
- The bus is thread-safe: each SSE connection owns an `asyncio.Queue`; publishers (running in watcher threads) call `loop.call_soon_threadsafe(queue.put_nowait, item)`. Keep a bounded in-memory replay buffer of the last 200 events so a newly connected UI can catch up (`GET /events?replay=1`).

### 7.2 `writer.py`

```python
def write_lesson(db, *, type, title, content, action, scope, measurement_ids,
                 source, workspace=None, memory_id=None) -> dict
```

1. Raise `ProvenanceError` if `measurement_ids` is empty or any ID is not in `measurements`.
2. Group IDs by the measurement's `gauge_id` into `support_sets` (sorted by gauge ID); set `derived_from`.
3. Embed `f"{title}. {content} Action: {action}"` with `input_type="document"`.
4. Insert with `validity_state="PROVISIONAL"`, `expire_at = now + 30 days`, `mw_success = mw_fail = 0`, `version = 1`, `history = [created]`.
5. `_id`: use `memory_id` if given, otherwise prefix (`L`, `F`, `B`) plus the next integer for that prefix.

Tests: refuses empty list; refuses unknown ID; groups two instruments into two sets; sets a 30-day `expire_at` (as a `datetime`).

### 7.3 `llm.py` and `ingest.py` (`POST /ncr`)

Request body:

```json
{
  "ncr_id": "NCR-0412", "workspace": "plant-1",
  "summary": "Ti-6Al-4V housing, Ø32H7 bore tapered after finish boring. Separate chatter on Inconel 718 sleeve.",
  "trials": [
    {"id": "A", "description": "Reduce feed only", "outcome": "fail", "measurement_ids": ["M14","M15","M16"]},
    {"id": "B", "description": "Spring pass plus lower radial engagement", "outcome": "pass", "measurement_ids": ["M1","M2","M3","M4","M5"]},
    {"id": "C", "description": "Coolant concentration 8% to 10% on Inconel 718", "outcome": "pass", "measurement_ids": ["M9","M10","M11","M12","M13"]}
  ],
  "measurements": [ { "...": "full measurement documents, see 5.2" } ]
}
```

Flow:

1. Insert the measurements (upsert by `_id`; `current_verdict = verdict`, `verdict_history = []`).
2. Call Claude with a single forced tool `draft_lessons` (`tool_choice={"type": "tool", "name": "draft_lessons"}`). Tool schema: `lessons[]` of `{kind: "lesson"|"failed_attempt", title, content, action, scope{material, process, machine, feature_class, tolerance_band}, measurement_ids[]}`. The prompt must say: cite only measurement IDs from the input; failed trials become `failed_attempt`; successful trials become `lesson`.
3. **Validate**: every returned ID must be in the input list; each item must cite at least one ID. On failure retry once, then fall back to `seed/fixtures/ncr_0412_lessons.json`. Never write an unvalidated item.
4. Call `write_lesson` for each. Return the created memory IDs, states and `support_sets`.

Expected result for NCR-0412: `L1` (Fix B, evidence M1 to M5), `L2` (coolant, evidence M9 to M13), `F1` (Fix A failed, evidence M14 to M16). All PROVISIONAL. The IDs come out as L1, L2, F1 only if the LLM response is cached and returned in this order; a test must assert it.

### 7.4 Corroboration (`POST /lessons/{id}/corroborate`)

Body: `{"job_id": "NCR-0419", "measurements": [ ...full docs or [] ], "measurement_ids": ["M6","M7","M8"]}`.

1. Insert any provided measurements. Validate all IDs exist.
2. Merge into `support_sets` by gauge: IDs from a gauge that already has a set join that set (same instrument is not independent); IDs from a new gauge create a new set.
3. Recompute the lesson state from all sets (Section 6.3 and 6.4 logic but allowing promotion): if any set `holds`, set `ACTIVE`, `$unset expire_at`, append history `corroborated by <gauge> (job <job_id>)`. Otherwise leave state unchanged.
4. Return the updated memory.

For the demo: corroborating L1 with M6 to M8 on CMM-02 yields `support_sets = [[M1..M5] (BG-07), [M6,M7,M8] (CMM-02)]` and state ACTIVE.

### 7.5 Retrieval and ranking

`retrieval.py`:

```python
db.memories.aggregate([
  {"$vectorSearch": {"index": "memories_vec", "path": "embedding",
     "queryVector": qvec, "numCandidates": 100, "limit": 10,
     "filter": {"workspace": ws,
                "type": {"$in": ["lesson", "failed_attempt"]},
                "validity_state": {"$in": ["ACTIVE", "PROVISIONAL", "NEEDS_VERIFICATION"]}}}},
  {"$addFields": {"vector_score": {"$meta": "vectorSearchScore"}}}])
```

- `history=true` mode removes the `validity_state` filter.
- Material and process are **not** hard filters (the Stage 2 query is Inconel 718 and must still retrieve the Ti-6Al-4V lesson L1). They feed `scope_match` in ranking. An optional `scope_filter=true` request flag turns them into filters.
- Query embedding uses `input_type="query"`.

`ranking.py` (weights are starting values, tune on seed data):

```
final = vector_score + state_bias + 0.2*(MW - 0.5) + 0.05*recency + 0.1*scope_match
MW = (mw_success + 1) / (mw_success + mw_fail + 2)
recency = exp(-age_days / 90)
scope_match = (matching scope fields) / (scope fields supplied in the query)
```

| State | Bias | Retrieved by default |
|---|---|---|
| ACTIVE | +0.12 | yes |
| PROVISIONAL | +0.04 | yes |
| NEEDS_VERIFICATION | -0.10 | yes, with a verify step |
| HISTORICAL_ONLY / SUPERSEDED | -0.22 | no (history queries only) |

PROVISIONAL takes +0.04 because the PACMI-style lattice has no PROVISIONAL slot.

Every term is stored in `ranking_trace` per memory: `{memory_id, vector_score, state, state_bias, mw, mw_term, recency, recency_term, scope_match, scope_term, final}`. The UI shows one column per term.

### 7.6 `cache.py`

Disk cache keyed by `sha256(model + canonical JSON input)` in `CACHE_DIR`. Used by `llm.py` and the Voyage wrapper. With `OFFLINE=1`, a cache miss raises a clear error. Run the full demo once online to fill the cache, then commit `seed/fixtures/` copies so any laptop can replay it. Seeded embeddings are precomputed and stored in `seed/fixtures/embeddings.json` so `reset` stays under 10 seconds.

### 7.7 `recommend.py` (`POST /recommend`)

Request: `{"query": "...", "scope": {...}, "workspace": "plant-1", "persist": true, "history": false}`.

Plan steps are built by **code**, then the LLM rewrites wording only:

1. Retrieve and rank (7.5), keep the top 5.
2. For each retrieved memory, in rank order:
   - `lesson` with state ACTIVE or PROVISIONAL: step `{kind: "apply", text: "Apply: <action>", lesson_ids: [id]}`.
   - `lesson` with state NEEDS_VERIFICATION: step `{kind: "verify", text: "Verify on <instrument> before adopting: <action>", lesson_ids: [id], verify_instrument: <gauge>}`. `pick_verify_instrument(lesson)`: choose a gauge with `cal_status == "OK"` that is not in the lesson's weakened or broken sets; prefer type `CMM`; break ties alphabetically. For the seed this returns `CMM-02`.
   - `failed_attempt`: step `{kind: "avoid", text: "Do not: <action>. Failed on a prior job (<id>)", lesson_ids: [id]}`.
3. Ask Claude to reword each step's `text` for readability. The LLM receives the steps as JSON and must return the same number of steps, with the same `kind` and `lesson_ids`. Reject and fall back to the code-built text on any mismatch. In Stage 3 also ask for a one-sentence "why the plan changed", grounded in the memory `history[]`.
4. If `persist` is true: insert a `decisions` document (`lessons_used` = the lesson and failed-attempt IDs in the plan; `part_serials` from the scope if provided; `$addToSet used_by` on each memory).
5. Return `{decision_id, plan_steps, lessons_used, ranking_trace, explanation}`.

### 7.8 Stretch (build only after Milestone 7)

- `POST /decisions/{id}/outcome` updates `mw_success` / `mw_fail` for the lessons used.
- `contradicts` edges between opposite lessons in the same scope.
- 20-scenario drift benchmark (Section 12).

---

## 8. API reference (all JSON)

| Method and path | Purpose | Notes |
|---|---|---|
| `POST /ncr` | Ingest NCR, trials, measurements; draft memories | Section 7.3 |
| `POST /lessons/{id}/corroborate` | Add an independent support set, promote | Section 7.4 |
| `POST /recommend` | Retrieve, rank, build plan, write decision | Section 7.7 |
| `GET /memories/{id}` | Memory, evidence chain, state history | Evidence chain = each member measurement with `verdict`, `current_verdict`, `gauge_id`, gauge `cal_status` |
| `GET /graph` | Cytoscape elements | Section 8.1 |
| `POST /calibration` | Write an as-found result to `gauges` | Body `{"gauge_id","as_found_error_mm","as_found_u_mm","result":"OUT_OF_TOLERANCE"}`; generates `event_id`; the gauge watcher does the rest. `?direct=true` runs the cascade inline. |
| `GET /decisions/review` | Decisions with `review_flag == true` | Includes `part_serials` and `review_reason` |
| `GET /events` | Server-Sent Events | `?replay=1` replays the last 200 events |
| `POST /demo/reset` | Drop and reload seed data | Must finish in under 10 s |
| `POST /demo/stage/{n}` | Replay a stage's inputs | `n` in 1, 2, 3; see Section 10 |

### 8.1 `GET /graph`

Cytoscape-format elements, kept under about 40 nodes:

- One compound **parent** node per gauge (`data.id = "g:BG-07"`, `data.kind = "gauge"`, `data.status`).
- Measurement **child** nodes (`data.parent = "g:BG-07"`) only for measurements referenced by demo lessons (L1, L2, F1). Filler measurements collapse into one node per gauge (`data.kind = "measurement_group"`, label with the count).
- Lesson nodes (`data.kind = "lesson"`, `data.state`), decision nodes (`data.kind = "decision"`, `data.flagged`).
- Edges: measurement (or group) to lesson (one edge per support set member group), lesson to decision (`lessons_used`).
- Background lessons are included with `data.background = true` so the UI can hide them behind a toggle.

### 8.2 Watchers

`streams/gauge_watcher.py`:

```python
pipeline = [{"$match": {"operationType": "update",
            "updateDescription.updatedFields.cal_status": {"$exists": True}}}]
with db.gauges.watch(pipeline, full_document="updateLookup", resume_after=saved_token) as stream:
    for change in stream:
        gauge = change["fullDocument"]
        if gauge["cal_status"] == "OUT_OF_TOLERANCE":
            run_cascade(db, gauge["_id"], gauge["event_id"], gauge["as_found_error_mm"],
                        gauge["as_found_u_mm"], gauge["event_time"])
        save_resume_token(stream.resume_token)   # after successful handling
```

Run in a daemon thread started from the FastAPI lifespan. Wrap in a retry loop with backoff; on error log and resume from the saved token.

`streams/memory_watcher.py`:

```python
db.memories.watch(full_document="updateLookup", full_document_before_change="whenAvailable")
```

- `update` where `validity_state` changed: publish `memory_changed` (UI recolors the node).
- `delete`: write `audit_log` `ttl_deleted` (or `memory_deleted`) using the before-image: `cause = "ttl_expiry"` when `before.expire_at <= now + 1 s`, otherwise `"deleted"`. Publish the same.
- Duplicate UI events (a cascade `lesson_state_changed` plus a `memory_changed`) are harmless: the UI patches nodes idempotently.

---

## 9. Seed data and the demo scenario

`seed/scenario.yaml` is the single source of truth. Expected outcomes are written **first**; they become test assertions.

### 9.1 Gauges (6)

`BG-07` (bore gauge), `BG-03` (bore gauge), `CMM-02`, `CMM-05` (CMM), `MIC-11` (micrometer), `HG-04` (height gauge). All `cal_status = OK`; `BG-07.last_good_cal = 2026-08-01`.

### 9.2 Measurements for the scenario

BG-07 event: `e = +0.006`, `U = 0.002`.

| ID | Gauge | Used by | Feature (lo to hi) | Recorded value | Recorded verdict | After correction |
|---|---|---|---|---|---|---|
| M1 | BG-07 | L1 | Ø32H7 (32.000 to 32.025) | 32.012 | pass | pass |
| M2 | BG-07 | L1 | same | 32.007 | pass | indeterminate |
| M3 | BG-07 | L1 | same | 32.003 | pass | **fail (flipped)** |
| M4 | BG-07 | L1 | same | 32.015 | pass | pass |
| M5 | BG-07 | L1 | same | 32.010 | pass | pass |
| M6 to M8 | CMM-02 | L1 (corroboration) | same | 32.011, 32.014, 32.009 | pass | pass (not in window) |
| M9 | BG-07 | L2 | Ø28H7 (28.000 to 28.021) | 28.010 | pass | pass |
| M10 | BG-07 | L2 | same | 28.007 | pass | indeterminate |
| M11 | BG-07 | L2 | same | 28.011 | pass | pass |
| M12 | BG-07 | L2 | same | 28.006 | pass | indeterminate |
| M13 | BG-07 | L2 | same | 28.012 | pass | pass |
| M14 to M16 | BG-07 | F1 | Ø32H7 | 32.034, 32.038, 32.041 | fail | fail (unchanged) |
| M-old | BG-07 | none | Ø32H7 | 32.003, dated 2026-07-20 | pass | untouched (before `last_good_cal`) |

Check the corrections: M10 `28.007 - 0.006 = 28.001`, interval 27.999 to 28.003, indeterminate. M12 `28.006 - 0.006 = 28.000`, interval 27.998 to 28.002, indeterminate. M9 interval 28.002 to 28.006, pass. No L2 measurement flips (a flip needs value below 28.004).

All BG-07 measurement timestamps are between 2026-08-02 and 2026-10-30. Give each a `part_serial` (for example `SN-2201` onward).

### 9.3 Filler

`generate.py` creates about 190 filler measurements far from tolerance limits (mid-band values) across all gauges (including about 40 on BG-07 inside the window, referenced by no lesson) and 13 background lessons (`B1` to `B13`, ACTIVE, with `support_sets` on BG-03, MIC-11, HG-04, CMM-05 and different scopes). Use a fixed random seed. Embeddings for background lessons come from `fixtures/embeddings.json`.

### 9.4 Past decisions

`D1` and `D2` are seeded with `lessons_used = ["L2"]`, plausible `plan_steps`, and `part_serials` `["SN-2208"]` and `["SN-2211"]`. They reference `L2` before Stage 1 creates it; this is intentional demo scaffolding (the flagging query uses `decisions.lessons_used`, not a join).

### 9.5 Expected outcome of the Stage 3 cascade (becomes the integration test)

| Item | Before | After |
|---|---|---|
| L1 | ACTIVE (after corroboration) | **ACTIVE**, history note "saved by independent support on CMM-02" |
| L2 | PROVISIONAL | **NEEDS_VERIFICATION** |
| F1 | PROVISIONAL | PROVISIONAL (evidence still holds) |
| B1 to B13 | ACTIVE | unchanged |
| M1, M4, M5, M9, M11, M13 | pass | pass (unchanged) |
| M2, M10, M12 | pass | indeterminate |
| M3 | pass | fail |
| M14 to M16 | fail | fail |
| M-old | pass | untouched |
| Flagged decisions | none | D1, D2, and the Stage 2 decision (3 total) |

Note on the flagged count: the original plan says "two decisions flagged". The Stage 2 decision also used L2, so it is flagged too. Either accept three (and say "the plan I gave you two minutes ago is now flagged", which is a stronger moment), or call `POST /recommend` with `persist=false` in Stage 2 to keep exactly two. Pick one in `DECISIONS.md` and make the test match.

---

## 10. Demo stages (drives `/demo/stage/{n}` and the script)

| Stage and step | Endpoint | What happens |
|---|---|---|
| 1a | `POST /demo/stage/1?step=a` | `POST /ncr` with NCR-0412 (cached LLM). L1, L2, F1 appear PROVISIONAL (grey) with edges to their measurements on BG-07. |
| 1b | `POST /demo/stage/1?step=b` | `POST /lessons/L1/corroborate` with CMM-02 (M6 to M8). L1 turns ACTIVE (green): "Two instruments now support this lesson." L2 stays grey, BG-07 only. |
| 2 | `POST /demo/stage/2` | `POST /recommend` for "Process plan for an Inconel 718 sleeve with a Ø28H7 bore". Scope: Inconel 718, finish boring, bore, H7. The plan applies L1 and L2 and avoids the feed-only fix citing F1. The inspector for L2 shows similarity, state bias, Memory Worth and the evidence chain. |
| 3-arm | `POST /demo/stage/3?step=arm` | Press at the end of Stage 2. Writes a PROVISIONAL memory `T1` ("abandoned trial") with `expire_at = now + 30 s`, evidence from a BG-03 measurement. The TTL monitor deletes it 30 to 90 s later. |
| 3 | `POST /demo/stage/3` | `POST /calibration` for BG-07, `+0.006 mm`, `U = 0.002 mm`. The cascade runs, L2 turns amber, L1 stays green, the review list fills, the re-asked plan shows the verify step, and the TTL delete appears in the feed. |

`/demo/reset` drops the five collections plus `stream_state`, then reloads: the six gauges, the filler measurements (including `M-old`, the BG-07 measurement dated before `last_good_cal`), the 13 background lessons, and decisions `D1` and `D2`. It clears the in-memory event buffer.

Reset does **not** load M1 to M16. Those scenario measurements are inserted during the demo (M1 to M5, M9 to M16 by Stage 1a `POST /ncr`; M6 to M8 by Stage 1b corroboration), so the UI can show them arriving.

Reset must be repeatable: run reset, Stage 1, 2, 3 three times in a row with identical results (compare the ranking traces and final states).

---

## 11. Frontend spec (Track C)

Build on fixtures first. `NEXT_PUBLIC_USE_FIXTURES=1` loads `frontend/fixtures/*.json`; `NEXT_PUBLIC_API_BASE=http://localhost:8000` uses the live API. The UI must never wait for the backend.

Fixtures to create (exported from Pydantic sample JSON in Milestone 1): `graph.stage1.json, graph.stage2.json, graph.stage3.json, recommend.stage2.json, recommend.stage3.json, memory.L1.json, memory.L2.json, review.json, events.stage1.jsonl, events.stage3.jsonl`.

Layout: three panels plus a demo control bar.

1. **Recommendation panel**: query box, plan steps. Each step shows a chip per lesson it used, coloured by state; `verify` steps are highlighted; `avoid` steps show the failed-attempt chip.
2. **Memory inspector**: raw document JSON, ranking trace table (one column per score term), state history timeline, evidence chain (each measurement with recorded vs current verdict).
3. **Provenance graph (Cytoscape)**: gauge (compound) to measurements to lesson to decision. Node colours: ACTIVE `#16a34a` (green), PROVISIONAL `#9ca3af` (grey), NEEDS_VERIFICATION `#f59e0b` (amber), HISTORICAL_ONLY `#dc2626` (red). Flipped measurements show old and new verdict labels. Hide background lessons behind a toggle.
4. **Event feed**: each `audit_log` event including TTL deletions, newest on top.
5. **Control bar**: Reset, Stage 1a, Stage 1b, Stage 2, Arm TTL, "Post calibration: BG-07 +6 µm", Re-ask, Replay TTL event (fallback).

Behaviour:

- SSE client with auto-reconnect and `?replay=1`.
- On `calibration_posted`, pulse the gauge node; on each `measurement_recomputed`, pulse then recolour the measurement node; on `lesson_state_changed` or `memory_changed`, animate the lesson node to its new colour (use `cy.animate`, 300 ms). Patching is idempotent.
- **Plan diff**: show the Stage 2 plan and the re-asked plan side by side, with the inserted verify step highlighted.
- **Review list panel**: flagged decisions with part serials and `review_reason`.
- State legend plus a one-line caption per stage on screen.
- Stage captions: 1 "Lessons carry provenance", 2 "Recall explains itself", 3 "Calibration out of tolerance (clause 7.1.5.2)".

---

## 12. Tests (Track B owns, everyone runs)

| File | What it proves |
|---|---|
| `test_metrology.py` | Table in Section 6.2, including boundaries and negative `e` |
| `test_lattice.py` | Lesson state cases in Section 6.4, including L1 saved by CMM-02, L2 demoted, all-broken case, no promotion by cascade, transitive case with synthetic L3 |
| `test_writer.py` | Provenance enforced; grouping by gauge; 30-day `expire_at` |
| `test_cascade.py` | Suspect window (M-old untouched); expected outcome table 9.5; idempotency; background lessons unchanged |
| `test_ranking.py` | Weights and bias table; MW formula; deterministic ordering on seed |
| `test_recommend.py` | Stage 2 plan contains `apply` steps for L1 and L2 and an `avoid` step for F1; after the cascade the L2 step becomes `verify` with `CMM-02`; LLM rewording that changes step count is rejected |
| `test_api.py` | Each endpoint with the cache in `OFFLINE=1` mode |

Integration tests need a real MongoDB (Atlas Local container). Do not use mock Mongo libraries; they do not support change streams or vector search. The cascade function is called directly in tests (no change stream needed).

**Optional benchmark (high value for the pitch):** a script that generates 20 calibration-drift scenarios with known ground truth, and compares (a) topology-only invalidation (demote everything downstream of the gauge) with (b) verdict recomputation. Report over-invalidation and under-invalidation counts, plus unnecessary verification steps. One slide.

---

## 13. Risks and fallbacks

| Risk | Likelihood | Fallback |
|---|---|---|
| Tier blocks pre-images | Medium | Keep prior state in `history[]` and `audit_log`; UI uses its own cache |
| TTL delete arrives late (monitor about every 60 s, primary only) | High | Arm the TTL document at the end of Stage 2; if it misses, press "Replay TTL event" |
| LLM cites wrong measurement IDs | Medium | Validate against the input list; fall back to seeded lessons |
| Conference Wi-Fi drops LLM or Atlas | Medium | `OFFLINE=1` with disk caches; Atlas Local on the demo laptop; backup video |
| Graph too crowded | Medium | Compound node per gauge; background lessons behind a toggle |
| Ranking puts the wrong lesson first | Low | Tune weights on seed data; verify step is inserted by code, not ranking |

Cut in this order if behind: drift benchmark, `contradicts` edges and conflict display, Memory Worth outcome endpoint (keep the seeded counters in the score), LLM explanation text (show state history instead), live TTL deletion (show the logged event), pre-image auditing.

---

## 14. Milestones with acceptance checks

Each milestone lists the tasks, the owner track, and a check that must pass before moving on.

### M0: Spike (Section 4)
Owner: A. **Check:** `PROGRESS.md` shows results for all seven spike checks and the chosen fallbacks.

### M1: Contracts and scaffolding
Owners: all. Tasks: repo layout; `config.py`; `models.py` with every model in Section 5; export sample JSON to `frontend/fixtures/`; `db.py` bootstrap (collections, TTL, pre-images, vector index, `wait_for_index_ready`); `Makefile`; `.env.example`.
**Check:** `python -c "from app.db import bootstrap; bootstrap()"` runs twice without error (idempotent); `make test` runs (even if empty); fixtures folder contains sample JSON.

### M2: Validity engine (pure code)
Owner: B. Tasks: `metrology.py`, `lattice.py`, test tables from Sections 6.2 and 6.4.
**Check:** `pytest tests/test_metrology.py tests/test_lattice.py -q` all green; no database needed.

### M3: Memory writer and seed data
Owners: A (writer, cache), B (seed). Tasks: `cache.py`, Voyage wrapper, `write_lesson`, `corroborate`, `scenario.yaml`, `generate.py`, `reset.py`.
**Check:** `POST /demo/reset` completes in under 10 s; `test_writer.py` green; a document in `memories` has a 1024-float `embedding` and a BSON-date `expire_at`.

### M4: Ingest and recall (Gate 1: Stage 1 works)
Owner: A. Tasks: `llm.py`, `ingest.py`, `retrieval.py`, `ranking.py`, `recommend.py`, `GET /memories/{id}`, `GET /graph`.
**Check:** `POST /ncr` writes L1, L2, F1 as PROVISIONAL with `support_sets`; corroboration moves L1 to ACTIVE; `POST /recommend` for the Stage 2 query returns a plan with L1, L2 (apply) and F1 (avoid) and a full `ranking_trace`; `GET /graph` returns under 40 nodes.

### M5: Cascade (Gate 2: cascade fires live)
Owner: B (cascade, gauge watcher), A (memory watcher, SSE). Tasks: `cascade.py`, `gauge_watcher.py`, `memory_watcher.py`, `sse.py`, `POST /calibration`, `GET /decisions/review`, `POST /demo/stage/{n}`.
**Check:** posting BG-07 `+0.006` demotes L2 only, L1 stays ACTIVE with the saved-by-CMM-02 note, decisions are flagged per Section 9.5, `test_cascade.py` (including idempotency) is green, and the SSE feed shows the events within 3 seconds. A restart of the API between event and handling does not lose the event (resume token test).

### M6: Behaviour change
Owner: A. Tasks: verify-step insertion by code, `pick_verify_instrument`, LLM rewording with validation, Stage 3 explanation.
**Check:** re-asking the Stage 2 query after the event returns a plan whose L2 step is `verify` with instrument `CMM-02`, and the L1 step is unchanged.

### M7: UI (Gate 3: feature freeze)
Owner: C (fixtures first, then live API). Tasks: Section 11.
**Check:** a full reset-to-Stage-3 run, twice in a row, with identical results and no manual page refresh; the TTL delete appears in the event feed (or the replay button works); plan diff and review list render.

### M8: Stretch and pitch
Owners: B (benchmark), C (slides), A (outcome endpoint). Tasks: drift benchmark; five slides (the 7.1.5.2 gap, the idea, architecture with each MongoDB feature labelled, the live demo, comparison with PACMI and Recant plus the benchmark result); backup video; `demo-script.md`.
**Check:** three full rehearsals identical; backup video recorded.

---

## 15. Demo script (4 minutes, one presenter plus one driver)

**Stage 1, learning with provenance (60 s).** Click Stage 1a: NCR-0412 (Ti-6Al-4V housing, Ø32H7 bore tapered after finish boring). F1 and L1 appear grey with edges to measurements on BG-07. Click Stage 1b: CMM-02 corroborates L1, which turns green. "Two instruments now support this lesson." Point out L2 (Inconel 718 coolant), supported only by BG-07.

**Stage 2, recall in a new session (60 s).** Ask for a process plan for an Inconel 718 sleeve with a Ø28H7 bore. The plan uses L1 and L2 and avoids the feed-only fix, citing F1. Open the inspector on L2: similarity, state bias, Memory Worth, evidence chain. Press Arm TTL.

**Stage 3, calibration out of tolerance (90 s).**
1. Click "Post calibration: BG-07 +6 µm". "This is the event clause 7.1.5.2 covers, and today it only reaches product."
2. The event feed shows the Change Stream firing; the BG-07 measurements recompute and some turn indeterminate.
3. L2 turns amber. L1 stays green; its history says "saved by independent support on CMM-02".
4. Open the review list: decisions that used L2, with part serials.
5. Re-ask the Stage 2 question. The plan diff highlights the new step: verify on CMM-02 before adopting the coolant change.
6. The abandoned-trial memory disappears and the feed logs the TTL delete.

**Close (30 s).** "Generic retraction demotes everything downstream of the gauge. Metrologic recomputes the verdicts, so it demotes only what lost its evidence." Show the benchmark slide if finished.

Likely judge questions:

- *How is this different from PACMI or Recant?* They propagate invalidation along graph edges. We recompute the measurement's verdict under the as-found error, so only verdicts that actually change propagate.
- *Why not delete the lesson?* Audit history and selective demotion; invalidated lessons stay as HISTORICAL_ONLY.
- *Is the uncertainty maths rigorous?* No. The guard-band rule is illustrative, not a GUM budget. A production system needs customer-agreed decision rules.

---

## 16. Decisions made where the original plan was ambiguous

Record these in `docs/DECISIONS.md` (change them if you disagree, but change tests too).

1. `support_sets` members may also be memory IDs, so the lattice handles lessons built on lessons.
2. F1's evidence is M14 to M16 (recorded fails with large margin) rather than M1 to M5, so it demonstrably survives the cascade ("everything else unchanged").
3. The Stage 2 decision is also flagged in Stage 3 (three flagged), unless Stage 2 runs with `persist=false`.
4. L2 starts PROVISIONAL (grey) and turns amber; only L1 is corroborated.
5. Material and process are ranking terms, not hard retrieval filters.
6. Added fields: `title`, `action`, `owner` on memories; `current_verdict` on measurements; `stream_state` collection.
7. `SUPERSEDED` is ranked like `HISTORICAL_ONLY` (-0.22) and excluded by default.
8. The calibration event's `U` is used for recomputation; each measurement's own `u_mm` is stored for display only.

## 17. Claims to verify before presenting

- The Voyage model name and its 1024-dimension output.
- That TTL deletions emit change stream delete events on your Atlas tier (Section 4).
- Every paper citation on the slides (PACMI, Zep, Reflexion, Mem0, and the ones in your research report that were not opened). Say "none found in our search" about novelty, never "nobody has done this".
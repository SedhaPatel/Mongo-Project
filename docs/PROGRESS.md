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

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


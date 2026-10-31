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

## 12. Corroboration needs a second instrument to promote
PLAN 7.4 says "if any set holds, set ACTIVE". Taken literally, adding more passing measurements on the *same* gauge (the same non-independent instrument) would promote a PROVISIONAL lesson. `corroborate()` therefore requires at least two distinct instruments plus a holding set. That preserves the demo intent ("two instruments now support this lesson") and keeps Section 6.4's rule that only corroboration promotes. Tested in `test_writer.py`.

## 13. Offline fixture embeddings
`embeddings.py` falls back to `backend/seed/fixtures/text_embeddings.json` only for exact `(input_type, text)` pairs precomputed by `backend/seed/text_embeddings.py` (deterministic 1024-dim signed word hashes). This is synthetic fixture data for replaying the demo without a Voyage key (PLAN 7.6 allow precomputed fixtures); it is not presented as Voyage output and never invents a vector for unseen text. With a key configured, Voyage is called first. The fixture also carries the string used by `test_embeddings.py`, which previously failed offline.

## 14. `write_lesson(..., embedding=None)` optional injection
The Section 7.2 signature is unchanged; an optional `embedding` keyword was added so offline fixtures and tests can supply the already-precomputed vector without duplicating the embedding wrapper. When omitted, `get_embedding(..., input_type="document")` is used exactly as specified.

## 15. Retrieval fallback when `$vectorSearch` is unavailable
The development MongoDB on this laptop is a standalone server (change streams and Atlas Search are unavailable). `retrieval.py` therefore uses `$vectorSearch` when the deployment serves it and falls back to `find` + in-process cosine over the identical pre-filters when the aggregation does not return a `vector_score` (also what `tests/mock_db.py` needs). The fallback is explicit and observable: it never masks a partially-filtered Atlas result, and an Atlas deployment always takes the index path. This is the PLAN 4 fallback for "vector search unavailable on tier", applied at query time.

## 16. Scope match with no scope supplied
`scope_match = matching / supplied` would divide by zero for `POST /recommend` without a scope. The term is neutral (1.0) when no scope field is supplied, so ranking falls back to vector score, state, Memory Worth and recency. Recorded as the simplest option (AGENTS rule 7).

## 17. Anthropic transport is the Messages REST API via `httpx`
The `anthropic` SDK is not installed and `uv` is not on PATH in this environment, so adding an SDK dependency was not possible (and would not be used by the offline demo anyway). `agent/llm.py` posts to `https://api.anthropic.com/v1/messages` with `httpx` (already in `pyproject.toml`) and sends the same forced-tool body the SDK would: `tools=[{name, input_schema}]`, `tool_choice={"type":"tool","name":...}`, `anthropic-version: 2023-06-01`. The response parser accepts only a `tool_use` block with the expected tool name; anything else raises `LLMUnavailable` and the caller falls back. This keeps `llm.py` importable and testable without the SDK and without the network.

## 18. The committed fallback draft is cached on use
PLAN 7.3 says to fall back to `seed/fixtures/ncr_0412_lessons.json`, and PLAN 7.6 wants an online run to fill the cache for offline replay. `ingest_ncr` therefore runs the fallback through the same shape validation as an LLM answer and stores the validated fallback under the forced-tool cache key. A second `POST /ncr` for the same payload returns `draft_source="cache"` with identical lessons. This also means the fallback is never trusted blindly: if the NCR does not cite the fixture's measurements (or the `ncr_id` differs), no lessons are written.

## 19. Plan steps cover the top five, not just the demo triad
PLAN 7.7 says "keep the top 5" and build a step for each retrieved memory. On the seed, positions 4 and 5 are background lessons `B1` and `B4`, so a live `POST /recommend` returns five steps (apply L2, apply L1, avoid F1, apply B1, apply B4), while `frontend/fixtures/recommend.stage2.json` shows the three demo-relevant steps. The three required steps are always present; no extra filter was invented because the spec is explicit about top 5. Tests assert the presence of L1/L2/F1 rather than an exact count.

## 20. Stage 2 decision keeps the fixture ID `D-STAGE2`
`POST /recommend` numbers ordinary decisions `D1`, `D2`, ... (ignoring non-numeric demo IDs). The `/demo/stage/2` endpoint passes `decision_id="D-STAGE2"` so the live review list matches `frontend/fixtures/review.json` (D1, D2, D-STAGE2 flagged after the Stage 3 cascade). A later direct `POST /recommend` still allocates `D3`. Stage 3's re-ask persists after the cascade, so it is not retroactively flagged and the review count stays three.

## 21. Verify step when no independent OK gauge exists
`pick_verify_instrument` returns `None` if every OK gauge is in the lesson's weakened/broken sets. The code-built step stays `kind="verify"` with `verify_instrument=None` and the text "Verify on an independent instrument before adopting: ...". The demo never hits this path (CMM-02/CMM-05 are OK and independent of BG-07), but refusing to invent a gauge is safer than naming one that just failed.

## 22. Removed the `UpdateOptions` import from `streams/memory_watcher.py`
The watcher imported `from pymongo import UpdateOptions`, which does not exist in the installed pymongo 4.19 (the symbol lives in `pymongo.operations`, and the watcher never used it). The import blocked `import backend.app.main` entirely. Removing the unused import is the smallest fix; the watcher logic is unchanged and still uses `full_document_before_change="whenAvailable"` through the collection options created by `bootstrap()`.

## 23. `/calibration` runs the cascade inline when change streams are unsupported
The specified demo flag is `POST /calibration?direct=true` (Section 8/10). On this standalone MongoDB the gauge watcher cannot open a change stream, so `direct=false` would write `cal_status` and silently never demote anything. The endpoint therefore treats `direct` as a boolean query flag (`true` and `1` both work) and, when it is false, checks `db.command("hello")`; if the deployment is not a replica set or mongos it runs the cascade inline. On Atlas the request stays watcher-driven and the flag keeps its original meaning. Recorded in PROGRESS with the live `?direct=true` output.

## 24. Background lessons collapse into one `lesson_group` node on `/graph`
PLAN 8.1 says "under about 40 nodes" and also that background lessons are included with `background=true`. Six gauges, 16 demo measurements, six filler groups and four decisions already use 32 nodes; the 13 seeded background lessons would push the live graph to 45. `GET /graph` therefore emits one `lesson_group` node (`id="background_lessons"`, `count=13`, `background=true`) instead of 13 nodes, giving 36 nodes / 24 edges in the live run. The UI toggle still has a single background element to hide; no background lesson detail is needed by the demo graph because the fixtures only draw L1, L2, F1 and decisions.

## 25. Cache keys serialise BSON dates with `default=str`
The reword input includes each memory's `history[]`, whose `ts` values are `datetime` objects from MongoDB. `cache.compute_cache_key()` used `json.dumps` without a default and raised `TypeError: Object of type datetime is not JSON serializable` on the first live `POST /recommend`. Both the key computation and the cache writer now pass `default=str`. Payloads without dates hash exactly as before (the default is never called), so the committed NCR draft cache key is unchanged.

## 26. `GET /events` streams from `events.py`, not `streams/sse.py`
PLAN 7.1 makes `events.log_event` the single bus (audit insert + replay buffer + subscriber queues), and every watcher and endpoint calls it. `streams/sse.py` contains a second, independent `_REPLAY`/queue that nothing publishes to; splitting the feed between two buses would drop events depending on which helper a caller used. The API therefore uses `events.subscribe_events`/`unsubscribe_events`/`get_replay_events` and leaves `streams/sse.py` untouched for its owner. The SSE test asserts the main bus has no leaking subscribers after a stream closes.

## 27. API response envelopes follow the committed frontend fixtures
`GET /graph` returns `{"elements": {"nodes": [...], "edges": [...]}}`, the shape of `frontend/fixtures/graph.stage*.json`, rather than a bare `nodes`/`edges` object. `GET /memories/{id}` returns the memory document at top level plus an `evidence` array, matching the flat `frontend/fixtures/memory.L1.json`; the evidence entries carry `verdict`, `current_verdict`, `gauge_id` and the live gauge `cal_status` required by PLAN Section 8. `GET /decisions/review` keeps the field subset the original endpoint returned, now sorted newest first — the original bug was `list(...).sort(...)`, which is in place and returns `None`, so the endpoint had no list to iterate. Extra keys in a response are allowed; keys the fixtures rely on are not omitted.



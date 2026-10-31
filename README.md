# Metrologic

Metrologic is a calibration-aware agent-memory demo for manufacturing quality workflows. It links learned process lessons to the physical measurements and instruments that support them, then reevaluates that evidence when an instrument is reported out of calibration. Rather than invalidating every lesson associated with a gauge, Metrologic recomputes measurement verdicts and changes only the memories and past decisions affected by the new evidence.

> **Scope:** Metrologic is a synthetic-data research and demonstration project, not a production quality system or a substitute for a calibrated measurement process, a validated decision rule, or regulatory advice. Its benchmark and example tolerances are illustrative.

## At a glance

- **Backend:** Python 3.12+, FastAPI, Pydantic, PyMongo, and Uvicorn.
- **Database:** MongoDB; Atlas Local is used for local demonstrations of Vector Search, change streams, pre/post images, and TTL behavior.
- **Agent and embeddings:** Structured LLM tool calls for drafting/rewording and Voyage AI embeddings, with a disk cache and exact-text synthetic fixtures for offline replay.
- **Frontend:** Next.js 15, React 19, TypeScript, Tailwind CSS 4, and Cytoscape.js.
- **Demo UI:** Home/ledger and provenance workbench, with a fixture-driven mode that does not require the API or MongoDB.

## Why calibration-aware memory?

A normal retrieval system can remember that a process adjustment worked without retaining which measurements justified it or which instrument produced those measurements. If that gauge later drifts, the recommendation can remain in circulation even though its evidence needs review. A topology-only response has the opposite problem: it can discard all lessons downstream of that instrument, including lessons supported independently.

Metrologic stores measurement and gauge provenance with each lesson. When calibration data arrives, deterministic Python recomputes the affected verdicts and reevaluates support sets. Independently supported lessons can remain active; lessons whose evidence is weakened can be retained as `NEEDS_VERIFICATION`, and decisions that relied on them are flagged for review.

## How it works

### 1. Ingest a non-conformance report

`POST /ncr` accepts an NCR summary, trials, and measurement documents. An LLM can draft structured lessons and failed attempts, but the backend validates every cited measurement ID and requires at least one valid measurement reference for every memory. Invalid output is retried and then handled by the validated committed demo draft; unvalidated memories are never written.

Each lesson stores `support_sets`, grouped by measuring instrument. The set structure preserves independent evidence instead of flattening all measurements into one list.

### 2. Corroborate and promote

`POST /lessons/{lesson_id}/corroborate` adds measurements from another job. Measurements from the same gauge are merged into that gauge's support set; a new gauge forms a distinct set. Corroboration promotes a provisional lesson only when a holding support set from a distinct instrument exists. For the demo, CMM-02 corroborates L1, promoting it from `PROVISIONAL` to `ACTIVE`.

### 3. Retrieve and rank memories

Recommendations retrieve relevant lessons and failed attempts using MongoDB Atlas Vector Search when available. Scope fields such as material and process contribute to ranking rather than acting as hard filters by default, so a related lesson can still be considered across materials. Optional scope filtering and history retrieval are also available.

Each result includes a transparent ranking trace. The implemented score is:

```text
final = vector_score
      + state_bias
      + 0.2 * (memory_worth - 0.5)
      + 0.05 * recency
      + 0.1 * scope_match

memory_worth = (successes + 1) / (successes + failures + 2)
recency      = exp(-age_days / 90)
```

State biases are `ACTIVE` +0.12, `PROVISIONAL` +0.04, `NEEDS_VERIFICATION` -0.10, and `HISTORICAL_ONLY` / `SUPERSEDED` -0.22. Historical-only and superseded memories are excluded from normal retrieval. If a deployment cannot perform `$vectorSearch`, retrieval falls back to the same prefilters plus in-process cosine similarity.

The backend builds recommendation step kinds in code: `apply` for usable lessons, `verify` for lessons needing verification, and `avoid` for failed attempts. The LLM may reword those steps, but validation requires it to preserve the step count, kinds, and referenced memories; otherwise, the code-built wording is used. It never decides measurement truth, validity state, or whether evidence passes.

### 4. Recompute verdicts after calibration drift

For a calibration event on gauge `G` at time `T`, the cascade considers measurements from the suspect interval after the gauge's last known good calibration and through the event time. It corrects each reading with the as-found error `e` and expanded uncertainty `U`:

```text
x' = x - e
corrected interval = [x' - U, x' + U]
```

Using `Decimal` arithmetic, the interval is classified against the measurement tolerance as:

- `pass` when the entire interval is within tolerance (inclusive).
- `fail` when the interval is disjoint from tolerance.
- `indeterminate` when it overlaps or touches a tolerance boundary from outside.

Measurement records retain the original `verdict`; the recalculated result is written to `current_verdict` with event history. The support-set lattice treats evidence as holding, weakened, or broken. A cascade never promotes a lesson: `corroborate()` is the promotion path. If independent evidence still holds, the lesson can stay active; otherwise it can move through `NEEDS_VERIFICATION` or `HISTORICAL_ONLY`. The cascade is idempotent and can reevaluate dependent memories and flag past decisions that used demoted evidence.

### 5. Stream events and inspect provenance

MongoDB change streams drive gauge/memory watchers where the deployment supports them. Audit events are published through a shared event bus and exposed as Server-Sent Events. The graph endpoint returns Cytoscape-compatible elements; it groups filler measurements and background lessons to keep the graph compact. Memory detail includes the evidence chain, original/current verdicts, gauge calibration status, and history.

## Demo walkthrough

The seeded scenario is synthetic and includes six gauges, 193 measurements, 13 background lessons, and prior decisions.

| Stage | Action | Expected behavior |
|---|---|---|
| Reset | Reload the seeded scenario | Start from the repeatable demo state. |
| 1a — Learn | Ingest NCR-0412 | Draft L1, L2, and failed attempt F1 as `PROVISIONAL`, each with measurement provenance. |
| 1b — Corroborate | Add CMM-02 measurements for L1 | L1 becomes `ACTIVE` with independent support; L2 remains supported by BG-07 alone. |
| 2 — Recommend | Request a process plan | The plan includes apply steps for lessons, an avoid step for F1, and an explainable ranking trace; the decision is persisted. |
| Arm TTL | Create the temporary trial memory | The live path uses a MongoDB TTL index; fixture mode provides a replayable demonstration event. |
| 3 — Calibration | Report BG-07 at +6 µm with 2 µm uncertainty | Recompute affected measurements, retain L1 through independent CMM-02 evidence, and move L2 to `NEEDS_VERIFICATION`; decisions using L2 are flagged. |
| Re-ask | Request the plan again | L2's step changes to “verify on CMM-02 before adopting”; the event feed, plan diff, graph, and review list show the change. |

The frontend's fixture mode drives this sequence locally, including staged graph updates and replayable event-feed entries. It is the recommended option for a presentation without a live backend. Live API mode connects the dashboard to the FastAPI service and its SSE feed.

## Architecture and data

```text
backend/
  app/
    agent/       # NCR ingestion, LLM tool calls, recommendation planning
    memory/      # provenance-enforcing writer, retrieval, ranking
    validity/    # Decimal metrology, support lattice, calibration cascade
    streams/     # gauge/memory watchers and SSE support
    cache.py     # disk cache for model and embedding responses
    db.py        # MongoDB handles, indexes, and bootstrap
    main.py      # FastAPI endpoints and application lifespan
    models.py    # Pydantic data contract
  seed/          # synthetic scenario, reset/stages, fixtures, benchmark
  tests/         # deterministic unit, API, and workflow tests
frontend/
  app/           # Next.js application
  components/    # workbench, graph, inspector, feed, dialogs
  fixtures/      # offline stage graphs, memories, recommendations, events
  lib/           # API client, fixture data, graph transforms, state store
docs/
  PLAN.md        # full technical plan, data contract, and API behavior
  PROGRESS.md    # milestone status, acceptance outputs, and verification notes
  DECISIONS.md   # implementation decisions and deviations
  demo-script.md # four-minute presenter/driver script and Q&A
  slides.md      # five-slide hackathon pitch deck
```

MongoDB stores the following principal collections:

- `memories`: lessons and failed attempts, embeddings, validity state, evidence support sets, use history, and optional expiry.
- `measurements`: synthetic measurement readings, tolerance bounds, original and current verdicts, gauge ID, and verdict history.
- `gauges`: instrument calibration status, last good calibration, and as-found calibration data.
- `decisions`: generated plan steps, memories used, ranking trace, part serials, and review status.
- `audit_log`: timestamped calibration, cascade, verdict, memory-state, decision-review, and TTL events.
- `stream_state`: change-stream resume tokens.

The database bootstrap configures standard indexes, a TTL index, change-stream pre-images where supported, and the `memories_vec` vector-search index. Atlas Local was used to verify vector search, change streams, pre-images, update events, and TTL delete events. Standalone MongoDB does not provide all of those capabilities; the app has a vector-retrieval fallback and runs the calibration cascade inline when change streams are unavailable.

All scenario data is synthetic. The project stores feature class and tolerance band as scope metadata; do not put drawings, customer names, or operator names into the seed or demo data.

## API reference

The API listens on `http://localhost:8000`. JSON endpoints are implemented in `backend/app/main.py`; `/events` is an SSE stream.

| Method and path | Purpose |
|---|---|
| `POST /ncr` | Validate and ingest an NCR, its trials, and measurements; draft and write provenance-backed memories. |
| `POST /lessons/{lesson_id}/corroborate` | Add measurement evidence, merge support by gauge, and promote with independent holding evidence. |
| `POST /recommend` | Retrieve/rank memories, build and optionally persist a plan decision. Request fields include `query`, optional `scope`, `workspace`, `persist`, `history`, and `part_serials`. |
| `GET /memories/search?q=...` | Search memories. Optional query parameters include `material`, `process`, `machine`, `feature_class`, `tolerance_band`, `history`, `scope_filter`, `limit`, and `rank_limit`. |
| `GET /memories/{memory_id}` | Return the memory document and its measurement/memory evidence chain. |
| `GET /graph` | Return graph nodes and edges in Cytoscape format. |
| `POST /calibration` | Record an `OUT_OF_TOLERANCE` event. Body fields include `gauge_id`, `as_found_error_mm`, and `as_found_u_mm`; `?direct=true` requests inline cascade execution. |
| `GET /decisions/review` | List decisions flagged for review, including the reason and associated part serials. |
| `GET /events` | Subscribe to Server-Sent Events; `?replay=1` sends up to 200 recent events before following the live stream. |
| `POST /demo/reset` | Reload the synthetic scenario and clear the in-memory event replay buffer. |
| `POST /demo/stage/{stage_n}` | Replay demo inputs. Stage 1 accepts `?step=a` (default) or `?step=b`; Stage 3 accepts `?step=arm` or runs the calibration stage. |

For the complete request/response contract and graph semantics, see [docs/PLAN.md](docs/PLAN.md).

## Requirements

- Python 3.12 or newer.
- [`uv`](https://docs.astral.sh/uv/) for the Python environment.
- Node.js 20 or newer and npm.
- Docker for the local MongoDB Atlas Local container.
- `make` is optional; the direct commands below work without it.

## Quick start

### 1. Configure the backend

Create a root `.env` from the template:

```powershell
Copy-Item .env.example .env
```

On macOS/Linux, use `cp .env.example .env`.

For the Docker database in this guide, edit `.env` and set:

```dotenv
MONGODB_URI=mongodb://127.0.0.1:27017/?directConnection=true
MONGODB_DB=metrologic
WORKSPACE=plant-1
```

The committed template uses a placeholder Atlas URI; replace it with a real URI if connecting to Atlas. Never commit `.env` or API keys.

### 2. Install dependencies and start MongoDB

```powershell
uv sync
docker run -d --name metrologic-mongo -p 27017:27017 mongodb/mongodb-atlas-local
```

The Docker command creates the `metrologic-mongo` container and exposes MongoDB on port 27017. If it is already running, do not create a second container with the same name.

### 3. Seed the demo and start the API

In the repository root:

```powershell
uv run python -m backend.seed.reset
uv run uvicorn backend.app.main:app --reload --port 8000
```

The API bootstraps the database and starts supported watchers on startup. Keep this terminal open.

### 4. Start the frontend

In another terminal:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Open `http://localhost:3000`. Fixture mode is the default and does not wait for the API. To use the live backend, create `frontend/.env.local` with:

```dotenv
NEXT_PUBLIC_USE_FIXTURES=0
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

Restart the Next.js dev server after changing environment variables. Live calls that use uncached LLM or embedding inputs also need valid provider credentials.

### Make targets

If `make` is installed, the `Makefile` provides:

| Command | Action |
|---|---|
| `make up` | Start the Atlas Local MongoDB container. |
| `make seed` | Reset and seed the synthetic scenario. |
| `make api` | Run the FastAPI app on port 8000. |
| `make web` | Run the Next.js dev server on port 3000. |
| `make test` | Run `uv run pytest -q`. |

## Configuration and offline behavior

The root `.env.example` documents the current configuration:

| Variable | Purpose |
|---|---|
| `MONGODB_URI` | MongoDB connection string. The template is a placeholder Atlas URI; local Atlas Local can use `mongodb://127.0.0.1:27017/?directConnection=true`. |
| `MONGODB_DB` | Database name; defaults to `metrologic`. |
| `WORKSPACE` | Default workspace identifier; defaults to `plant-1`. |
| `LLM_PROVIDER` | Provider selection. The implementation supports Gemini (`gemini`) and Anthropic (the non-Gemini path). |
| `LLM_MODEL` | Model identifier for the selected provider. |
| `LLM_BASE_URL` | Present in the template for a local endpoint, but not currently consumed by the LLM client. |
| `GOOGLE_API_KEY` | Required for Gemini requests when using that provider. |
| `ANTHROPIC_API_KEY` | Credential for the Anthropic Messages API path. |
| `VOYAGE_API_KEY` | Required for live Voyage embedding requests that miss cache and fixtures. |
| `EMBED_MODEL` | Voyage embedding model; template default is `voyage-3-large` (1024 dimensions). |
| `CACHE_DIR` | Disk cache directory; defaults to `.cache`. |
| `OFFLINE` | Set to `1` to prohibit remote LLM/Voyage calls; cache or exact demo-fixture misses raise an explicit error. |
| `NEXT_PUBLIC_USE_FIXTURES` | Frontend mode; `1` (default) uses local JSON fixtures, `0` uses the live API. |
| `NEXT_PUBLIC_API_BASE` | Live backend base URL; frontend config defaults to a hosted URL if unset. Set it to localhost for local live mode. |

**Provider configuration note:** `.env.example` currently says `LLM_PROVIDER=ollama`, but an Ollama transport is not implemented; `LLM_BASE_URL` is also unused. For live LLM requests, set `LLM_PROVIDER=gemini` and provide `GOOGLE_API_KEY`, or provide `ANTHROPIC_API_KEY` and use the Anthropic path. Cached and validated fixture responses can still support the documented offline demo flow.

Embedding lookup checks the disk cache and committed exact-text fixtures before calling Voyage. The fixtures are synthetic demo vectors, not a general embedding substitute; they do not invent embeddings for unseen text. NCR fallback drafts are validated and only apply to their matching demo input. For new input in live mode, configure the required provider credentials; in `OFFLINE=1`, a cache/fixture miss is reported rather than silently replaced.

## Testing and verification

Run the backend suite:

```powershell
uv run pytest -q
```

Run the frontend production build:

```powershell
Set-Location frontend
npm run build
```

Tests cover interval guardbanding and boundary cases, support-set/lattice transitions, provenance enforcement, ingestion and offline cache behavior, ranking/retrieval, recommendation behavior, cascade idempotency, demo stages, API endpoints, and SSE event replay.

The latest recorded acceptance results in [docs/PROGRESS.md](docs/PROGRESS.md) show **79 backend tests passing**, a successful frontend build, the complete live local-database flow, and all seven Atlas Local capability-spike checks passing. These are repository verification records, not a claim that every external provider credential or hosted deployment has been tested. The Voyage model/dimension was checked against its documentation; a live Voyage API call was not made in the recorded verification.

The synthetic 20-scenario drift benchmark in `backend/seed/drift_benchmark.py` reports 60 topology-only false demotions avoided, zero under-invalidation, and zero unnecessary verification in that test set. Reproduce it with:

```powershell
uv run python backend/seed/drift_benchmark.py
```

These are results from a deterministic synthetic benchmark, not real-world production measurements or a guarantee of zero quality escapes.

## Project documentation and presentation

- [docs/PLAN.md](docs/PLAN.md) — technical specification, data contract, algorithms, endpoints, demo stages, and acceptance criteria.
- [docs/PROGRESS.md](docs/PROGRESS.md) — milestone completion, command output, live acceptance notes, and verification limitations.
- [docs/DECISIONS.md](docs/DECISIONS.md) — design decisions, fallbacks, and implementation deviations.
- [docs/demo-script.md](docs/demo-script.md) — four-minute presenter/driver script with actions, talk track, and anticipated Q&A.
- [docs/slides.md](docs/slides.md) — five-slide hackathon pitch deck.

The latest presentation material also outlines a ten-minute talk: title and hook (0:00–1:00), industrial problem (1:00–2:15), breakthrough (2:15–3:30), architecture and MongoDB role (3:30–4:45), Stage 1/2 walkthrough (4:45–6:15), calibration cascade (6:15–7:45), governance and plan adaptation (7:45–8:30), benchmark (8:30–9:15), and conclusion (9:15–10:00).

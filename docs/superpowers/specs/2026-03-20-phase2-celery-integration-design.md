# Phase 2: Celery Integration — Design Spec

**Date:** 2026-03-20
**Scope:** Weeks 3–4 of the SimulationCity development roadmap
**Status:** Approved

---

## Overview

Phase 2 wires up the Celery task queue for two purposes:

1. **Build actions** — player actions (place building, road, zone, demolish) are enqueued from the Socket.IO server to the `high_priority` queue and processed by a worker asynchronously.
2. **Simulation ticks** — a periodic Beat task fans out `simulate_city_tick` jobs to the `simulation` queue, one per active city, every 10 seconds.

Results are written directly to MongoDB. Real-time broadcasting to players is deferred to Phase 3 (MongoDB change streams).

---

## Architecture & Data Flow

### Build Actions

```
Client
  │
  │  emit("build_action", { action_type, payload })
  ▼
socket_handlers.py
  │  1. Auth check (session user_id + city_id)
  │  2. Validate action_type is in VALID_ACTION_TYPES (frozenset in app/constants.py)
  │  3. Enqueue via celery_app.send_task("workers.build_actions.process_build_action", ...)
  │  4a. ACK:   emit("action_queued", { action_type, status: "queued" }, to=sid)
  │  4b. Error: emit("error", { message: "..." }, to=sid)  [for validation failures]
  ▼
Celery high_priority queue
  │
  ▼
workers/build_actions.py
  │  process_build_action(city_id, user_id, action_type, payload)
  │  → REGISTRY[action_type](city_id, user_id, payload)
  │  → appends/modifies documents in MongoDB via pymongo
  │  → updates chunk.last_updated and city.last_updated
  ▼
MongoDB (chunks collection)
```

### Simulation Ticks

```
Celery Beat (every 10s)
  │
  ▼
workers/simulation.py :: tick_all_cities()  [queue: simulation]
  │  → queries MongoDB for all city IDs
  │  → fans out simulate_city_tick.delay(city_id) for each
  │
  │  NOTE (Week 3 simplification): ticks ALL cities regardless of activity.
  │  A follow-up item will add an activity filter (e.g. last_updated within
  │  a recent window) before production to avoid ticking abandoned cities.
  ▼
Celery simulation queue (one task per city)
  │
  ▼
workers/simulation.py :: simulate_city_tick(city_id)
  │  1. Load all chunks via pymongo
  │  2. Apply simulation rules per chunk
  │  3. Write updated chunks (increment version, skip on conflict — see Concurrency note)
  │  4. Aggregate population, treasury, happiness → update city.global_stats
  │     and city.last_updated
  ▼
MongoDB (chunks + cities collections)
```

**Concurrency note:** When a chunk write is skipped due to a version conflict (another process updated it between load and write), that chunk's simulation result for this tick is silently discarded. This is intentional and acceptable for Phase 2 — the chunk will be re-processed on the next tick. Partial tick results are expected and safe.

---

## Shared Constants

A new file `backend/app/constants.py` defines the set of valid action types:

```python
VALID_ACTION_TYPES: frozenset[str] = frozenset({
    "place_building",
    "place_road",
    "place_zone",
    "demolish",
})
```

Both `socket_handlers.py` (for validation) and `workers/build_actions.py` (as the registry's authoritative key set) import from here. This avoids importing any worker module into the FastAPI process.

---

## Components

### `workers/build_actions.py`

**Task:** `process_build_action(city_id, user_id, action_type, payload)`
- Queue: `high_priority`
- Max retries: 3, exponential backoff
- Routes `action_type` through a module-level `REGISTRY` dict

**Registry:**
```python
REGISTRY: dict[str, Callable] = {
    "place_building": _handle_place_building,
    "place_road":     _handle_place_road,
    "place_zone":     _handle_place_zone,
    "demolish":       _handle_demolish,
}
```

**Handler contract:** `(city_id: str, user_id: str, payload: dict) -> None`

Each handler writes to MongoDB via pymongo and updates `chunk.last_updated` on every write.

**Week 3 scope:** `place_building` is fully implemented — it appends a new entry to `chunk.base.buildings` via a pymongo `$push` update on the correct chunk (looked up by `city_id` + `coordinates`). Since Celery serializes kwargs as JSON, `city_id` always arrives in the worker as a `str`; pymongo queries must convert it: `{"city_id": ObjectId(city_id)}`. The other three handlers are stubs (log + return) — the registry is complete but not over-built.

**Error handling:**
- Unknown `action_type`: log warning, return early (no retry) — this should not occur since the socket handler pre-validates against `VALID_ACTION_TYPES`
- Handler exception: log, re-raise → Celery retries up to 3 times with exponential backoff

**pymongo connection:** Module-level `MongoClient` instance, instantiated at module level and reused across tasks on the same worker process (standard Celery pattern). The module is structured so that `MongoClient` is only created when the module is first loaded by a worker — not at import time in other processes.

**Task import in socket_handlers.py:** The socket handler enqueues tasks by name using `celery_app.send_task("workers.build_actions.process_build_action", kwargs={...})` rather than importing the task function directly. This avoids pulling the workers module (and its `MongoClient` instantiation) into the FastAPI process.

---

### `workers/simulation.py`

**Task 1:** `tick_all_cities()` — Beat entry point
- Queue: `simulation`
- Queries MongoDB for all city IDs
- Fans out `simulate_city_tick.delay(city_id)` for each
- Runs every 10 seconds via Celery Beat

**Task 2:** `simulate_city_tick(city_id)`
- Queue: `simulation`
- Idempotent — safe to re-run

**Tick sequence:**
1. Load all chunks for the city via pymongo
2. Apply rules per chunk (see below)
3. Write modified chunks back: increment `version`, update `chunk.last_updated`; use a conditional update (`$where version == expected`) — skip the chunk silently if version has changed (see Concurrency note above)
4. Aggregate `population`, `treasury`, and `happiness` from chunk data → write all three fields to `city.global_stats`, and update `city.last_updated`

**`ChunkLayers` schema for simulation:** The existing `layers` fields (`electricity`, `pollution`, `water`) are typed as `dict`. For simulation purposes, each is treated as `{"coverage": float}` where `coverage` is a value from `0.0` to `1.0`. The simulation rules read and write the `coverage` key:

- `electricity.coverage > 0` → the chunk has power
- `water.coverage > 0` → the chunk has water
- `pollution.coverage` → increases with industrial buildings, decreases slowly each tick

This schema is a Week 4 decision that must be settled before implementing `simulate_city_tick`. If the schema changes in a future phase, only the simulation rules and the layer initialization logic need updating.

**Simulation rules:**

| Rule | Logic |
|---|---|
| Residential growth | Chunks with residential buildings gain `+1` population if `electricity.coverage > 0` AND `water.coverage > 0`; lose `-1` population per tick otherwise |
| Treasury income | `treasury += population * TAX_RATE_PER_TICK` (constant defined in simulation module) |
| Industrial pollution | Industrial buildings set `layers.pollution.coverage` to `min(1.0, current + 0.1)` for their chunk and `min(1.0, current + 0.05)` for adjacent chunks; pollution decays by `0.01` per tick in all chunks |
| Happiness | `happiness = clamp(100 - (avg_pollution * 50) + (commercial_count * 2), 0, 100)` across all city chunks; `commercial_count` is computed at tick time by counting buildings with `type == "commercial"` across all loaded chunks |

---

### `socket_handlers.py` — `build_action` event

New handler added to the existing `socket_handlers.py`:

```
@sio.event async def build_action(sid, data):
    1. Check session has user_id + city_id → emit "error" if not
    2. Extract action_type from data → emit "error" if missing
    3. Check action_type in VALID_ACTION_TYPES (from app.constants) → emit "error" if unknown
    4. celery_app.send_task(
           "workers.build_actions.process_build_action",
           kwargs={ city_id, user_id, action_type, payload },
           queue="high_priority"
       )
    5. emit("action_queued", { "action_type": ..., "status": "queued" }, to=sid)
```

The handler never awaits task completion. It validates, enqueues, and ACKs immediately.

---

### `workers/celery_app.py` — changes

Register task modules explicitly (the standard `autodiscover_tasks` assumes a `tasks.py` convention and will not find these non-standard module names; `conf.include` is the correct mechanism):
```python
celery_app.conf.include = ["workers.simulation", "workers.build_actions"]
```

Add Beat schedule with explicit queue assignment:
```python
celery_app.conf.beat_schedule = {
    "tick-all-cities": {
        "task": "workers.simulation.tick_all_cities",
        "schedule": 10.0,  # seconds
        "queue": "simulation",  # must be explicit; default is high_priority
    }
}
```

---

## What Is NOT in Scope

- Real-time broadcast of build/tick results (Phase 3 — change streams)
- Full implementation of `place_road`, `place_zone`, `demolish` handlers (stubs only)
- Activity-based filtering for `tick_all_cities` (known Week 3 simplification; follow-up item)
- Viewport-based chunk filtering in tick (Phase 3)
- Celery worker auto-scaling (Phase 6)

---

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Unit | Simulation rules | Pure functions, pytest, no DB required |
| Unit | Registry dispatch | Mock handler, assert called with correct args |
| Integration | `process_build_action` | Real MongoDB (docker-compose), assert `$push` to chunk.base.buildings |
| Integration | `simulate_city_tick` | Seed city + chunks, run tick, assert all three global_stats fields updated |
| Integration | Socket.IO → queue | `python-socketio` `AsyncTestClient`, assert `send_task` called with correct kwargs |

---

## Files Created / Modified

| File | Change |
|---|---|
| `backend/app/constants.py` | New — `VALID_ACTION_TYPES` frozenset |
| `backend/workers/build_actions.py` | New — registry + task + `place_building` handler |
| `backend/workers/simulation.py` | New — `tick_all_cities` + `simulate_city_tick` + rules |
| `backend/workers/celery_app.py` | Modified — autodiscovery + Beat schedule (with queue) |
| `backend/app/socket_handlers.py` | Modified — add `build_action` event handler |
| `backend/tests/test_build_actions.py` | New — unit + integration tests |
| `backend/tests/test_simulation.py` | New — unit + integration tests |

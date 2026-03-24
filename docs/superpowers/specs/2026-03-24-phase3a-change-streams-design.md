# Phase 3a: Change Streams — Design Spec

**Date:** 2026-03-24
**Scope:** Week 5 of the SimulationCity development roadmap
**Status:** Approved

---

## Overview

Phase 3a adds real-time updates to connected players by watching MongoDB change streams and broadcasting relevant Socket.IO events to city rooms. When the simulation tick updates chunk pollution or city stats, or when a build action adds a building, connected players receive the update immediately — no polling required.

The change stream listener runs as an `asyncio` background task inside the existing FastAPI/Socket.IO process. Phase 3b (viewport-based filtering, lazy chunk loading) is deferred to a separate spec.

---

## Architecture & Data Flow

```
MongoDB Atlas (replica set)
  │
  │  change stream (Motor async)
  ▼
app/change_stream.py :: watch_changes()   [asyncio background task]
  │  Watches two collections: chunks + cities
  │  Routes events by updatedFields
  │  Emits Socket.IO events to city:{city_id} rooms
  ▼
Socket.IO server (sio)
  │
  ▼
Connected clients in the city room
```

`watch_changes()` is started in the FastAPI lifespan on startup and cancelled on shutdown. It opens two Motor change streams concurrently using `asyncio.gather`. Both streams request `full_document="updateLookup"` to get the current document state alongside the diff.

---

## Change Stream Routing

All routing uses **prefix matching** against `updateDescription.updatedFields` keys. A single MongoDB write can produce multiple `updatedFields` entries (e.g. `layers.pollution.coverage` and `last_updated` in the same event) — the checks are OR conditions, not exclusive branches.

### `chunks` collection

Inspect `updateDescription.updatedFields` on each `update` event:

| Any `updatedFields` key starts with… | Action |
|---|---|
| `layers.` | Emit `layers_update` |
| `base.buildings.` | Emit `chunk_update` (`$push` generates keys like `base.buildings.3`) |
| Anything else only (e.g. `last_updated`, `version`) | Skip — no broadcast |

Note: `simulate_city_tick` writes `layers.pollution.coverage` and `last_updated` in the same update. The presence of `last_updated` alongside a `layers.*` key must not suppress the event — check for the meaningful prefix first.

Note: `$push` to `base.buildings` generates `updatedFields` keys of the form `base.buildings.<index>` (e.g. `base.buildings.3`), not the bare key `base.buildings`. The routing check must match the prefix `base.buildings.`, not an exact key.

### `cities` collection

| Any `updatedFields` key starts with… | Action |
|---|---|
| `global_stats.` | Emit `stats_update` |
| Anything else only | Skip — no broadcast |

Only `update` operations are watched. Insert and delete operations on these collections are not broadcast in Phase 3a.

---

## Socket.IO Events

All events are emitted to the `city:{city_id}` room (broadcast to all players in that city).

### `stats_update`

Fired when `cities.global_stats` is updated (simulation tick).

```json
{
  "city_id": "<str>",
  "population": 142,
  "treasury": 10284.3,
  "happiness": 67
}
```

Note: `treasury` is stored as a float by the simulation worker (pymongo bypasses Pydantic coercion). Clients should treat it as a float.

### `layers_update`

Fired when `chunks.layers` is updated (simulation tick — pollution coverage changes).

```json
{
  "city_id": "<str>",
  "chunk_x": 2,
  "chunk_y": 3,
  "layers": {
    "electricity": { "coverage": 1.0 },
    "pollution":   { "coverage": 0.23 },
    "water":       { "coverage": 0.8 }
  }
}
```

The full `layers` dict is sent from the looked-up document (via `full_document="updateLookup"`). In Phase 3a, only `layers.pollution.coverage` is written by the simulation worker — `electricity` and `water` layers will be `{}` until those simulation paths are implemented. The client must treat absent coverage keys as `0.0`.

### `chunk_update`

Fired when `chunks.base.buildings` is updated (build action). In Phase 3a, only `place_building` writes to this field — `place_road`, `place_zone`, and `demolish` are stubs and will not trigger this event until implemented in a later phase.

```json
{
  "city_id": "<str>",
  "chunk_x": 2,
  "chunk_y": 3,
  "buildings": [ ... ],
  "roads": [ ... ]
}
```

The full `base.buildings` and `base.roads` arrays are sent. The terrain grid (`base.terrain`) is excluded — it never changes after initial creation.

---

## Resume Tokens

Each stream stores its resume token after processing every event. If the Motor connection drops, the stream reopens using the last stored token so no events are missed during a transient disconnect.

Tokens are held in memory only. A full process restart will lose the in-flight token and may miss events that occurred during the downtime. This is acceptable for Phase 3a — the simulation tick runs every 10 seconds, so state converges quickly after reconnection.

---

## Error Handling

- If a stream raises an exception, the background task logs the error and reopens that stream from scratch after a 5-second backoff.
- If `watch_changes()` itself raises an unhandled exception, the FastAPI lifespan cancels it cleanly on shutdown.
- Atlas change streams can expire after an idle period (7 days by default). The reconnect logic handles this transparently.

---

## Components

### `backend/app/change_stream.py` (new)

Single public coroutine:

```python
async def watch_changes(sio: socketio.AsyncServer, mongo_url: str, db_name: str) -> None:
```

Internally starts two stream watchers as independent `asyncio.Task` objects (not `asyncio.gather` — if one watcher crashes before its internal retry loop catches it, gather would cancel the other):

```python
chunk_task = asyncio.create_task(_watch_chunks(sio, db))
city_task = asyncio.create_task(_watch_cities(sio, db))
try:
    await asyncio.gather(chunk_task, city_task)
finally:
    chunk_task.cancel()
    city_task.cancel()
    await asyncio.gather(chunk_task, city_task, return_exceptions=True)
```

Each watcher is a `while True` loop that opens a stream, iterates events, emits to `sio`, and stores the resume token. On any exception inside the loop, it logs the error, sleeps 5s, and retries — the outer task never exits unless cancelled.

Helper to extract `city_id` from a chunk document:
- Chunks store `city_id` as an `ObjectId` — convert to `str` for the room name and payload.

### `backend/app/main.py` (modified)

Add to the lifespan context manager:

```python
task = asyncio.create_task(
    watch_changes(sio, settings.mongodb_url, settings.mongodb_db_name)
)
yield
task.cancel()
try:
    await task
except asyncio.CancelledError:
    pass
```

---

## Testing Strategy

| Test | What | How |
|---|---|---|
| Unit | `layers_update` emitted on chunk layers write | Mock Motor stream yielding a synthetic change event; assert `sio.emit` called with correct payload |
| Unit | `chunk_update` emitted on chunk base.buildings write | Same pattern |
| Unit | `stats_update` emitted on city global_stats write | Same pattern |
| Unit | Irrelevant field update skipped | Mock event with only `last_updated` in updatedFields; assert `sio.emit` not called |
| Unit | Stream exception triggers reconnect | Mock stream raising an exception; assert task does not crash, retries after backoff |

Motor change streams are not integration-tested in CI (requires live Atlas with change stream access). A manual smoke test against the Atlas staging cluster verifies end-to-end behaviour.

---

## What Is NOT in Scope

- Viewport-based filtering (per-client chunk subscriptions) — Phase 3b
- Lazy chunk loading on viewport scroll — Phase 3b
- View modes (base / electricity / pollution / water) — frontend concern, no backend changes needed
- Socket.IO Redis adapter for horizontal scaling — Phase 6
- Broadcasting to individual players (currently broadcasts to entire city room) — Phase 3b

---

## Files Created / Modified

| File | Change |
|---|---|
| `backend/app/change_stream.py` | New — `watch_changes()` + routing logic |
| `backend/app/main.py` | Modified — start/stop `watch_changes()` in lifespan |
| `backend/tests/test_change_stream.py` | New — unit tests with mocked Motor streams |

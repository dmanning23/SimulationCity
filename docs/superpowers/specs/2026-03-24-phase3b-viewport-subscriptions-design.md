# Phase 3b: Viewport-Based Data Delivery — Design Spec

**Date:** 2026-03-24
**Scope:** Week 6 of the SimulationCity development roadmap
**Status:** Approved

---

## Overview

Phase 3a broadcasts every chunk and city change to all players in a city room. Phase 3b narrows delivery to what each player's camera can actually see. A new `update_viewport` Socket.IO event lets clients declare their visible bounding box; the server tracks per-session chunk subscriptions and routes change stream events only to interested sessions.

Scope: backend only. Frontend Phaser camera integration and chunk lazy-loading are deferred.

---

## Architecture & Data Flow

```
Client
  │
  │  emit update_viewport {city_id, min_x, min_y, max_x, max_y}
  ▼
app/socket_handlers.py :: handle_update_viewport()
  │  1. Validate bbox and city membership
  │  2. Expand bbox → set of chunk keys
  │  3. Diff vs previous subscription (added, removed)
  │  4. Update viewport_store (both indexes)
  │  5. Fetch chunk documents for added chunks from MongoDB
  │  6. Emit viewport_seed → back to this session only
  ▼
app/viewport_store.py  [module-level state]
  │  session_subscriptions: dict[str, set[str]]  ← session_id → {"city:x:y", ...}
  │  chunk_subscribers:    dict[str, set[str]]   ← "city:x:y" → {session_id, ...}
  ▼
app/change_stream.py :: watch_changes()  [modified]
  │  On chunk event: chunk_key = f"{city_id}:{x}:{y}"
  │  sessions = viewport_store.get_subscribers(chunk_key)
  │  → emit chunk_update / layers_update only to those sessions
  │
  │  On city event: stats_update still broadcasts to city:{city_id} room
  ▼
Connected clients (only those watching the affected chunk)
```

---

## New Module: `app/viewport_store.py`

Module-level dicts shared across the process. No class wrapper needed — all access is from async coroutines on the same event loop, so no locking is required.

```python
session_subscriptions: dict[str, set[str]] = {}  # session_id → set of chunk keys
chunk_subscribers: dict[str, set[str]] = {}        # chunk_key → set of session_ids

def update_viewport(
    session_id: str,
    city_id: str,
    min_x: int, min_y: int,
    max_x: int, max_y: int,
) -> tuple[set[str], set[str]]:
    """
    Replaces the subscription for session_id with the chunks in the given bbox.
    Returns (added_chunk_keys, removed_chunk_keys).
    """

def remove_session(session_id: str) -> None:
    """Removes session from both indexes. No-op if session not present."""

def get_subscribers(chunk_key: str) -> set[str]:
    """Returns the set of session IDs subscribed to a chunk. O(1) lookup."""
```

### Chunk key format

```
f"{city_id}:{x}:{y}"
```

### Bbox expansion

```python
{f"{city_id}:{x}:{y}" for x in range(min_x, max_x + 1) for y in range(min_y, max_y + 1)}
```

---

## Socket.IO Events

### `update_viewport` (client → server)

```json
{
  "city_id": "abc123",
  "min_x": 0,
  "min_y": 0,
  "max_x": 6,
  "max_y": 6
}
```

Handler steps:
1. Verify the session is authenticated and joined to `city:{city_id}`
2. Validate that all bbox fields are integers and `max >= min`
3. Call `viewport_store.update_viewport(...)` → get `(added, removed)`
4. Fetch MongoDB chunk documents for chunks in `added` (project to `x`, `y`, `base`, `layers`, `version`)
5. Emit `viewport_seed` to the session

### `viewport_seed` (server → requesting session only)

```json
{
  "city_id": "abc123",
  "chunks": [
    { "x": 3, "y": 4, "base": { "buildings": [...] }, "layers": { "pollution": {...} }, "version": 17 },
    ...
  ]
}
```

`chunks` contains only newly-visible chunks (delta from previous subscription). If the camera moved within already-loaded territory, `chunks` is an empty list.

### Modified: `layers_update` and `chunk_update`

Previously emitted to the `city:{city_id}` room. Now delivered only to subscribed sessions:

```python
# Phase 3b delivery
chunk_key = f"{city_id}:{chunk_x}:{chunk_y}"
for sid in viewport_store.get_subscribers(chunk_key):
    await sio.emit(event_name, payload, to=sid)
```

### Unchanged: `stats_update`

Continues to broadcast to the full `city:{city_id}` room. Treasury, population, and happiness are city-wide data that all players need regardless of viewport.

---

## Disconnect Cleanup

The existing disconnect handler is extended to call:

```python
viewport_store.remove_session(session_id)
```

This runs even if the session never sent `update_viewport` (no-op). It ensures no ghost entries accumulate in `chunk_subscribers` after a session ends.

---

## Error Handling

| Condition | Response |
|---|---|
| Non-integer bbox field | Emit `error` to session; no state change |
| `max_x < min_x` or `max_y < min_y` | Emit `error` to session; no state change |
| `city_id` session is not joined to | Emit `error` to session; no state change |
| Chunk not found in DB during seed fetch | Skip silently; do not fail the whole seed |
| `get_subscribers` for unknown chunk key | Return empty set; no emit |

---

## Testing

### Unit tests — `tests/test_viewport_store.py`

- `update_viewport` populates `session_subscriptions` and `chunk_subscribers` correctly
- Second call replaces subscription; only changed entries appear in returned diff
- Disjoint bbox move: all old chunks returned as removed, all new chunks as added
- Overlapping bbox move: overlap chunks not in added or removed
- `remove_session` clears both indexes completely; no orphan entries
- `get_subscribers` returns correct session set after multiple sessions subscribe

### Integration tests — `tests/test_viewport_socket.py`

Following the existing Phase 3a pattern (AsyncMock sio, test MongoDB):

- `update_viewport` emits `viewport_seed` with correct chunks for the bbox
- Second `update_viewport` with overlapping bbox: seed contains only new chunks
- Disconnect clears subscriptions; subsequent chunk change not emitted to disconnected session
- Two sessions with non-overlapping viewports: chunk update only reaches the watching session
- `stats_update` still delivered to all sessions in the city room regardless of viewport

---

## What's Not in Scope

- Frontend: Phaser camera emitting `update_viewport` on scroll — Phase 3b frontend
- View mode switching (base / electricity / pollution / water) — Phase 3b frontend
- Horizontal scaling: subscription state is in-process. The Redis Socket.IO adapter (Phase 6) will resolve multi-dyno consistency.

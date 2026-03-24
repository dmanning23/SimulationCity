# Phase 3b: Viewport Subscriptions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-session chunk subscription management so change stream events are delivered only to sessions whose camera can see the affected chunk.

**Architecture:** A new `viewport_store` module maintains two in-memory indexes (session→chunks, chunk→sessions). The `update_viewport` Socket.IO event replaces an existing stub: it validates a bbox, diffs subscriptions, seeds newly-visible chunks from MongoDB, and keeps both indexes up to date. `_watch_chunks` in `change_stream.py` switches from room broadcast to per-session emit via `viewport_store.get_subscribers()`. Sessions are cleaned up on `leave_city` and `disconnect`.

**Tech Stack:** Python 3.12, FastAPI, python-socketio 5.x, Motor/Beanie (MongoDB), pytest-asyncio, unittest.mock

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `backend/app/viewport_store.py` | Two in-memory dicts + 3 pure functions |
| Create | `backend/tests/test_viewport_store.py` | Unit tests for viewport_store (no I/O) |
| Modify | `backend/app/socket_handlers.py` | Replace `update_viewport` stub; add lifecycle hooks to `join_city`, `leave_city`, `disconnect` |
| Create | `backend/tests/test_viewport_socket.py` | Handler tests for lifecycle + `update_viewport` |
| Modify | `backend/app/change_stream.py` | Switch `_watch_chunks` from room emit to per-session loop |
| Modify | `backend/tests/test_change_stream.py` | Update assertions in existing watcher tests |

---

## Task 1: viewport_store module

The foundation. Pure Python — no async, no I/O. All tests run without MongoDB or a running server.

**Files:**
- Create: `backend/app/viewport_store.py`
- Create: `backend/tests/test_viewport_store.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_viewport_store.py`:

```python
"""Unit tests for viewport_store — pure Python, no I/O."""
import pytest
import app.viewport_store as store
from app.viewport_store import update_viewport, remove_session, get_subscribers


@pytest.fixture(autouse=True)
def clear_store():
    store.session_subscriptions.clear()
    store.chunk_subscribers.clear()
    yield
    store.session_subscriptions.clear()
    store.chunk_subscribers.clear()


def test_first_call_adds_all_bbox_chunks():
    added, removed = update_viewport("sid1", "city1", 0, 0, 1, 1)
    expected = {"city1:0:0", "city1:0:1", "city1:1:0", "city1:1:1"}
    assert added == expected
    assert removed == set()
    assert store.session_subscriptions["sid1"] == expected
    for key in expected:
        assert "sid1" in store.chunk_subscribers[key]


def test_overlapping_move_only_diffs_change():
    update_viewport("sid1", "city1", 0, 0, 2, 2)   # 3×3 grid
    added, removed = update_viewport("sid1", "city1", 1, 1, 3, 3)  # shift right+down

    overlap = {"city1:1:1", "city1:1:2", "city1:2:1", "city1:2:2"}
    for key in overlap:
        assert key not in added and key not in removed

    assert "city1:3:3" in added    # new corner
    assert "city1:0:0" in removed  # old corner


def test_disjoint_move_replaces_all():
    update_viewport("sid1", "city1", 0, 0, 0, 0)
    added, removed = update_viewport("sid1", "city1", 5, 5, 5, 5)
    assert added == {"city1:5:5"}
    assert removed == {"city1:0:0"}
    assert "sid1" not in store.chunk_subscribers.get("city1:0:0", set())
    assert "sid1" in store.chunk_subscribers.get("city1:5:5", set())


def test_remove_session_clears_both_indexes():
    update_viewport("sid1", "city1", 0, 0, 1, 1)
    remove_session("sid1")
    assert "sid1" not in store.session_subscriptions
    for subscribers in store.chunk_subscribers.values():
        assert "sid1" not in subscribers


def test_remove_session_noop_for_unknown_session():
    remove_session("ghost-sid")  # must not raise


def test_get_subscribers_returns_all_watching_sessions():
    update_viewport("sid1", "city1", 0, 0, 0, 0)
    update_viewport("sid2", "city1", 0, 0, 0, 0)
    subs = get_subscribers("city1:0:0")
    assert "sid1" in subs and "sid2" in subs


def test_get_subscribers_unknown_key_returns_empty_set():
    assert get_subscribers("city1:99:99") == set()


def test_get_subscribers_isolates_non_watching_sessions():
    update_viewport("sid1", "city1", 0, 0, 0, 0)
    update_viewport("sid2", "city1", 5, 5, 5, 5)
    assert get_subscribers("city1:0:0") == {"sid1"}
    assert get_subscribers("city1:5:5") == {"sid2"}


def test_remove_session_does_not_affect_other_sessions():
    update_viewport("sid1", "city1", 0, 0, 0, 0)
    update_viewport("sid2", "city1", 0, 0, 0, 0)
    remove_session("sid1")
    assert get_subscribers("city1:0:0") == {"sid2"}
```

- [ ] **Step 2: Run tests — expect all to fail with ImportError**

```bash
cd backend && uv run pytest tests/test_viewport_store.py -v
```
Expected: `ImportError: cannot import name 'update_viewport' from 'app.viewport_store'`

- [ ] **Step 3: Implement viewport_store.py**

Create `backend/app/viewport_store.py`:

```python
"""Per-session chunk subscription store.

Two in-memory indexes, kept in sync:
  session_subscriptions: session_id → set of chunk keys ("city_id:x:y")
  chunk_subscribers:     chunk_key  → set of session IDs

All access is from async coroutines on the same event loop — no locking needed.
"""

session_subscriptions: dict[str, set[str]] = {}
chunk_subscribers: dict[str, set[str]] = {}


def update_viewport(
    session_id: str,
    city_id: str,
    min_x: int,
    min_y: int,
    max_x: int,
    max_y: int,
) -> tuple[set[str], set[str]]:
    """Replace the subscription for session_id with the chunks in the given bbox.

    Returns (added_chunk_keys, removed_chunk_keys).
    """
    new_keys = {
        f"{city_id}:{x}:{y}"
        for x in range(min_x, max_x + 1)
        for y in range(min_y, max_y + 1)
    }
    old_keys = session_subscriptions.get(session_id, set())

    added = new_keys - old_keys
    removed = old_keys - new_keys

    session_subscriptions[session_id] = new_keys

    for key in added:
        chunk_subscribers.setdefault(key, set()).add(session_id)

    for key in removed:
        sids = chunk_subscribers.get(key)
        if sids:
            sids.discard(session_id)
            if not sids:
                del chunk_subscribers[key]

    return added, removed


def remove_session(session_id: str) -> None:
    """Remove session from both indexes. No-op if session not present."""
    keys = session_subscriptions.pop(session_id, set())
    for key in keys:
        sids = chunk_subscribers.get(key)
        if sids:
            sids.discard(session_id)
            if not sids:
                del chunk_subscribers[key]


def get_subscribers(chunk_key: str) -> set[str]:
    """Return a copy of the set of session IDs subscribed to chunk_key. O(1)."""
    return set(chunk_subscribers.get(chunk_key, set()))
```

- [ ] **Step 4: Run tests — expect all to pass**

```bash
cd backend && uv run pytest tests/test_viewport_store.py -v
```
Expected: 9 PASSED

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/viewport_store.py tests/test_viewport_store.py
git commit -m "feat: add viewport_store module with dual-index subscription management"
```

---

## Task 2: Session lifecycle hooks

Wire `viewport_store` into `join_city`, `leave_city`, and `disconnect`. Tests go in a new file that follows the same pattern as `test_socket_build_action.py`.

**Files:**
- Modify: `backend/app/socket_handlers.py`
- Create: `backend/tests/test_viewport_socket.py` (lifecycle portion only)

- [ ] **Step 1: Write failing lifecycle tests**

Create `backend/tests/test_viewport_socket.py`:

```python
"""Tests for viewport subscription lifecycle: join, leave, disconnect."""
import pytest
from unittest.mock import AsyncMock, patch
from bson import ObjectId

import app.viewport_store as store
from app.socket_handlers import sio

_FAKE_SID = "test-sid-viewport"
_FAKE_USER_ID = str(ObjectId("000000000000000000000010"))
_FAKE_CITY_ID = str(ObjectId("000000000000000000000020"))


def _get_handler(event: str):
    handler = sio.handlers.get("/", {}).get(event)
    if handler is None:
        raise RuntimeError(f"Event '{event}' not registered on sio")
    return handler


@pytest.fixture(autouse=True)
def clear_store():
    store.session_subscriptions.clear()
    store.chunk_subscribers.clear()
    yield
    store.session_subscriptions.clear()
    store.chunk_subscribers.clear()


# ---------------------------------------------------------------------------
# join_city: initial subscription registered
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_join_city_registers_initial_viewport(db):
    """join_city with viewport registers subscription so change stream works immediately."""
    from app.models.city import City
    from app.models.player import Player
    from beanie import PydanticObjectId

    owner_id = PydanticObjectId(_FAKE_USER_ID)
    city = City(
        name="Test City",
        owner_id=owner_id,
        collaborators=[],
        global_stats={"population": 0, "treasury": 0.0, "happiness": 50},
        settings={"design_style": "default"},
    )
    await city.insert()
    city_id = str(city.id)

    handler = _get_handler("join_city")
    session = {"user_id": _FAKE_USER_ID}

    with patch.object(sio, "get_session", new=AsyncMock(return_value=session)), \
         patch.object(sio, "enter_room", new=AsyncMock()), \
         patch.object(sio, "save_session", new=AsyncMock()), \
         patch.object(sio, "emit", new=AsyncMock()):
        await handler(_FAKE_SID, {
            "city_id": city_id,
            "viewport": {"chunkX": 2, "chunkY": 2, "radius": 1},
        })

    subs = store.session_subscriptions.get(_FAKE_SID, set())
    assert f"{city_id}:2:2" in subs
    assert f"{city_id}:1:1" in subs
    assert f"{city_id}:3:3" in subs


@pytest.mark.asyncio
async def test_join_city_registers_default_viewport_when_none(db):
    """join_city with no viewport uses 4×4 default at origin."""
    from app.models.city import City
    from beanie import PydanticObjectId

    city = City(
        name="Test City",
        owner_id=PydanticObjectId(_FAKE_USER_ID),
        collaborators=[],
        global_stats={"population": 0, "treasury": 0.0, "happiness": 50},
        settings={"design_style": "default"},
    )
    await city.insert()
    city_id = str(city.id)

    handler = _get_handler("join_city")
    session = {"user_id": _FAKE_USER_ID}

    with patch.object(sio, "get_session", new=AsyncMock(return_value=session)), \
         patch.object(sio, "enter_room", new=AsyncMock()), \
         patch.object(sio, "save_session", new=AsyncMock()), \
         patch.object(sio, "emit", new=AsyncMock()):
        await handler(_FAKE_SID, {"city_id": city_id})

    subs = store.session_subscriptions.get(_FAKE_SID, set())
    # radius=2 default: min=max(0,0-2)=0, max=0+2=2 → bbox [0,0]–[2,2]
    assert f"{city_id}:0:0" in subs
    assert f"{city_id}:2:2" in subs


# ---------------------------------------------------------------------------
# leave_city: subscription removed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_leave_city_removes_viewport_subscription():
    """leave_city clears the session from viewport_store."""
    store.session_subscriptions[_FAKE_SID] = {f"{_FAKE_CITY_ID}:0:0"}
    store.chunk_subscribers[f"{_FAKE_CITY_ID}:0:0"] = {_FAKE_SID}

    handler = _get_handler("leave_city")
    session = {"user_id": _FAKE_USER_ID, "city_id": _FAKE_CITY_ID}

    with patch.object(sio, "get_session", new=AsyncMock(return_value=session)), \
         patch.object(sio, "leave_room", new=AsyncMock()), \
         patch.object(sio, "save_session", new=AsyncMock()), \
         patch.object(sio, "emit", new=AsyncMock()):
        await handler(_FAKE_SID)

    assert _FAKE_SID not in store.session_subscriptions
    assert _FAKE_SID not in store.chunk_subscribers.get(f"{_FAKE_CITY_ID}:0:0", set())


# ---------------------------------------------------------------------------
# disconnect: subscription removed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disconnect_removes_viewport_subscription():
    """disconnect clears the session from viewport_store."""
    store.session_subscriptions[_FAKE_SID] = {f"{_FAKE_CITY_ID}:0:0"}
    store.chunk_subscribers[f"{_FAKE_CITY_ID}:0:0"] = {_FAKE_SID}

    handler = _get_handler("disconnect")
    session = {"user_id": _FAKE_USER_ID, "city_id": _FAKE_CITY_ID}

    with patch.object(sio, "get_session", new=AsyncMock(return_value=session)), \
         patch.object(sio, "leave_room", new=AsyncMock()), \
         patch.object(sio, "emit", new=AsyncMock()):
        await handler(_FAKE_SID)

    assert _FAKE_SID not in store.session_subscriptions
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd backend && uv run pytest tests/test_viewport_socket.py -v
```
Expected: FAILED — `leave_city` and `disconnect` handlers don't call `remove_session` yet; `join_city` doesn't call `update_viewport` yet.

- [ ] **Step 3: Wire viewport_store into socket_handlers.py**

Add import at the top of `backend/app/socket_handlers.py` (after existing imports):

```python
from app import viewport_store
```

In `join_city`, after `await sio.save_session(sid, {**session, "city_id": city_id})` (the line that sets city_id in session), add:

```python
    # Register initial viewport subscription so change stream delivery works immediately.
    # Converts the chunkX/chunkY/radius format from join_city into a bbox.
    vp = data.get("viewport") or {}
    cx = int(vp.get("chunkX", 0))
    cy = int(vp.get("chunkY", 0))
    radius = int(vp.get("radius", 2))
    viewport_store.update_viewport(
        sid, city_id,
        max(0, cx - radius), max(0, cy - radius),
        cx + radius, cy + radius,
    )
```

In `leave_city`, at the start of the `if city_id:` block, before `await sio.leave_room(...)`, add:

```python
        viewport_store.remove_session(sid)
```

In `disconnect`, at the end of the handler (after all existing logic), add:

```python
    viewport_store.remove_session(sid)
```

- [ ] **Step 4: Run tests — expect all to pass**

```bash
cd backend && uv run pytest tests/test_viewport_socket.py -v
```
Expected: all lifecycle tests PASSED

- [ ] **Step 5: Run full suite to check for regressions**

```bash
cd backend && uv run pytest -v
```
Expected: all existing tests still pass

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/socket_handlers.py tests/test_viewport_socket.py
git commit -m "feat: wire viewport_store into join_city, leave_city, and disconnect"
```

---

## Task 3: update_viewport handler

Replace the 5-line stub at lines 171–177 of `socket_handlers.py` with the full implementation: validate bbox, diff subscriptions, seed newly-visible chunks from MongoDB, emit `viewport_seed`.

**Files:**
- Modify: `backend/app/socket_handlers.py`
- Modify: `backend/tests/test_viewport_socket.py` (append new tests)

- [ ] **Step 1: Write the failing handler tests**

Append to `backend/tests/test_viewport_socket.py`:

```python
# ---------------------------------------------------------------------------
# update_viewport: bbox validation, seeding, subscription update
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_viewport_seeds_new_chunks(db):
    """update_viewport emits viewport_seed containing newly-visible chunk docs."""
    from app.models.city import City
    from app.models.chunk import Chunk
    from beanie import PydanticObjectId

    city = City(
        name="Seed City",
        owner_id=PydanticObjectId(_FAKE_USER_ID),
        collaborators=[],
        global_stats={"population": 0, "treasury": 0.0, "happiness": 50},
        settings={"design_style": "default"},
    )
    await city.insert()
    city_id = str(city.id)

    chunk = Chunk(
        city_id=city.id,
        coordinates={"x": 0, "y": 0},
        base={"buildings": [], "roads": [], "terrain": [[0] * 16 for _ in range(16)]},
        layers={"electricity": {}, "pollution": {}, "water": {}},
        version=1,
    )
    await chunk.insert()

    handler = _get_handler("update_viewport")
    session = {"user_id": _FAKE_USER_ID, "city_id": city_id}
    emitted = []

    async def capture(event, data, to=None, **kwargs):
        emitted.append({"name": event, "data": data})

    with patch.object(sio, "get_session", new=AsyncMock(return_value=session)), \
         patch.object(sio, "emit", side_effect=capture):
        await handler(_FAKE_SID, {
            "city_id": city_id,
            "min_x": 0, "min_y": 0, "max_x": 1, "max_y": 1,
        })

    seed = next((e for e in emitted if e["name"] == "viewport_seed"), None)
    assert seed is not None, f"Expected viewport_seed, got: {[e['name'] for e in emitted]}"
    assert seed["data"]["city_id"] == city_id
    # Chunk.model_dump(mode="json") serializes ChunkCoordinates as {"x": int, "y": int}
    # under the "coordinates" key — same shape as the raw MongoDB document.
    chunk_coords = [(c["coordinates"]["x"], c["coordinates"]["y"]) for c in seed["data"]["chunks"]]
    assert (0, 0) in chunk_coords
    assert f"{city_id}:0:0" in store.session_subscriptions.get(_FAKE_SID, set())


@pytest.mark.asyncio
async def test_update_viewport_second_call_seeds_only_new_chunks(db):
    """Second update_viewport with overlapping bbox seeds only the new chunks."""
    from app.models.city import City
    from app.models.chunk import Chunk
    from beanie import PydanticObjectId

    city = City(
        name="Delta City",
        owner_id=PydanticObjectId(_FAKE_USER_ID),
        collaborators=[],
        global_stats={"population": 0, "treasury": 0.0, "happiness": 50},
        settings={"design_style": "default"},
    )
    await city.insert()
    city_id = str(city.id)

    for x, y in [(0, 0), (1, 0), (0, 1), (1, 1)]:
        await Chunk(
            city_id=city.id,
            coordinates={"x": x, "y": y},
            base={"buildings": [], "roads": [], "terrain": [[0] * 16 for _ in range(16)]},
            layers={"electricity": {}, "pollution": {}, "water": {}},
            version=1,
        ).insert()

    handler = _get_handler("update_viewport")
    session = {"user_id": _FAKE_USER_ID, "city_id": city_id}

    async def noop_emit(event, data, to=None, **kwargs):
        pass

    # First call: subscribe to (0,0)-(1,1)
    with patch.object(sio, "get_session", new=AsyncMock(return_value=session)), \
         patch.object(sio, "emit", side_effect=noop_emit):
        await handler(_FAKE_SID, {
            "city_id": city_id,
            "min_x": 0, "min_y": 0, "max_x": 1, "max_y": 1,
        })

    # Second call: move to (1,1)-(2,2) — overlap at (1,1), new: (2,1),(1,2),(2,2)
    emitted = []

    async def capture(event, data, to=None, **kwargs):
        emitted.append({"name": event, "data": data})

    with patch.object(sio, "get_session", new=AsyncMock(return_value=session)), \
         patch.object(sio, "emit", side_effect=capture):
        await handler(_FAKE_SID, {
            "city_id": city_id,
            "min_x": 1, "min_y": 1, "max_x": 2, "max_y": 2,
        })

    seed = next((e for e in emitted if e["name"] == "viewport_seed"), None)
    assert seed is not None
    seeded_coords = {(c["coordinates"]["x"], c["coordinates"]["y"]) for c in seed["data"]["chunks"]}
    assert (0, 0) not in seeded_coords  # already had this
    assert (1, 1) not in seeded_coords  # overlap — already had this


@pytest.mark.asyncio
async def test_update_viewport_error_when_not_joined():
    """update_viewport emits error when session has no city_id."""
    handler = _get_handler("update_viewport")
    session = {"user_id": _FAKE_USER_ID}  # no city_id
    emitted = []

    async def capture(event, data, to=None, **kwargs):
        emitted.append({"name": event, "data": data})

    with patch.object(sio, "get_session", new=AsyncMock(return_value=session)), \
         patch.object(sio, "emit", side_effect=capture):
        await handler(_FAKE_SID, {
            "city_id": _FAKE_CITY_ID,
            "min_x": 0, "min_y": 0, "max_x": 1, "max_y": 1,
        })

    assert any(e["name"] == "error" for e in emitted)
    assert _FAKE_SID not in store.session_subscriptions


@pytest.mark.asyncio
async def test_update_viewport_error_on_city_id_mismatch():
    """update_viewport emits error when payload city_id doesn't match session."""
    handler = _get_handler("update_viewport")
    session = {"user_id": _FAKE_USER_ID, "city_id": _FAKE_CITY_ID}
    emitted = []

    async def capture(event, data, to=None, **kwargs):
        emitted.append({"name": event, "data": data})

    with patch.object(sio, "get_session", new=AsyncMock(return_value=session)), \
         patch.object(sio, "emit", side_effect=capture):
        await handler(_FAKE_SID, {
            "city_id": str(ObjectId("000000000000000000000099")),  # wrong city
            "min_x": 0, "min_y": 0, "max_x": 1, "max_y": 1,
        })

    assert any(e["name"] == "error" for e in emitted)


@pytest.mark.asyncio
async def test_update_viewport_error_on_invalid_bbox():
    """update_viewport emits error for non-integer bbox fields."""
    handler = _get_handler("update_viewport")
    session = {"user_id": _FAKE_USER_ID, "city_id": _FAKE_CITY_ID}
    emitted = []

    async def capture(event, data, to=None, **kwargs):
        emitted.append({"name": event, "data": data})

    with patch.object(sio, "get_session", new=AsyncMock(return_value=session)), \
         patch.object(sio, "emit", side_effect=capture):
        await handler(_FAKE_SID, {
            "city_id": _FAKE_CITY_ID,
            "min_x": "bad", "min_y": 0, "max_x": 1, "max_y": 1,
        })

    assert any(e["name"] == "error" for e in emitted)


@pytest.mark.asyncio
async def test_update_viewport_error_on_inverted_bbox():
    """update_viewport emits error when max < min."""
    handler = _get_handler("update_viewport")
    session = {"user_id": _FAKE_USER_ID, "city_id": _FAKE_CITY_ID}
    emitted = []

    async def capture(event, data, to=None, **kwargs):
        emitted.append({"name": event, "data": data})

    with patch.object(sio, "get_session", new=AsyncMock(return_value=session)), \
         patch.object(sio, "emit", side_effect=capture):
        await handler(_FAKE_SID, {
            "city_id": _FAKE_CITY_ID,
            "min_x": 5, "min_y": 0, "max_x": 0, "max_y": 1,  # max_x < min_x
        })

    assert any(e["name"] == "error" for e in emitted)


@pytest.mark.asyncio
async def test_update_viewport_error_on_oversized_bbox():
    """update_viewport emits error when bbox exceeds 20×20."""
    handler = _get_handler("update_viewport")
    session = {"user_id": _FAKE_USER_ID, "city_id": _FAKE_CITY_ID}
    emitted = []

    async def capture(event, data, to=None, **kwargs):
        emitted.append({"name": event, "data": data})

    with patch.object(sio, "get_session", new=AsyncMock(return_value=session)), \
         patch.object(sio, "emit", side_effect=capture):
        await handler(_FAKE_SID, {
            "city_id": _FAKE_CITY_ID,
            "min_x": 0, "min_y": 0, "max_x": 20, "max_y": 20,  # 21×21 > 20×20
        })

    assert any(e["name"] == "error" for e in emitted)
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd backend && uv run pytest tests/test_viewport_socket.py -v
```
Expected: new `update_viewport` tests FAIL — the stub doesn't emit `viewport_seed`.

- [ ] **Step 3: Replace the update_viewport stub**

In `backend/app/socket_handlers.py`, replace the `update_viewport` handler (lines 171–177):

```python
@sio.event
async def update_viewport(sid: str, data: dict):
    """Replace the viewport subscription for this session and seed newly-visible chunks."""
    session = await sio.get_session(sid)
    city_id = session.get("city_id") if session else None
    if not city_id:
        await sio.emit("error", {"message": "Must be joined to a city first"}, to=sid)
        return

    payload_city_id = str(data.get("city_id", ""))
    if payload_city_id != str(city_id):
        await sio.emit("error", {"message": "city_id does not match joined city"}, to=sid)
        return

    try:
        min_x = int(data["min_x"])
        min_y = int(data["min_y"])
        max_x = int(data["max_x"])
        max_y = int(data["max_y"])
    except (KeyError, TypeError, ValueError):
        await sio.emit("error", {"message": "min_x, min_y, max_x, max_y must be integers"}, to=sid)
        return

    if max_x < min_x or max_y < min_y:
        await sio.emit("error", {"message": "max must be >= min"}, to=sid)
        return

    if (max_x - min_x + 1) > 20 or (max_y - min_y + 1) > 20:
        await sio.emit("error", {"message": "Viewport exceeds maximum size of 20×20 chunks"}, to=sid)
        return

    added, _removed = viewport_store.update_viewport(sid, city_id, min_x, min_y, max_x, max_y)

    chunks: list[dict] = []
    if added:
        # $or query to fetch exactly the added (x, y) pairs (non-rectangular diffs need this)
        coord_conditions = [
            {"coordinates.x": int(k.split(":")[1]), "coordinates.y": int(k.split(":")[2])}
            for k in added
        ]
        results = await Chunk.find(
            {"city_id": PydanticObjectId(city_id), "$or": coord_conditions}
        ).to_list()
        chunks = [c.model_dump(mode="json") for c in results]

    await sio.emit("viewport_seed", {"city_id": city_id, "chunks": chunks}, to=sid)
```

- [ ] **Step 4: Run all viewport socket tests — expect all to pass**

```bash
cd backend && uv run pytest tests/test_viewport_socket.py -v
```
Expected: all tests PASSED

- [ ] **Step 5: Run full suite to check for regressions**

```bash
cd backend && uv run pytest -v
```
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/socket_handlers.py tests/test_viewport_socket.py
git commit -m "feat: implement update_viewport handler with bbox validation and chunk seeding"
```

---

## Task 4: Change stream per-session delivery

Switch `_watch_chunks` from room broadcast to per-session emit via `viewport_store.get_subscribers()`. Update the existing watcher tests — they currently assert `room=...`; after this task they assert `to=session_id`.

**Files:**
- Modify: `backend/app/change_stream.py`
- Modify: `backend/tests/test_change_stream.py`

- [ ] **Step 1: Update the existing watcher tests to assert per-session delivery**

In `backend/tests/test_change_stream.py`, add at the top of the file (after existing imports):

```python
import app.viewport_store as _vp_store

_SUBSCRIBER_SID = "test-subscriber-sid"
```

Add a module-level fixture to manage store state (add after the existing helper functions, before the test functions):

```python
@pytest.fixture(autouse=True)
def clear_viewport_store():
    _vp_store.session_subscriptions.clear()
    _vp_store.chunk_subscribers.clear()
    yield
    _vp_store.session_subscriptions.clear()
    _vp_store.chunk_subscribers.clear()
```

Update `test_watch_chunks_emits_layers_update` — pre-populate the store and change the assertion:

```python
@pytest.mark.asyncio
async def test_watch_chunks_emits_layers_update():
    """_watch_chunks emits layers_update to subscribed sessions only."""
    from app.change_stream import _watch_chunks

    event = _chunk_change_event()  # city=_CITY_OID, x=0, y=0
    chunk_key = f"{_CITY_OID}:0:0"
    _vp_store.session_subscriptions[_SUBSCRIBER_SID] = {chunk_key}
    _vp_store.chunk_subscribers[chunk_key] = {_SUBSCRIBER_SID}

    mock_sio = AsyncMock()
    mock_collection = MagicMock()
    mock_collection.watch.return_value = _MockStream(event)
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    with pytest.raises(asyncio.CancelledError):
        await _watch_chunks(mock_sio, mock_db)

    mock_sio.emit.assert_called_once_with(
        "layers_update",
        {
            "city_id": str(_CITY_OID),
            "chunk_x": 0,
            "chunk_y": 0,
            "layers": {"electricity": {}, "pollution": {"coverage": 0.25}, "water": {}},
        },
        to=_SUBSCRIBER_SID,
    )
```

Add a new test after `test_watch_chunks_emits_layers_update`:

```python
@pytest.mark.asyncio
async def test_watch_chunks_not_emitted_when_no_subscriber():
    """_watch_chunks does not emit when no session is subscribed to the chunk."""
    from app.change_stream import _watch_chunks

    event = _chunk_change_event()  # store is empty — no subscribers
    mock_sio = AsyncMock()
    mock_collection = MagicMock()
    mock_collection.watch.return_value = _MockStream(event)
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    with pytest.raises(asyncio.CancelledError):
        await _watch_chunks(mock_sio, mock_db)

    mock_sio.emit.assert_not_called()
```

Replace `test_watch_chunks_retries_on_exception` in full (store setup must be added before `make_stream` is defined so the second-attempt event gets delivered):

```python
@pytest.mark.asyncio
async def test_watch_chunks_retries_on_exception():
    """_watch_chunks logs and reopens the stream after a non-cancel exception."""
    from app.change_stream import _watch_chunks

    chunk_key = f"{_CITY_OID}:0:0"
    _vp_store.session_subscriptions[_SUBSCRIBER_SID] = {chunk_key}
    _vp_store.chunk_subscribers[chunk_key] = {_SUBSCRIBER_SID}

    call_count = 0

    def make_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            class FailStream:
                async def __aenter__(self): return self
                async def __aexit__(self, *_): pass
                def __aiter__(self): return self
                async def __anext__(self): raise ConnectionError("stream died")
            return FailStream()
        return _MockStream(_chunk_change_event())

    mock_sio = AsyncMock()
    mock_collection = MagicMock()
    mock_collection.watch.side_effect = make_stream
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    with patch("app.change_stream.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(asyncio.CancelledError):
            await _watch_chunks(mock_sio, mock_db)

    assert call_count == 2
    mock_sio.emit.assert_called_once()
```

- [ ] **Step 2: Run change stream tests — expect failures on updated assertions**

```bash
cd backend && uv run pytest tests/test_change_stream.py -v
```
Expected: `test_watch_chunks_emits_layers_update` FAILS (assertion `room=...` vs `to=...`)

- [ ] **Step 3: Modify _watch_chunks in change_stream.py**

Add import at the top of `backend/app/change_stream.py` (after existing imports):

```python
from app import viewport_store
```

Replace the emit block inside `_watch_chunks` (the `if result:` block):

```python
                    if result:
                        event_name, payload = result
                        city_id = payload["city_id"]
                        chunk_x = payload.get("chunk_x")
                        chunk_y = payload.get("chunk_y")
                        if chunk_x is None or chunk_y is None:
                            logger.warning(
                                "chunk event for city %s missing coordinates — skipping delivery",
                                city_id,
                            )
                        else:
                            chunk_key = f"{city_id}:{chunk_x}:{chunk_y}"
                            for sid in viewport_store.get_subscribers(chunk_key):
                                await sio.emit(event_name, payload, to=sid)
```

The `_watch_cities` function is **not** changed — `stats_update` still broadcasts to the `city:{city_id}` room.

- [ ] **Step 4: Run change stream tests — expect all to pass**

```bash
cd backend && uv run pytest tests/test_change_stream.py -v
```
Expected: all tests PASSED

- [ ] **Step 5: Run full test suite**

```bash
cd backend && uv run pytest -v
```
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/change_stream.py tests/test_change_stream.py
git commit -m "feat: route chunk change stream events per-session via viewport_store"
```

---

## Done

All four tasks complete. The system now delivers `chunk_update` and `layers_update` events only to sessions subscribed to the affected chunk. `stats_update` remains a full room broadcast. Session cleanup runs on both `leave_city` and `disconnect`.

Verify end state:

```bash
cd backend && uv run pytest -v
```
Expected: all tests pass, no skips.

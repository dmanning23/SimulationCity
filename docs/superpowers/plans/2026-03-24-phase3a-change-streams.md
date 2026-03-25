# Phase 3a: Change Streams Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a MongoDB change stream listener that broadcasts real-time `layers_update`, `chunk_update`, and `stats_update` Socket.IO events to city rooms whenever simulation ticks or build actions write to MongoDB.

**Architecture:** An `asyncio` background task (`watch_changes`) starts in the FastAPI lifespan. It runs two concurrent Motor change stream watchers — one for `chunks`, one for `cities`. Each watcher loops forever, routing change events to Socket.IO rooms via pure routing helper functions. Results are broadcast to the `city:{city_id}` room; viewport filtering is deferred to Phase 3b.

**Tech Stack:** Python 3.12, Motor (async MongoDB driver, already a Beanie dependency), python-socketio 5, FastAPI lifespan, pytest-asyncio

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/app/change_stream.py` | Create | Public `watch_changes()` coroutine + routing helpers + watcher coroutines |
| `backend/app/main.py` | Modify | Start/stop `watch_changes()` in the lifespan context manager |
| `backend/tests/test_change_stream.py` | Create | Unit tests for routing functions and watcher coroutines |

---

## Task 1: Routing Helper Functions

Pure functions that map a raw MongoDB change event dict to a `(event_name, payload)` pair — or `None` to skip. No async, no DB, fully unit-testable.

**Files:**
- Create: `backend/app/change_stream.py`
- Create: `backend/tests/test_change_stream.py`

### Background: what MongoDB change events look like

`simulate_city_tick` writes:
- `{"$set": {"layers.pollution.coverage": 0.3, "last_updated": ...}}` → `updatedFields` = `{"layers.pollution.coverage": 0.3, "last_updated": ...}`
- `{"$set": {"global_stats.population": 11, "global_stats.treasury": 1001.1, ...}}` → `updatedFields` = `{"global_stats.population": 11, ...}`

`_handle_place_building` writes:
- `{"$push": {"base.buildings": {...}}}` → `updatedFields` = `{"base.buildings.3": {...}}` (index of the appended element)

Routing must use **prefix matching** (`startswith`), not exact key equality.

- [ ] **Step 1: Write the failing routing tests**

Create `backend/tests/test_change_stream.py`:

```python
"""Unit tests for change stream routing helpers."""
import pytest
from bson import ObjectId

_CITY_OID = ObjectId("000000000000000000000001")


# --- helpers ---

def _chunk_event(updated_fields: dict, full_doc: dict) -> dict:
    return {
        "operationType": "update",
        "_id": {"_data": "resume_token"},
        "updateDescription": {"updatedFields": updated_fields},
        "fullDocument": full_doc,
    }


def _city_event(updated_fields: dict, full_doc: dict) -> dict:
    return {
        "operationType": "update",
        "_id": {"_data": "resume_token"},
        "updateDescription": {"updatedFields": updated_fields},
        "fullDocument": full_doc,
    }


def _chunk_doc(city_id=_CITY_OID, x=2, y=3):
    return {
        "city_id": city_id,
        "coordinates": {"x": x, "y": y},
        "layers": {
            "electricity": {},
            "pollution": {"coverage": 0.3},
            "water": {},
        },
        "base": {
            "buildings": [{"id": "b1", "type": "residential"}],
            "roads": [],
            "terrain": [[0] * 16 for _ in range(16)],
        },
        "version": 1,
    }


def _city_doc(city_id=_CITY_OID):
    return {
        "_id": city_id,
        "global_stats": {"population": 11, "treasury": 1001.1, "happiness": 75},
        "last_updated": "...",
    }


# --- _route_chunk_event ---

def test_route_chunk_layers_returns_layers_update():
    from app.change_stream import _route_chunk_event
    event = _chunk_event(
        {"layers.pollution.coverage": 0.3, "last_updated": "..."},
        _chunk_doc(),
    )
    result = _route_chunk_event(event)
    assert result is not None
    name, payload = result
    assert name == "layers_update"
    assert payload["city_id"] == str(_CITY_OID)
    assert payload["chunk_x"] == 2
    assert payload["chunk_y"] == 3
    assert payload["layers"] == {
        "electricity": {},
        "pollution": {"coverage": 0.3},
        "water": {},
    }


def test_route_chunk_layers_not_suppressed_by_last_updated():
    """last_updated co-occurring with layers.* must not suppress the event."""
    from app.change_stream import _route_chunk_event
    event = _chunk_event(
        {"layers.pollution.coverage": 0.1, "last_updated": "...", "version": 2},
        _chunk_doc(),
    )
    result = _route_chunk_event(event)
    assert result is not None
    assert result[0] == "layers_update"


def test_route_chunk_push_buildings_returns_chunk_update():
    """$push generates base.buildings.<index> — must match the prefix."""
    from app.change_stream import _route_chunk_event
    doc = _chunk_doc()
    event = _chunk_event(
        {"base.buildings.0": {"id": "b1", "type": "residential"}, "last_updated": "..."},
        doc,
    )
    result = _route_chunk_event(event)
    assert result is not None
    name, payload = result
    assert name == "chunk_update"
    assert payload["city_id"] == str(_CITY_OID)
    assert payload["chunk_x"] == 2
    assert payload["chunk_y"] == 3
    assert payload["buildings"] == doc["base"]["buildings"]
    assert payload["roads"] == []
    assert "terrain" not in payload


def test_route_chunk_only_bookkeeping_skipped():
    from app.change_stream import _route_chunk_event
    event = _chunk_event({"last_updated": "...", "version": 2}, _chunk_doc())
    assert _route_chunk_event(event) is None


# --- _route_city_event ---

def test_route_city_global_stats_returns_stats_update():
    from app.change_stream import _route_city_event
    event = _city_event(
        {
            "global_stats.population": 11,
            "global_stats.treasury": 1001.1,
            "global_stats.happiness": 75,
            "last_updated": "...",
        },
        _city_doc(),
    )
    result = _route_city_event(event)
    assert result is not None
    name, payload = result
    assert name == "stats_update"
    assert payload["city_id"] == str(_CITY_OID)
    assert payload["population"] == 11
    assert payload["treasury"] == pytest.approx(1001.1)
    assert payload["happiness"] == 75


def test_route_city_only_last_updated_skipped():
    from app.change_stream import _route_city_event
    event = _city_event({"last_updated": "..."}, _city_doc())
    assert _route_city_event(event) is None
```

- [ ] **Step 2: Run — verify FAIL**

```bash
cd /Users/danmanning/Documents/Source/SimulationCity/backend && uv run pytest tests/test_change_stream.py -v
```

Expected: `ImportError: cannot import name '_route_chunk_event' from 'app.change_stream'` (module doesn't exist yet).

- [ ] **Step 3: Create `backend/app/change_stream.py`** — routing functions only

```python
"""MongoDB change stream listener — broadcasts real-time events to Socket.IO city rooms.

Routing uses prefix matching against updateDescription.updatedFields keys:
  - chunks: "layers.*"       → layers_update
  - chunks: "base.buildings.*" → chunk_update  ($push generates "base.buildings.<N>")
  - cities: "global_stats.*" → stats_update

Watchers and the public watch_changes() coroutine are in this same file (Task 2).
"""
import asyncio
import logging

import socketio

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Routing helpers — pure functions, no I/O
# ---------------------------------------------------------------------------

def _route_chunk_event(event: dict) -> tuple[str, dict] | None:
    """Return (socket_event_name, payload) for a chunk change event, or None to skip."""
    updated_fields = event.get("updateDescription", {}).get("updatedFields", {})
    keys = set(updated_fields.keys())

    full_doc = event.get("fullDocument") or {}
    city_id = str(full_doc.get("city_id", ""))
    coordinates = full_doc.get("coordinates", {})
    chunk_x = coordinates.get("x")
    chunk_y = coordinates.get("y")

    if any(k.startswith("layers.") for k in keys):
        return "layers_update", {
            "city_id": city_id,
            "chunk_x": chunk_x,
            "chunk_y": chunk_y,
            "layers": full_doc.get("layers", {}),
        }

    # $push to base.buildings generates keys like "base.buildings.3" — use prefix match
    if any(k.startswith("base.buildings.") for k in keys):
        base = full_doc.get("base", {})
        return "chunk_update", {
            "city_id": city_id,
            "chunk_x": chunk_x,
            "chunk_y": chunk_y,
            "buildings": base.get("buildings", []),
            "roads": base.get("roads", []),
        }

    return None


def _route_city_event(event: dict) -> tuple[str, dict] | None:
    """Return (socket_event_name, payload) for a city change event, or None to skip."""
    updated_fields = event.get("updateDescription", {}).get("updatedFields", {})
    keys = set(updated_fields.keys())

    if not any(k.startswith("global_stats.") for k in keys):
        return None

    full_doc = event.get("fullDocument") or {}
    city_id = str(full_doc.get("_id", ""))
    stats = full_doc.get("global_stats", {})

    return "stats_update", {
        "city_id": city_id,
        "population": stats.get("population", 0),
        "treasury": stats.get("treasury", 0.0),
        "happiness": stats.get("happiness", 0),
    }
```

- [ ] **Step 4: Run — verify PASS**

```bash
cd /Users/danmanning/Documents/Source/SimulationCity/backend && uv run pytest tests/test_change_stream.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/change_stream.py backend/tests/test_change_stream.py
git commit -m "feat: add change stream routing helpers with unit tests"
```

---

## Task 2: Watcher Coroutines + `watch_changes`

Add async watcher loops and the public `watch_changes` entry point to `change_stream.py`. Tests mock Motor streams using a helper class that yields synthetic events.

**Files:**
- Modify: `backend/app/change_stream.py`
- Modify: `backend/tests/test_change_stream.py`

### How to mock Motor change streams in tests

Motor's `collection.watch()` returns an async context manager. You iterate it with `async for`. The mock must implement `__aenter__`, `__aexit__`, `__aiter__`, and `__anext__`.

The watcher loops run forever — to make them exit cleanly in tests, raise `asyncio.CancelledError` from `__anext__` after yielding the test events. The watcher's `except asyncio.CancelledError: raise` clause re-raises it, terminating the task.

```python
class _MockStream:
    """Yields `events` then raises CancelledError to exit the infinite watcher loop."""
    def __init__(self, events):
        self._iter = iter(events)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise asyncio.CancelledError()
```

- [ ] **Step 1: Add watcher tests to `backend/tests/test_change_stream.py`**

Add these imports at the top of the existing file:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
```

Then append the following tests:

```python
# ---------------------------------------------------------------------------
# Watcher coroutine tests
# ---------------------------------------------------------------------------

class _MockStream:
    """Async context manager + iterator. Yields events then raises CancelledError."""
    def __init__(self, *events):
        self._events = list(events)
        self._pos = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._pos < len(self._events):
            event = self._events[self._pos]
            self._pos += 1
            return event
        raise asyncio.CancelledError()


def _chunk_change_event(city_id=_CITY_OID, x=0, y=0):
    """A synthetic chunk change event with a layers update."""
    return {
        "_id": {"_data": "resume_token_1"},
        "operationType": "update",
        "updateDescription": {"updatedFields": {"layers.pollution.coverage": 0.25}},
        "fullDocument": {
            "city_id": city_id,
            "coordinates": {"x": x, "y": y},
            "layers": {"electricity": {}, "pollution": {"coverage": 0.25}, "water": {}},
            "base": {"buildings": [], "roads": [], "terrain": []},
        },
    }


def _city_change_event(city_id=_CITY_OID):
    """A synthetic city change event with a global_stats update."""
    return {
        "_id": {"_data": "resume_token_2"},
        "operationType": "update",
        "updateDescription": {
            "updatedFields": {
                "global_stats.population": 5,
                "global_stats.treasury": 500.5,
                "global_stats.happiness": 80,
            }
        },
        "fullDocument": {
            "_id": city_id,
            "global_stats": {"population": 5, "treasury": 500.5, "happiness": 80},
        },
    }


async def test_watch_chunks_emits_layers_update():
    """_watch_chunks emits layers_update when stream yields a layers change event."""
    from app.change_stream import _watch_chunks

    event = _chunk_change_event()
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
        room=f"city:{_CITY_OID}",
    )


async def test_watch_chunks_skips_bookkeeping_event():
    """_watch_chunks does not emit when only last_updated changes."""
    from app.change_stream import _watch_chunks

    event = {
        "_id": {"_data": "resume_token"},
        "operationType": "update",
        "updateDescription": {"updatedFields": {"last_updated": "...", "version": 2}},
        "fullDocument": _chunk_doc(),
    }
    mock_sio = AsyncMock()
    mock_collection = MagicMock()
    mock_collection.watch.return_value = _MockStream(event)
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    with pytest.raises(asyncio.CancelledError):
        await _watch_chunks(mock_sio, mock_db)

    mock_sio.emit.assert_not_called()


async def test_watch_chunks_retries_on_exception():
    """_watch_chunks logs and reopens the stream after a non-cancel exception."""
    from app.change_stream import _watch_chunks

    call_count = 0

    def make_stream():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call: stream immediately raises
            class FailStream:
                async def __aenter__(self): return self
                async def __aexit__(self, *_): pass
                def __aiter__(self): return self
                async def __anext__(self): raise ConnectionError("stream died")
            return FailStream()
        # Second call: yield one event then cancel
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


async def test_watch_cities_emits_stats_update():
    """_watch_cities emits stats_update when stream yields a global_stats change event."""
    from app.change_stream import _watch_cities

    event = _city_change_event()
    mock_sio = AsyncMock()
    mock_collection = MagicMock()
    mock_collection.watch.return_value = _MockStream(event)
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    with pytest.raises(asyncio.CancelledError):
        await _watch_cities(mock_sio, mock_db)

    mock_sio.emit.assert_called_once_with(
        "stats_update",
        {
            "city_id": str(_CITY_OID),
            "population": 5,
            "treasury": pytest.approx(500.5),
            "happiness": 80,
        },
        room=f"city:{_CITY_OID}",
    )
```

- [ ] **Step 2: Run — verify FAIL**

```bash
cd /Users/danmanning/Documents/Source/SimulationCity/backend && uv run pytest tests/test_change_stream.py::test_watch_chunks_emits_layers_update -v
```

Expected: `ImportError: cannot import name '_watch_chunks' from 'app.change_stream'`

- [ ] **Step 3: Add watcher coroutines and `watch_changes` to `backend/app/change_stream.py`**

Append to the end of the file (after the routing helpers):

```python
# ---------------------------------------------------------------------------
# Stream watcher coroutines
# ---------------------------------------------------------------------------

_WATCH_BACKOFF_SECONDS = 5


async def _watch_chunks(sio: socketio.AsyncServer, db) -> None:
    """Forever: open the chunks change stream, route events, emit to Socket.IO.
    Retries with backoff on any non-cancel exception. Exits only on CancelledError.
    """
    resume_token = None
    while True:
        try:
            kwargs: dict = {"full_document": "updateLookup"}
            if resume_token:
                kwargs["resume_after"] = resume_token
            async with db["chunks"].watch(
                [{"$match": {"operationType": "update"}}], **kwargs
            ) as stream:
                async for event in stream:
                    resume_token = event["_id"]
                    result = _route_chunk_event(event)
                    if result:
                        event_name, payload = result
                        await sio.emit(event_name, payload, room=f"city:{payload['city_id']}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("chunks change stream error — retrying in %ds: %s", _WATCH_BACKOFF_SECONDS, exc)
            resume_token = None  # token may be invalid after an error
            await asyncio.sleep(_WATCH_BACKOFF_SECONDS)


async def _watch_cities(sio: socketio.AsyncServer, db) -> None:
    """Forever: open the cities change stream, route events, emit to Socket.IO.
    Retries with backoff on any non-cancel exception. Exits only on CancelledError.
    """
    resume_token = None
    while True:
        try:
            kwargs: dict = {"full_document": "updateLookup"}
            if resume_token:
                kwargs["resume_after"] = resume_token
            async with db["cities"].watch(
                [{"$match": {"operationType": "update"}}], **kwargs
            ) as stream:
                async for event in stream:
                    resume_token = event["_id"]
                    result = _route_city_event(event)
                    if result:
                        event_name, payload = result
                        await sio.emit(event_name, payload, room=f"city:{payload['city_id']}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("cities change stream error — retrying in %ds: %s", _WATCH_BACKOFF_SECONDS, exc)
            resume_token = None
            await asyncio.sleep(_WATCH_BACKOFF_SECONDS)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def watch_changes(sio: socketio.AsyncServer, mongo_url: str, db_name: str) -> None:
    """Start chunk and city change stream watchers. Run until cancelled.

    Opens its own Motor client (independent of the Beanie connection used by FastAPI).
    Call from the FastAPI lifespan:

        task = asyncio.create_task(
            watch_changes(sio, settings.mongodb_url, settings.mongodb_db_name)
        )
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    """
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    chunk_task = asyncio.create_task(_watch_chunks(sio, db))
    city_task = asyncio.create_task(_watch_cities(sio, db))
    try:
        await asyncio.gather(chunk_task, city_task)
    finally:
        chunk_task.cancel()
        city_task.cancel()
        await asyncio.gather(chunk_task, city_task, return_exceptions=True)
        client.close()
```

- [ ] **Step 4: Run — verify all change stream tests PASS**

```bash
cd /Users/danmanning/Documents/Source/SimulationCity/backend && uv run pytest tests/test_change_stream.py -v
```

Expected: all 11 tests pass.

- [ ] **Step 5: Run full test suite — no regressions**

```bash
cd /Users/danmanning/Documents/Source/SimulationCity/backend && uv run pytest -v
```

Expected: all 28 + 11 = 39 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/change_stream.py backend/tests/test_change_stream.py
git commit -m "feat: add change stream watcher coroutines and watch_changes entry point"
```

---

## Task 3: Lifespan Wiring

Wire `watch_changes` into the FastAPI lifespan so it starts with the server and cancels cleanly on shutdown. Add a test verifying the background task is started and stopped.

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_change_stream.py`

- [ ] **Step 1: Add lifespan test to `backend/tests/test_change_stream.py`**

Append:

```python
# ---------------------------------------------------------------------------
# Lifespan wiring test
# ---------------------------------------------------------------------------

async def test_lifespan_starts_and_stops_watch_changes():
    """watch_changes is started as a background task during lifespan and cancelled on shutdown."""
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def fake_watch_changes(sio, mongo_url, db_name):
        started.set()
        try:
            await asyncio.sleep(9999)
        except asyncio.CancelledError:
            stopped.set()
            raise

    with patch("app.main.watch_changes", side_effect=fake_watch_changes):
        from app.main import lifespan, app
        async with lifespan(app):
            await asyncio.wait_for(started.wait(), timeout=1.0)

    await asyncio.wait_for(stopped.wait(), timeout=1.0)
```

- [ ] **Step 2: Run — verify FAIL**

```bash
cd /Users/danmanning/Documents/Source/SimulationCity/backend && uv run pytest tests/test_change_stream.py::test_lifespan_starts_and_stops_watch_changes -v
```

Expected: `ImportError: cannot import name 'watch_changes' from 'app.main'` (not yet wired up).

- [ ] **Step 3: Wire `watch_changes` into `backend/app/main.py`**

Replace the current lifespan:

```python
from contextlib import asynccontextmanager
import asyncio

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.change_stream import watch_changes
from app.config import settings
from app.database import close_db, init_db
from app.routers import auth, cities
from app.socket_handlers import sio


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    change_stream_task = asyncio.create_task(
        watch_changes(sio, settings.mongodb_url, settings.mongodb_db_name)
    )
    yield
    change_stream_task.cancel()
    try:
        await change_stream_task
    except asyncio.CancelledError:
        pass
    await close_db()
```

Keep everything below (`app = FastAPI(...)` through `socket_app = ...`) unchanged.

- [ ] **Step 4: Run — verify PASS**

```bash
cd /Users/danmanning/Documents/Source/SimulationCity/backend && uv run pytest tests/test_change_stream.py -v
```

Expected: all 12 tests pass.

- [ ] **Step 5: Run full test suite — no regressions**

```bash
cd /Users/danmanning/Documents/Source/SimulationCity/backend && uv run pytest -v
```

Expected: all 40 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/tests/test_change_stream.py
git commit -m "feat: wire watch_changes into FastAPI lifespan"
```

---

## Verification

After all tasks are complete, verify end-to-end manually against Atlas:

- [ ] **Start infrastructure**

```bash
# From project root — Redis only needed (MongoDB is Atlas)
docker-compose up -d
```

- [ ] **Start backend**

```bash
cd backend && uv run uvicorn app.main:socket_app --reload
```

Expected in startup logs: no Motor connection errors. The watcher tasks start silently in the background.

- [ ] **Start workers + Beat**

```bash
cd backend && uv run celery -A workers.celery_app worker -Q simulation,high_priority -l info
cd backend && uv run celery -A workers.celery_app beat -l info
```

- [ ] **Connect a Socket.IO client and join a city**, then observe that `layers_update` and `stats_update` events arrive every ~10 seconds as the Beat tick fires.

- [ ] **Run full test suite one final time**

```bash
cd backend && uv run pytest -v
```

Expected: all tests pass.

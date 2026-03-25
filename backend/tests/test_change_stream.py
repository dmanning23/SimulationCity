"""Unit tests for change stream routing helpers."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

import app.viewport_store as _vp_store

_CITY_OID = ObjectId("000000000000000000000001")
_SUBSCRIBER_SID = "test-subscriber-sid"


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


@pytest.fixture(autouse=True)
def clear_viewport_store():
    _vp_store.session_subscriptions.clear()
    _vp_store.chunk_subscribers.clear()
    yield
    _vp_store.session_subscriptions.clear()
    _vp_store.chunk_subscribers.clear()


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


def test_route_chunk_event_returns_none_for_global_stats_key():
    """_route_chunk_event must not match global_stats.* keys — those belong to cities."""
    from app.change_stream import _route_chunk_event
    event = _chunk_event({"global_stats.population": 5}, _chunk_doc())
    assert _route_chunk_event(event) is None


def test_route_chunk_event_none_full_document_does_not_crash():
    """fullDocument can be None if updateLookup not configured — must not raise."""
    from app.change_stream import _route_chunk_event
    event = {
        "operationType": "update",
        "_id": {"_data": "resume_token"},
        "updateDescription": {"updatedFields": {"layers.pollution.coverage": 0.1}},
        "fullDocument": None,
    }
    result = _route_chunk_event(event)
    # Should return a payload (not None) but with empty/None coordinate fields
    assert result is not None
    name, payload = result
    assert name == "layers_update"


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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


# ---------------------------------------------------------------------------
# Lifespan wiring test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
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

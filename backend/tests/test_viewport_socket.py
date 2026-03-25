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
    """join_city with no viewport uses 4x4 default at origin."""
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
    """update_viewport emits error when bbox exceeds 20x20."""
    handler = _get_handler("update_viewport")
    session = {"user_id": _FAKE_USER_ID, "city_id": _FAKE_CITY_ID}
    emitted = []

    async def capture(event, data, to=None, **kwargs):
        emitted.append({"name": event, "data": data})

    with patch.object(sio, "get_session", new=AsyncMock(return_value=session)), \
         patch.object(sio, "emit", side_effect=capture):
        await handler(_FAKE_SID, {
            "city_id": _FAKE_CITY_ID,
            "min_x": 0, "min_y": 0, "max_x": 20, "max_y": 20,  # 21x21 > 20x20
        })

    assert any(e["name"] == "error" for e in emitted)


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

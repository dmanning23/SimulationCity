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

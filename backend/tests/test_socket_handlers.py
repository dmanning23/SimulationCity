"""Tests for player_joined and initial_state payload shapes in join_city."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from beanie import PydanticObjectId

from app.socket_handlers import sio


_FAKE_OWNER_SID = "owner-sid-001"
_FAKE_JOINER_SID = "joiner-sid-002"
_FAKE_OWNER_ID = str(ObjectId("aaaaaaaaaaaaaaaaaaaaaaaa"))
_FAKE_JOINER_ID = str(ObjectId("bbbbbbbbbbbbbbbbbbbbbbbb"))


def _get_handler(event: str):
    handler = sio.handlers.get("/", {}).get(event)
    if handler is None:
        raise RuntimeError(f"Event '{event}' not registered on sio")
    return handler


@pytest.mark.asyncio
async def test_player_joined_includes_username_and_role(db):
    """player_joined emitted to room includes username and role, not just user_id."""
    from app.models.city import City
    from app.models.player import Player
    from app.models.city import Collaborator, CollaboratorRole

    # Create the owner player
    owner = Player(username="ownerplayer", hashed_password="x", email="o@x.com")
    await owner.insert()
    owner_id = str(owner.id)

    # Create the joining player (a collaborator)
    joiner = Player(username="joinerplayer", hashed_password="x", email="j@x.com")
    await joiner.insert()
    joiner_id = str(joiner.id)

    # Create city with the joiner as a builder collaborator
    city = City(
        name="Test City",
        owner_id=PydanticObjectId(owner_id),
        collaborators=[
            Collaborator(user_id=PydanticObjectId(joiner_id), role=CollaboratorRole.BUILDER)
        ],
        global_stats={"population": 0, "treasury": 0.0, "happiness": 50},
        settings={"design_style": "default"},
    )
    await city.insert()
    city_id = str(city.id)

    handler = _get_handler("join_city")
    session = {"user_id": joiner_id}

    emitted_events = []

    async def capture_emit(event, data, **kwargs):
        emitted_events.append((event, data, kwargs))

    with patch.object(sio, "get_session", new=AsyncMock(return_value=session)), \
         patch.object(sio, "enter_room", new=AsyncMock()), \
         patch.object(sio, "save_session", new=AsyncMock()), \
         patch.object(sio, "emit", new=AsyncMock(side_effect=capture_emit)), \
         patch.object(sio.manager, "get_participants", return_value=[]):
        await handler(_FAKE_JOINER_SID, {"city_id": city_id})

    # Find the player_joined event
    player_joined_calls = [(e, d, kw) for e, d, kw in emitted_events if e == "player_joined"]
    assert len(player_joined_calls) == 1
    _, payload, _ = player_joined_calls[0]
    assert payload["user_id"] == joiner_id
    assert payload["username"] == "joinerplayer"
    assert payload["role"] == "builder"


@pytest.mark.asyncio
async def test_player_joined_owner_has_admin_role(db):
    """City owner joining is reported with role='admin' in player_joined."""
    from app.models.city import City
    from app.models.player import Player

    owner = Player(username="adminuser", hashed_password="x", email="a@x.com")
    await owner.insert()
    owner_id = str(owner.id)

    city = City(
        name="Admin City",
        owner_id=PydanticObjectId(owner_id),
        collaborators=[],
        global_stats={"population": 0, "treasury": 0.0, "happiness": 50},
        settings={"design_style": "default"},
    )
    await city.insert()
    city_id = str(city.id)

    handler = _get_handler("join_city")
    session = {"user_id": owner_id}

    emitted_events = []

    async def capture_emit(event, data, **kwargs):
        emitted_events.append((event, data, kwargs))

    with patch.object(sio, "get_session", new=AsyncMock(return_value=session)), \
         patch.object(sio, "enter_room", new=AsyncMock()), \
         patch.object(sio, "save_session", new=AsyncMock()), \
         patch.object(sio, "emit", new=AsyncMock(side_effect=capture_emit)), \
         patch.object(sio.manager, "get_participants", return_value=[]):
        await handler(_FAKE_OWNER_SID, {"city_id": city_id})

    player_joined_calls = [(e, d, kw) for e, d, kw in emitted_events if e == "player_joined"]
    assert len(player_joined_calls) == 1
    _, payload, _ = player_joined_calls[0]
    assert payload["role"] == "admin"


@pytest.mark.asyncio
async def test_initial_state_includes_collaborators_list(db):
    """initial_state includes active collaborators so PlayerList is seeded on join."""
    from app.models.city import City
    from app.models.player import Player

    owner = Player(username="cityowner", hashed_password="x", email="co@x.com")
    await owner.insert()
    owner_id = str(owner.id)

    already_online = Player(username="onlineplayer", hashed_password="x", email="on@x.com")
    await already_online.insert()
    online_id = str(already_online.id)

    new_joiner = Player(username="newplayer", hashed_password="x", email="np@x.com")
    await new_joiner.insert()
    new_joiner_id = str(new_joiner.id)

    from app.models.city import Collaborator, CollaboratorRole
    city = City(
        name="Populated City",
        owner_id=PydanticObjectId(owner_id),
        collaborators=[
            Collaborator(user_id=PydanticObjectId(new_joiner_id), role=CollaboratorRole.BUILDER),
        ],
        global_stats={"population": 0, "treasury": 0.0, "happiness": 50},
        settings={"design_style": "default"},
    )
    await city.insert()
    city_id = str(city.id)

    handler = _get_handler("join_city")
    session = {"user_id": new_joiner_id}

    # Simulate online_player already in the room
    async def fake_get_session(sid):
        if sid == "online-sid":
            return {"user_id": online_id, "city_id": city_id}
        return {"user_id": new_joiner_id}

    emitted_events = []

    async def capture_emit(event, data, **kwargs):
        emitted_events.append((event, data, kwargs))

    with patch.object(sio, "get_session", new=AsyncMock(side_effect=fake_get_session)), \
         patch.object(sio, "enter_room", new=AsyncMock()), \
         patch.object(sio, "save_session", new=AsyncMock()), \
         patch.object(sio, "emit", new=AsyncMock(side_effect=capture_emit)), \
         patch.object(sio.manager, "get_participants", return_value=[("online-sid", "fake-eio-id")]):
        await handler("new-joiner-sid", {"city_id": city_id})

    initial_state_calls = [(e, d, kw) for e, d, kw in emitted_events if e == "initial_state"]
    assert len(initial_state_calls) == 1
    _, payload, _ = initial_state_calls[0]
    collaborators = payload["city"]["collaborators"]
    assert len(collaborators) == 1
    assert collaborators[0]["user_id"] == online_id
    assert collaborators[0]["username"] == "onlineplayer"
    assert collaborators[0]["role"] == "viewer"

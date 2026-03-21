"""Integration tests for the build_action Socket.IO event handler.

python-socketio 5.x removed AsyncTestClient.  We test by:
  1. Retrieving the registered handler function from sio.handlers['/'].
  2. Mocking sio.get_session to return preset session data.
  3. Mocking sio.emit to capture emitted events.
  4. Calling the handler directly — no network I/O needed.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from app.socket_handlers import sio

_FAKE_SID = "test-sid-build-action"
_FAKE_USER_ID = "000000000000000000000001"
_FAKE_CITY_ID = "000000000000000000000002"


def _get_handler(event: str):
    """Retrieve the registered sio event handler or raise if not yet registered."""
    handler = sio.handlers.get("/", {}).get(event)
    if handler is None:
        raise RuntimeError(
            f"Event '{event}' is not registered on sio — implement the handler first."
        )
    return handler


@pytest.fixture
def with_city_session():
    """Patch sio.get_session to return a joined-city session."""
    session = {"user_id": _FAKE_USER_ID, "city_id": _FAKE_CITY_ID}
    with patch.object(sio, "get_session", new=AsyncMock(return_value=session)):
        yield session


@pytest.fixture
def without_city_session():
    """Patch sio.get_session to return a session with no city_id."""
    session = {"user_id": _FAKE_USER_ID}
    with patch.object(sio, "get_session", new=AsyncMock(return_value=session)):
        yield session


async def test_build_action_queues_task_and_acks(with_city_session):
    """Valid build_action enqueues task and emits action_queued."""
    handler = _get_handler("build_action")
    emitted_events = []

    async def capture_emit(event, data, to=None, **kwargs):
        emitted_events.append({"name": event, "data": data})

    mock_send = MagicMock()
    with patch("app.socket_handlers._celery_app") as mock_app, \
         patch.object(sio, "emit", side_effect=capture_emit):
        mock_app.send_task = mock_send
        await handler(
            _FAKE_SID,
            {
                "action_type": "place_building",
                "payload": {
                    "chunk_x": 0,
                    "chunk_y": 0,
                    "building_type": "residential",
                    "position": {"x": 1, "y": 2},
                },
            },
        )

    ack = next((e for e in emitted_events if e["name"] == "action_queued"), None)
    assert ack is not None, f"Expected action_queued event, got: {emitted_events}"
    assert ack["data"]["action_type"] == "place_building"
    assert ack["data"]["status"] == "queued"

    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args
    assert call_kwargs.args[0] == "workers.build_actions.process_build_action"
    assert call_kwargs.kwargs["queue"] == "high_priority"
    task_kwargs = call_kwargs.kwargs["kwargs"]
    assert task_kwargs["city_id"] == _FAKE_CITY_ID
    assert task_kwargs["action_type"] == "place_building"


async def test_build_action_unknown_type_emits_error(with_city_session):
    """Unknown action_type returns error event, no task enqueued."""
    handler = _get_handler("build_action")
    emitted_events = []

    async def capture_emit(event, data, to=None, **kwargs):
        emitted_events.append({"name": event, "data": data})

    mock_send = MagicMock()
    with patch("app.socket_handlers._celery_app") as mock_app, \
         patch.object(sio, "emit", side_effect=capture_emit):
        mock_app.send_task = mock_send
        await handler(_FAKE_SID, {"action_type": "destroy_world", "payload": {}})

    error = next((e for e in emitted_events if e["name"] == "error"), None)
    assert error is not None, f"Expected error event, got: {emitted_events}"
    assert "Unknown" in error["data"]["message"]
    mock_send.assert_not_called()


async def test_build_action_missing_action_type_emits_error(with_city_session):
    """Missing action_type emits error."""
    handler = _get_handler("build_action")
    emitted_events = []

    async def capture_emit(event, data, to=None, **kwargs):
        emitted_events.append({"name": event, "data": data})

    with patch.object(sio, "emit", side_effect=capture_emit):
        await handler(_FAKE_SID, {"payload": {}})

    assert any(e["name"] == "error" for e in emitted_events), \
        f"Expected error event, got: {emitted_events}"


async def test_build_action_without_joining_city_emits_error(without_city_session):
    """Client connected but not joined to a city gets an error on build_action."""
    handler = _get_handler("build_action")
    emitted_events = []

    async def capture_emit(event, data, to=None, **kwargs):
        emitted_events.append({"name": event, "data": data})

    with patch.object(sio, "emit", side_effect=capture_emit):
        await handler(_FAKE_SID, {"action_type": "place_building", "payload": {}})

    assert any(e["name"] == "error" for e in emitted_events), \
        f"Expected error event, got: {emitted_events}"

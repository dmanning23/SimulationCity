import logging

import socketio
from beanie import PydanticObjectId
from jose import JWTError

from app.constants import VALID_ACTION_TYPES
from app.models.chunk import Chunk
from app.models.city import City
from app.services.auth import decode_token
from workers.celery_app import celery_app as _celery_app

logger = logging.getLogger(__name__)

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
)


async def _load_viewport_chunks(city_id: str, viewport: dict | None) -> list[dict]:
    """Return serialized chunks visible in the given viewport (defaults to 4x4 at origin)."""
    if viewport:
        cx = viewport.get("chunkX", 0)
        cy = viewport.get("chunkY", 0)
        radius = viewport.get("radius", 2)
        x_coords = list(range(max(0, cx - radius), cx + radius + 1))
        y_coords = list(range(max(0, cy - radius), cy + radius + 1))
    else:
        x_coords = list(range(0, 4))
        y_coords = list(range(0, 4))

    # Use a raw pymongo query dict — Beanie expression + dict cannot be mixed
    chunks = await Chunk.find(
        {
            "city_id": PydanticObjectId(city_id),
            "coordinates.x": {"$in": x_coords},
            "coordinates.y": {"$in": y_coords},
        }
    ).to_list()
    return [c.model_dump(mode="json") for c in chunks]


@sio.event
async def connect(sid: str, environ: dict, auth: dict | None = None):
    if not auth or "token" not in auth:
        raise ConnectionRefusedError("Authentication required")

    try:
        payload = decode_token(auth["token"])
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise ConnectionRefusedError("Invalid token payload")
    except JWTError:
        raise ConnectionRefusedError("Invalid or expired token")

    await sio.save_session(sid, {"user_id": user_id})
    logger.info("Player %s connected (sid=%s)", user_id, sid)


@sio.event
async def disconnect(sid: str):
    session = await sio.get_session(sid)
    if not session:
        return

    user_id = session.get("user_id", "unknown")
    city_id = session.get("city_id")

    if city_id:
        await sio.leave_room(sid, f"city:{city_id}")
        await sio.emit(
            "player_left",
            {"user_id": user_id},
            room=f"city:{city_id}",
            skip_sid=sid,
        )

    logger.info("Player %s disconnected (sid=%s)", user_id, sid)


@sio.event
async def join_city(sid: str, data: dict):
    session = await sio.get_session(sid)
    if not session or not session.get("user_id"):
        await sio.emit("error", {"message": "Not authenticated"}, to=sid)
        return

    city_id = data.get("city_id")
    if not city_id:
        await sio.emit("error", {"message": "city_id required"}, to=sid)
        return

    try:
        city_oid = PydanticObjectId(city_id)
    except Exception:
        await sio.emit("error", {"message": "Invalid city_id"}, to=sid)
        return

    city = await City.get(city_oid)
    if not city:
        await sio.emit("error", {"message": "City not found"}, to=sid)
        return

    user_id: str = session["user_id"]
    is_owner = str(city.owner_id) == user_id
    is_collab = any(str(c.user_id) == user_id for c in city.collaborators)
    if not (is_owner or is_collab):
        await sio.emit("error", {"message": "Access denied"}, to=sid)
        return

    # Leave any previously joined city room
    old_city_id = session.get("city_id")
    if old_city_id and old_city_id != city_id:
        await sio.leave_room(sid, f"city:{old_city_id}")

    await sio.enter_room(sid, f"city:{city_id}")
    await sio.save_session(sid, {**session, "city_id": city_id})

    # Notify others in the room
    await sio.emit(
        "player_joined",
        {"user_id": user_id},
        room=f"city:{city_id}",
        skip_sid=sid,
    )

    # Send initial state: city metadata + visible chunks
    chunks = await _load_viewport_chunks(city_id, data.get("viewport"))
    await sio.emit(
        "initial_state",
        {
            "city": {
                "id": str(city.id),
                "name": city.name,
                "global_stats": city.global_stats.model_dump(),
                "settings": city.settings.model_dump(),
            },
            "chunks": chunks,
        },
        to=sid,
    )
    logger.info("Player %s joined city %s", user_id, city_id)


@sio.event
async def leave_city(sid: str):
    session = await sio.get_session(sid)
    if not session:
        return

    city_id = session.get("city_id")
    user_id = session.get("user_id")

    if city_id:
        await sio.leave_room(sid, f"city:{city_id}")
        await sio.save_session(sid, {k: v for k, v in session.items() if k != "city_id"})
        await sio.emit(
            "player_left",
            {"user_id": user_id},
            room=f"city:{city_id}",
            skip_sid=sid,
        )
        logger.info("Player %s left city %s", user_id, city_id)


@sio.event
async def update_viewport(sid: str, data: dict):
    """Client notifies server about viewport change for chunk subscription management (Phase 3)."""
    session = await sio.get_session(sid)
    if not session or not session.get("city_id"):
        return
    await sio.save_session(sid, {**session, "viewport": data.get("viewport", {})})


@sio.event
async def build_action(sid: str, data: dict):
    session = await sio.get_session(sid)
    if not session or not session.get("user_id") or not session.get("city_id"):
        await sio.emit("error", {"message": "Must be joined to a city to perform actions"}, to=sid)
        return

    action_type = data.get("action_type")
    if not action_type:
        await sio.emit("error", {"message": "action_type is required"}, to=sid)
        return

    if action_type not in VALID_ACTION_TYPES:
        await sio.emit("error", {"message": f"Unknown action_type: {action_type!r}"}, to=sid)
        return

    _celery_app.send_task(
        "workers.build_actions.process_build_action",
        kwargs={
            "city_id": session["city_id"],
            "user_id": session["user_id"],
            "action_type": action_type,
            "payload": data.get("payload", {}),
        },
        queue="high_priority",
    )
    await sio.emit("action_queued", {"action_type": action_type, "status": "queued"}, to=sid)
    logger.info("Queued %r for city %s by user %s", action_type, session["city_id"], session["user_id"])

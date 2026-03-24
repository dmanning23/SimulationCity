"""MongoDB change stream listener — broadcasts real-time events to Socket.IO city rooms.

Routing uses prefix matching against updateDescription.updatedFields keys:
  - chunks: "layers.*"         → layers_update
  - chunks: "base.buildings.*" → chunk_update  ($push generates "base.buildings.<N>")
  - cities: "global_stats.*"   → stats_update

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
            resume_token = None
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

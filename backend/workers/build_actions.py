import logging
from datetime import datetime, timezone
from typing import Callable

from celery.signals import worker_process_init

from app.config import settings
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Lazy MongoClient — created on first task execution, not at import time.
_mongo_client = None


def _get_db():
    global _mongo_client
    if _mongo_client is None:
        from pymongo import MongoClient
        _mongo_client = MongoClient(settings.mongodb_url)
    return _mongo_client[settings.mongodb_db_name]


@worker_process_init.connect
def _reset_mongo_on_fork(**kwargs):
    """Close and reset MongoClient after prefork so child workers get fresh connections."""
    global _mongo_client
    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None


# --- Handlers ---

def _handle_place_building(city_id: str, user_id: str, payload: dict) -> None:
    import uuid
    from bson import ObjectId

    building = {
        "id": str(uuid.uuid4()),
        "type": payload["building_type"],
        "subtype": payload.get("subtype", ""),
        "position": payload["position"],
        "size": payload.get("size", {"width": 1, "height": 1}),
        "level": 1,
        "health": 100,
        "asset_id": None,
    }
    _get_db().chunks.update_one(
        {
            "city_id": ObjectId(city_id),
            "coordinates.x": payload["chunk_x"],
            "coordinates.y": payload["chunk_y"],
        },
        {
            "$push": {"base.buildings": building},
            "$set": {"last_updated": datetime.now(timezone.utc)},
        },
    )


def _handle_place_road(city_id: str, user_id: str, payload: dict) -> None:
    logger.info("place_road stub: city=%s user=%s", city_id, user_id)


def _handle_place_zone(city_id: str, user_id: str, payload: dict) -> None:
    logger.info("place_zone stub: city=%s user=%s", city_id, user_id)


def _handle_demolish(city_id: str, user_id: str, payload: dict) -> None:
    logger.info("demolish stub: city=%s user=%s", city_id, user_id)


REGISTRY: dict[str, Callable] = {
    "place_building": _handle_place_building,
    "place_road": _handle_place_road,
    "place_zone": _handle_place_zone,
    "demolish": _handle_demolish,
}


# --- Task ---

@celery_app.task(bind=True, queue="high_priority", max_retries=3)
def process_build_action(
    self, city_id: str, user_id: str, action_type: str, payload: dict
) -> None:
    if action_type not in REGISTRY:
        logger.warning("Unknown action_type %r — skipping (no retry)", action_type)
        return
    try:
        REGISTRY[action_type](city_id, user_id, payload)
    except NotImplementedError:
        raise  # stub not yet implemented — do not retry
    except Exception as exc:
        logger.exception("Build action %r failed: %s", action_type, exc)
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

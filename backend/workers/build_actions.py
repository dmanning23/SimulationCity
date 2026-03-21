import logging
from datetime import datetime, timezone
from typing import Callable

from app.config import settings
from app.constants import VALID_ACTION_TYPES
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


# --- Handlers ---

def _handle_place_building(city_id: str, user_id: str, payload: dict) -> None:
    raise NotImplementedError


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
    except Exception as exc:
        logger.exception("Build action %r failed: %s", action_type, exc)
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

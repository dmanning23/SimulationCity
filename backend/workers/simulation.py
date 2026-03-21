import logging
from datetime import datetime, timezone

from bson import ObjectId

from app.config import settings
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

TAX_RATE_PER_TICK = 0.1

# Thread safety note: this lazy initializer is NOT thread-safe. It is safe
# only for Celery's default prefork concurrency model (one thread per worker
# process). Do not switch to --pool=gevent or --pool=threads without adding
# a threading.Lock guard here.
_mongo_client = None


def _get_db():
    global _mongo_client
    if _mongo_client is None:
        from pymongo import MongoClient
        _mongo_client = MongoClient(settings.mongodb_url)
    return _mongo_client[settings.mongodb_db_name]


# ---------------------------------------------------------------------------
# Pure rule functions — no DB access, easy to unit test
# ---------------------------------------------------------------------------

def compute_population_delta(chunk: dict) -> int:
    """Return +1 if residential chunk has power+water, -1 if residential but lacking, 0 if no residential."""
    has_residential = any(
        b["type"] == "residential" for b in chunk["base"].get("buildings", [])
    )
    if not has_residential:
        return 0
    has_power = chunk["layers"]["electricity"].get("coverage", 0.0) > 0
    has_water = chunk["layers"]["water"].get("coverage", 0.0) > 0
    return 1 if (has_power and has_water) else -1


def compute_new_pollution(chunk: dict) -> float:
    """Return new pollution coverage after applying industrial increase and natural decay."""
    industrial_count = sum(
        1 for b in chunk["base"].get("buildings", []) if b["type"] == "industrial"
    )
    current = chunk["layers"]["pollution"].get("coverage", 0.0)
    new = current + (industrial_count * 0.1) - 0.01
    return max(0.0, min(1.0, new))


def compute_treasury_delta(total_population: int) -> float:
    """Tax income per tick."""
    return total_population * TAX_RATE_PER_TICK


def compute_happiness(avg_pollution: float, commercial_count: int) -> int:
    """City happiness as a 0–100 int. Decreases with pollution, increases with commercial density."""
    raw = 100.0 - (avg_pollution * 50.0) + (commercial_count * 2.0)
    return max(0, min(100, int(raw)))

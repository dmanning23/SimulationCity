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


# ---------------------------------------------------------------------------
# Celery tasks
# ---------------------------------------------------------------------------

@celery_app.task(queue="simulation")
def simulate_city_tick(city_id: str) -> None:
    """Apply one simulation tick to all chunks in a city and update global stats."""
    db = _get_db()
    now = datetime.now(timezone.utc)

    chunks = list(db.chunks.find({"city_id": ObjectId(city_id)}))
    if not chunks:
        return

    total_pop_delta = 0
    all_pollution: list[float] = []
    commercial_count = 0
    writes_applied = 0

    for chunk in chunks:
        old_version = chunk["version"]

        new_pollution = compute_new_pollution(chunk)
        all_pollution.append(new_pollution)

        total_pop_delta += compute_population_delta(chunk)

        commercial_count += sum(
            1 for b in chunk["base"].get("buildings", []) if b["type"] == "commercial"
        )

        # Conditional write: skip silently if version changed (another process beat us)
        result = db.chunks.update_one(
            {"_id": chunk["_id"], "version": old_version},
            {
                "$set": {
                    "layers.pollution.coverage": new_pollution,
                    "last_updated": now,
                },
                "$inc": {"version": 1},
            },
        )
        if result.modified_count:
            writes_applied += 1

    if writes_applied == 0:
        logger.warning(
            "simulate_city_tick city=%s: all %d chunk write(s) skipped (version conflicts)",
            city_id, len(chunks),
        )
        return

    city = db.cities.find_one({"_id": ObjectId(city_id)})
    if not city:
        return

    avg_pollution = sum(all_pollution) / len(all_pollution)
    happiness = compute_happiness(avg_pollution, commercial_count)

    current_pop = city["global_stats"]["population"]
    new_pop = max(0, current_pop + total_pop_delta)
    new_treasury = city["global_stats"]["treasury"] + compute_treasury_delta(new_pop)

    db.cities.update_one(
        {"_id": ObjectId(city_id)},
        {
            "$set": {
                "global_stats.population": new_pop,
                "global_stats.treasury": new_treasury,
                "global_stats.happiness": happiness,
                "last_updated": now,
            }
        },
    )
    logger.info(
        "Ticked city %s: pop=%d treasury=%.1f happiness=%d",
        city_id, new_pop, new_treasury, happiness,
    )


@celery_app.task(queue="simulation")
def tick_all_cities() -> None:
    """Beat entry point: fan out one simulate_city_tick per city."""
    db = _get_db()
    city_ids = [str(doc["_id"]) for doc in db.cities.find({}, {"_id": 1})]
    for city_id in city_ids:
        simulate_city_tick.delay(city_id)
    logger.info("Dispatched ticks for %d cities", len(city_ids))

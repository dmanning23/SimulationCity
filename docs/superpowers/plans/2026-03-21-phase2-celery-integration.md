# Phase 2: Celery Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire up Celery for player build actions (via Socket.IO → `high_priority` queue) and periodic city simulation ticks (via Celery Beat → `simulation` queue), writing results directly to MongoDB.

**Architecture:** The Socket.IO handler validates and enqueues `build_action` events using `celery_app.send_task()` by name — no direct worker import. Workers use a lazy-initialized module-level `MongoClient` (not Beanie) and write results synchronously to MongoDB. Real-time broadcasting is deferred to Phase 3.

**Tech Stack:** Python 3.12, Celery 5.4 + Redis 7, pymongo 4.7, python-socketio 5.11, pytest + pytest-asyncio

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/app/constants.py` | Create | `VALID_ACTION_TYPES` frozenset — shared between socket handler and worker |
| `backend/workers/celery_app.py` | Modify | Add `conf.include` (register task modules) + `beat_schedule` |
| `backend/workers/build_actions.py` | Create | `process_build_action` task + action registry + `place_building` handler |
| `backend/workers/simulation.py` | Create | Pure simulation rule functions + `simulate_city_tick` + `tick_all_cities` tasks |
| `backend/app/socket_handlers.py` | Modify | Add `build_action` Socket.IO event handler |
| `backend/tests/conftest.py` | Modify | Add `pymongo_db` sync fixture for worker integration tests |
| `backend/tests/test_build_actions.py` | Create | Unit + integration tests for build actions worker |
| `backend/tests/test_simulation.py` | Create | Unit tests for simulation rules + integration test for tick |
| `backend/tests/test_socket_build_action.py` | Create | Socket.IO integration test for `build_action` event |

---

## Task 1: Shared Constants + Celery App Wiring

No TDD needed — this is pure configuration with no logic to test.

**Files:**
- Create: `backend/app/constants.py`
- Modify: `backend/workers/celery_app.py`

- [ ] **Step 1: Create `backend/app/constants.py`**

```python
VALID_ACTION_TYPES: frozenset[str] = frozenset({
    "place_building",
    "place_road",
    "place_zone",
    "demolish",
})
```

- [ ] **Step 2: Update `backend/workers/celery_app.py`**

Replace the commented-out autodiscover line and add the Beat schedule. The final file should look like:

```python
from celery import Celery

from app.config import settings

celery_app = Celery(
    "simulationcity",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_queues={
        "high_priority": {
            "exchange": "high_priority",
            "routing_key": "high_priority",
        },
        "simulation": {
            "exchange": "simulation",
            "routing_key": "simulation",
        },
    },
    task_default_queue="high_priority",
)

# Register task modules explicitly.
# Note: autodiscover_tasks() assumes a tasks.py convention; conf.include is
# the correct mechanism for non-standard module names.
celery_app.conf.include = ["workers.simulation", "workers.build_actions"]

# Beat schedule — tick all cities every 10 seconds.
# "queue" must be explicit; task_default_queue is high_priority.
celery_app.conf.beat_schedule = {
    "tick-all-cities": {
        "task": "workers.simulation.tick_all_cities",
        "schedule": 10.0,
        "queue": "simulation",
    }
}
```

- [ ] **Step 3: Verify import works**

```bash
cd backend && uv run python -c "from workers.celery_app import celery_app; print(celery_app.conf.beat_schedule)"
```

Expected: prints the beat schedule dict without errors.

- [ ] **Step 4: Commit**

```bash
git add backend/app/constants.py backend/workers/celery_app.py
git commit -m "feat: add shared action constants and wire Celery Beat schedule"
```

---

## Task 2: Build Actions Worker — Registry Scaffold (Unit Test)

TDD: write the registry dispatch test first, then implement the module skeleton.

**Files:**
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/test_build_actions.py`
- Create: `backend/workers/build_actions.py`

- [ ] **Step 1: Add `pymongo_db` fixture to `backend/tests/conftest.py`**

Add after the existing fixtures:

```python
import pymongo as _pymongo

@pytest.fixture()
def pymongo_db():
    """Synchronous pymongo DB for worker integration tests. Cleaned up after each test.

    WARNING: Do not combine with the async `db` fixture in the same test — both
    connect to simulationcity_test and both drop all collections on teardown.
    Worker tests (sync) use this fixture; socket/FastAPI tests (async) use `db`.
    """
    client = _pymongo.MongoClient(_MONGO_URL)
    db = client[_TEST_DB]
    yield db
    for name in db.list_collection_names():
        db.drop_collection(name)
    client.close()
```

- [ ] **Step 2: Write the failing registry dispatch test**

Create `backend/tests/test_build_actions.py`:

```python
from unittest.mock import MagicMock, patch


def test_registry_dispatches_to_correct_handler():
    """process_build_action routes action_type to the registered handler."""
    from workers.build_actions import process_build_action, REGISTRY

    mock_handler = MagicMock()
    with patch.dict(REGISTRY, {"place_building": mock_handler}):
        process_build_action.apply(
            kwargs={
                "city_id": "000000000000000000000001",
                "user_id": "000000000000000000000002",
                "action_type": "place_building",
                "payload": {"chunk_x": 0, "chunk_y": 0, "building_type": "residential", "position": {"x": 0, "y": 0}},
            }
        )

    mock_handler.assert_called_once_with(
        "000000000000000000000001",
        "000000000000000000000002",
        {"chunk_x": 0, "chunk_y": 0, "building_type": "residential", "position": {"x": 0, "y": 0}},
    )


def test_unknown_action_type_returns_silently():
    """Unknown action_type logs a warning and returns — does not raise."""
    from workers.build_actions import process_build_action

    # Should not raise
    result = process_build_action.apply(
        kwargs={
            "city_id": "000000000000000000000001",
            "user_id": "000000000000000000000002",
            "action_type": "launch_missiles",
            "payload": {},
        }
    )
    assert result.successful()
```

- [ ] **Step 3: Run — verify FAIL**

```bash
cd backend && uv run pytest tests/test_build_actions.py -v
```

Expected: `ModuleNotFoundError: No module named 'workers.build_actions'`

- [ ] **Step 4: Create `backend/workers/build_actions.py`** (scaffold — no real handler yet)

```python
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
```

- [ ] **Step 5: Run — verify PASS**

```bash
cd backend && uv run pytest tests/test_build_actions.py::test_registry_dispatches_to_correct_handler tests/test_build_actions.py::test_unknown_action_type_returns_silently -v
```

Expected: 2 passed. (The registry test will fail because `_handle_place_building` raises `NotImplementedError` — see Task 3 for the fix. These two tests use a mock handler and an unknown type respectively, so they pass.)

- [ ] **Step 6: Commit**

```bash
git add backend/workers/build_actions.py backend/tests/test_build_actions.py backend/tests/conftest.py
git commit -m "feat: scaffold build_actions worker with registry dispatch"
```

---

## Task 3: `place_building` Handler — Integration Test

TDD: write the integration test first, then implement the handler.

**Files:**
- Modify: `backend/tests/test_build_actions.py`
- Modify: `backend/workers/build_actions.py`

- [ ] **Step 1: Add integration test to `backend/tests/test_build_actions.py`**

Add these imports to the **top of the file** (alongside the existing `from unittest.mock import MagicMock, patch`):

```python
from datetime import datetime, timezone
from bson import ObjectId
```

Then append the two test functions:

```python
def test_place_building_appends_to_chunk(pymongo_db):
    """place_building pushes a Building into chunk.base.buildings."""
    from workers.build_actions import _handle_place_building

    city_id = str(ObjectId())
    pymongo_db.chunks.insert_one({
        "city_id": ObjectId(city_id),
        "coordinates": {"x": 2, "y": 3},
        "version": 0,
        "last_updated": datetime.now(timezone.utc),
        "base": {"terrain": [[0] * 16 for _ in range(16)], "buildings": [], "roads": []},
        "layers": {"electricity": {}, "pollution": {}, "water": {}},
    })

    with patch("workers.build_actions._get_db", return_value=pymongo_db):
        _handle_place_building(
            city_id=city_id,
            user_id="test_user",
            payload={
                "chunk_x": 2,
                "chunk_y": 3,
                "building_type": "residential",
                "position": {"x": 5, "y": 7},
                "size": {"width": 1, "height": 1},
            },
        )

    updated = pymongo_db.chunks.find_one({"city_id": ObjectId(city_id)})
    assert len(updated["base"]["buildings"]) == 1
    b = updated["base"]["buildings"][0]
    assert b["type"] == "residential"
    assert b["position"] == {"x": 5, "y": 7}
    assert b["level"] == 1
    assert b["health"] == 100
    assert b["asset_id"] is None
    assert "id" in b  # UUID was assigned
    assert updated["last_updated"] > datetime(2020, 1, 1, tzinfo=timezone.utc)


def test_place_building_wrong_coordinates_updates_nothing(pymongo_db):
    """Handler for wrong chunk coordinates performs no update (no matching chunk)."""
    from workers.build_actions import _handle_place_building

    city_id = str(ObjectId())
    pymongo_db.chunks.insert_one({
        "city_id": ObjectId(city_id),
        "coordinates": {"x": 0, "y": 0},
        "version": 0,
        "last_updated": datetime.now(timezone.utc),
        "base": {"terrain": [[0] * 16 for _ in range(16)], "buildings": [], "roads": []},
        "layers": {"electricity": {}, "pollution": {}, "water": {}},
    })

    with patch("workers.build_actions._get_db", return_value=pymongo_db):
        _handle_place_building(
            city_id=city_id,
            user_id="test_user",
            payload={"chunk_x": 99, "chunk_y": 99, "building_type": "residential", "position": {"x": 0, "y": 0}},
        )

    chunk = pymongo_db.chunks.find_one({"city_id": ObjectId(city_id)})
    assert chunk["base"]["buildings"] == []  # no change
```

- [ ] **Step 2: Run — verify FAIL**

```bash
cd backend && uv run pytest tests/test_build_actions.py::test_place_building_appends_to_chunk -v
```

Expected: FAIL — `NotImplementedError` from the stub.

- [ ] **Step 3: Implement `_handle_place_building` in `backend/workers/build_actions.py`**

Replace the `NotImplementedError` stub:

```python
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
```

Note: `city_id` arrives as a JSON string (Celery serialization) — `ObjectId(city_id)` converts it for MongoDB.

- [ ] **Step 4: Run — verify PASS**

```bash
cd backend && uv run pytest tests/test_build_actions.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/workers/build_actions.py backend/tests/test_build_actions.py
git commit -m "feat: implement place_building handler with pymongo push"
```

---

## Task 4: Simulation Rules — Pure Functions (Unit Tests)

TDD: write tests for all four rule functions, then implement them. No DB needed.

**Files:**
- Create: `backend/tests/test_simulation.py`
- Create: `backend/workers/simulation.py` (rule functions only — no tasks yet)

- [ ] **Step 1: Write failing unit tests**

Create `backend/tests/test_simulation.py`:

```python
"""Unit tests for simulation rule functions (no DB required)."""


# --- Helpers ---

def _chunk(buildings=None, electricity=0.0, water=0.0, pollution=0.0):
    return {
        "base": {"buildings": buildings or []},
        "layers": {
            "electricity": {"coverage": electricity},
            "water": {"coverage": water},
            "pollution": {"coverage": pollution},
        },
    }


# --- compute_population_delta ---

def test_population_grows_with_power_and_water():
    from workers.simulation import compute_population_delta
    chunk = _chunk(buildings=[{"type": "residential"}], electricity=0.5, water=0.8)
    assert compute_population_delta(chunk) == 1


def test_population_shrinks_without_power():
    from workers.simulation import compute_population_delta
    chunk = _chunk(buildings=[{"type": "residential"}], electricity=0.0, water=0.8)
    assert compute_population_delta(chunk) == -1


def test_population_shrinks_without_water():
    from workers.simulation import compute_population_delta
    chunk = _chunk(buildings=[{"type": "residential"}], electricity=0.5, water=0.0)
    assert compute_population_delta(chunk) == -1


def test_population_unchanged_no_residential():
    from workers.simulation import compute_population_delta
    chunk = _chunk(buildings=[{"type": "commercial"}], electricity=1.0, water=1.0)
    assert compute_population_delta(chunk) == 0


def test_population_unchanged_empty_chunk():
    from workers.simulation import compute_population_delta
    assert compute_population_delta(_chunk()) == 0


# --- compute_new_pollution ---

def test_pollution_increases_with_industrial():
    from workers.simulation import compute_new_pollution
    chunk = _chunk(buildings=[{"type": "industrial"}], pollution=0.0)
    # +0.1 from industrial, -0.01 decay = 0.09
    assert abs(compute_new_pollution(chunk) - 0.09) < 1e-6


def test_pollution_decays_without_industrial():
    from workers.simulation import compute_new_pollution
    chunk = _chunk(pollution=0.5)
    assert abs(compute_new_pollution(chunk) - 0.49) < 1e-6


def test_pollution_clamps_to_zero():
    from workers.simulation import compute_new_pollution
    chunk = _chunk(pollution=0.005)
    assert compute_new_pollution(chunk) == 0.0


def test_pollution_clamps_to_one():
    from workers.simulation import compute_new_pollution
    # 10 industrial buildings pushing already-maxed pollution
    chunk = _chunk(buildings=[{"type": "industrial"}] * 10, pollution=1.0)
    assert compute_new_pollution(chunk) == 1.0


# --- compute_treasury_delta ---

def test_treasury_delta():
    from workers.simulation import compute_treasury_delta, TAX_RATE_PER_TICK
    assert compute_treasury_delta(100) == pytest.approx(100 * TAX_RATE_PER_TICK)


def test_treasury_delta_zero_population():
    from workers.simulation import compute_treasury_delta
    assert compute_treasury_delta(0) == 0.0


# --- compute_happiness ---

def test_happiness_high_pollution():
    from workers.simulation import compute_happiness
    # full pollution (1.0), no commercial → 100 - 50 + 0 = 50
    assert compute_happiness(avg_pollution=1.0, commercial_count=0) == 50


def test_happiness_no_pollution_some_commercial():
    from workers.simulation import compute_happiness
    # no pollution, 5 commercial → 100 - 0 + 10 = 110 → clamped to 100
    assert compute_happiness(avg_pollution=0.0, commercial_count=5) == 100


def test_happiness_clamps_to_zero():
    from workers.simulation import compute_happiness
    # avg_pollution=3.0 → 100 - 150 + 0 = -50 → clamped to 0
    assert compute_happiness(avg_pollution=3.0, commercial_count=0) == 0


def test_happiness_clamps_to_100():
    from workers.simulation import compute_happiness
    assert compute_happiness(avg_pollution=0.0, commercial_count=100) == 100
```

Add `import pytest` at the top of the file.

- [ ] **Step 2: Run — verify FAIL**

```bash
cd backend && uv run pytest tests/test_simulation.py -v
```

Expected: `ModuleNotFoundError: No module named 'workers.simulation'`

- [ ] **Step 3: Create `backend/workers/simulation.py`** (rule functions only — no tasks yet)

```python
import logging
from datetime import datetime, timezone

from bson import ObjectId

from app.config import settings
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

TAX_RATE_PER_TICK = 0.1

# Lazy MongoClient
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
```

Tasks (`tick_all_cities`, `simulate_city_tick`) will be added in Task 5.

- [ ] **Step 4: Run — verify PASS**

```bash
cd backend && uv run pytest tests/test_simulation.py -v
```

Expected: all 14 unit tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/workers/simulation.py backend/tests/test_simulation.py
git commit -m "feat: implement simulation rule functions with unit tests"
```

---

## Task 5: `simulate_city_tick` + `tick_all_cities` — Integration Test

TDD: write the integration test, then implement the Celery tasks.

**Files:**
- Modify: `backend/tests/test_simulation.py`
- Modify: `backend/workers/simulation.py`

- [ ] **Step 1: Add integration test to `backend/tests/test_simulation.py`**

```python
from datetime import datetime, timezone
from bson import ObjectId
from unittest.mock import patch


def test_simulate_city_tick_updates_all_stats(pymongo_db):
    """simulate_city_tick reads chunks, applies rules, updates city.global_stats."""
    from workers.simulation import simulate_city_tick

    city_id = ObjectId()
    now = datetime.now(timezone.utc)

    pymongo_db.cities.insert_one({
        "_id": city_id,
        "name": "TestCity",
        "global_stats": {"population": 10, "happiness": 50, "treasury": 10000},
        "last_updated": now,
    })

    # One residential chunk with power + water → population should grow
    pymongo_db.chunks.insert_one({
        "city_id": city_id,
        "coordinates": {"x": 0, "y": 0},
        "version": 0,
        "last_updated": now,
        "base": {
            "terrain": [[0] * 16 for _ in range(16)],
            "buildings": [{"type": "residential"}],
            "roads": [],
        },
        "layers": {
            "electricity": {"coverage": 1.0},
            "water": {"coverage": 1.0},
            "pollution": {"coverage": 0.0},
        },
    })

    with patch("workers.simulation._get_db", return_value=pymongo_db):
        simulate_city_tick.apply(kwargs={"city_id": str(city_id)})

    updated = pymongo_db.cities.find_one({"_id": city_id})
    assert updated["global_stats"]["population"] == 11                              # grew by 1
    assert updated["global_stats"]["treasury"] == pytest.approx(10000 + 11 * 0.1)  # TAX_RATE_PER_TICK=0.1 on new_pop=11
    assert 0 <= updated["global_stats"]["happiness"] <= 100                         # happiness set
    assert updated["last_updated"] >= now


def test_simulate_city_tick_no_chunks_returns_early(pymongo_db):
    """simulate_city_tick with no chunks for city_id returns without error."""
    from workers.simulation import simulate_city_tick

    with patch("workers.simulation._get_db", return_value=pymongo_db):
        result = simulate_city_tick.apply(kwargs={"city_id": str(ObjectId())})

    assert result.successful()


def test_simulate_city_tick_no_city_doc_returns_early(pymongo_db):
    """simulate_city_tick with chunks but no city document returns without error."""
    from workers.simulation import simulate_city_tick

    city_id = ObjectId()
    now = datetime.now(timezone.utc)
    # Insert chunks but NO city document — exercises the `if not city: return` branch
    pymongo_db.chunks.insert_one({
        "city_id": city_id,
        "coordinates": {"x": 0, "y": 0},
        "version": 0,
        "last_updated": now,
        "base": {"terrain": [[0] * 16 for _ in range(16)], "buildings": [], "roads": []},
        "layers": {"electricity": {}, "pollution": {}, "water": {}},
    })

    with patch("workers.simulation._get_db", return_value=pymongo_db):
        result = simulate_city_tick.apply(kwargs={"city_id": str(city_id)})

    assert result.successful()


def test_simulate_city_tick_version_conflict_skips_chunk(pymongo_db):
    """If chunk version changes during tick (conflict), write is skipped silently."""
    from workers.simulation import simulate_city_tick

    city_id = ObjectId()
    now = datetime.now(timezone.utc)
    pymongo_db.cities.insert_one({
        "_id": city_id,
        "global_stats": {"population": 0, "happiness": 50, "treasury": 0},
        "last_updated": now,
    })

    chunk_id = pymongo_db.chunks.insert_one({
        "city_id": city_id,
        "coordinates": {"x": 0, "y": 0},
        "version": 5,  # task will read version=5
        "last_updated": now,
        "base": {"terrain": [[0] * 16 for _ in range(16)], "buildings": [], "roads": []},
        "layers": {"electricity": {}, "pollution": {"coverage": 0.5}, "water": {}},
    }).inserted_id

    # Simulate a concurrent update: bump version before the task writes
    pymongo_db.chunks.update_one({"_id": chunk_id}, {"$inc": {"version": 1}})

    with patch("workers.simulation._get_db", return_value=pymongo_db):
        simulate_city_tick.apply(kwargs={"city_id": str(city_id)})

    chunk = pymongo_db.chunks.find_one({"_id": chunk_id})
    # Version should be 6 (the concurrent bump), not 7 (tick was skipped)
    assert chunk["version"] == 6


def test_tick_all_cities_fans_out(pymongo_db):
    """tick_all_cities dispatches simulate_city_tick for every city in the DB."""
    from workers.simulation import tick_all_cities

    city_ids = [ObjectId() for _ in range(3)]
    pymongo_db.cities.insert_many([
        {"_id": cid, "global_stats": {"population": 0, "happiness": 50, "treasury": 0}}
        for cid in city_ids
    ])

    dispatched = []

    def fake_delay(city_id):
        dispatched.append(city_id)

    with patch("workers.simulation._get_db", return_value=pymongo_db), \
         patch("workers.simulation.simulate_city_tick") as mock_task:
        mock_task.delay = fake_delay
        tick_all_cities.apply()

    assert len(dispatched) == 3
    assert set(dispatched) == {str(cid) for cid in city_ids}
```

- [ ] **Step 2: Run — verify FAIL**

```bash
cd backend && uv run pytest tests/test_simulation.py::test_simulate_city_tick_updates_all_stats -v
```

Expected: FAIL — `AttributeError: module 'workers.simulation' has no attribute 'simulate_city_tick'`

- [ ] **Step 3: Add tasks to `backend/workers/simulation.py`**

Append to the end of the file (after the pure functions):

```python
# ---------------------------------------------------------------------------
# Celery tasks
# ---------------------------------------------------------------------------

@celery_app.task(queue="simulation")
def tick_all_cities() -> None:
    """Beat entry point: fan out one simulate_city_tick per city."""
    db = _get_db()
    city_ids = [str(doc["_id"]) for doc in db.cities.find({}, {"_id": 1})]
    for city_id in city_ids:
        simulate_city_tick.delay(city_id)
    logger.info("Dispatched ticks for %d cities", len(city_ids))


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

    for chunk in chunks:
        old_version = chunk["version"]

        new_pollution = compute_new_pollution(chunk)
        all_pollution.append(new_pollution)

        total_pop_delta += compute_population_delta(chunk)

        commercial_count += sum(
            1 for b in chunk["base"].get("buildings", []) if b["type"] == "commercial"
        )

        # Conditional write: skip silently if version changed (another process beat us)
        db.chunks.update_one(
            {"_id": chunk["_id"], "version": old_version},
            {
                "$set": {
                    "layers.pollution.coverage": new_pollution,
                    "last_updated": now,
                },
                "$inc": {"version": 1},
            },
        )

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
```

- [ ] **Step 4: Run — verify PASS**

```bash
cd backend && uv run pytest tests/test_simulation.py -v
```

Expected: all tests pass (unit + integration).

- [ ] **Step 5: Commit**

```bash
git add backend/workers/simulation.py backend/tests/test_simulation.py
git commit -m "feat: implement simulate_city_tick and tick_all_cities tasks"
```

---

## Task 6: Socket.IO `build_action` Handler — Integration Test

TDD: write the socket integration test, then add the handler to `socket_handlers.py`.

**Files:**
- Create: `backend/tests/test_socket_build_action.py`
- Modify: `backend/app/socket_handlers.py`

- [ ] **Step 1: Write failing Socket.IO integration test**

Create `backend/tests/test_socket_build_action.py`:

```python
"""Integration tests for the build_action Socket.IO event handler."""

import pytest
import socketio
from unittest.mock import MagicMock, patch

from app.socket_handlers import sio
from app.services.auth import create_access_token, hash_password


@pytest.fixture
async def city_and_token(db):
    """Create a player + city and return (token, city_id_str)."""
    from app.models.player import Player
    from app.models.city import City

    player = Player(
        username="builder",
        email="builder@test.com",
        hashed_password=hash_password("pw"),
    )
    await player.insert()

    city = City(name="BuildCity", owner_id=player.id)
    await city.insert()

    token = create_access_token(str(player.id))
    return token, str(city.id)


@pytest.fixture
async def joined_client(city_and_token):
    """Connected + authenticated + city-joined Socket.IO test client."""
    import asyncio
    token, city_id = city_and_token
    client = socketio.AsyncTestClient(sio)
    await client.connect(auth={"token": token})
    await client.emit("join_city", {"city_id": city_id})
    # Yield to the event loop so the server-side join_city coroutine (which does
    # async DB lookups) runs to completion and saves city_id to the session before
    # the test body emits build_action.
    await asyncio.sleep(0)
    client.get_received()  # drain initial_state
    yield client, city_id
    await client.disconnect()


async def test_build_action_queues_task_and_acks(joined_client):
    """Valid build_action enqueues task and emits action_queued."""
    client, city_id = joined_client

    mock_send = MagicMock()
    with patch("app.socket_handlers._celery_app") as mock_app:
        mock_app.send_task = mock_send
        await client.emit(
            "build_action",
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

    received = client.get_received()
    ack = next((r for r in received if r["name"] == "action_queued"), None)
    assert ack is not None
    assert ack["args"][0]["action_type"] == "place_building"
    assert ack["args"][0]["status"] == "queued"

    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args
    assert call_kwargs.args[0] == "workers.build_actions.process_build_action"
    assert call_kwargs.kwargs["queue"] == "high_priority"
    task_kwargs = call_kwargs.kwargs["kwargs"]
    assert task_kwargs["city_id"] == city_id
    assert task_kwargs["action_type"] == "place_building"


async def test_build_action_unknown_type_emits_error(joined_client):
    """Unknown action_type returns error event, no task enqueued."""
    client, _ = joined_client

    mock_send = MagicMock()
    with patch("app.socket_handlers._celery_app") as mock_app:
        mock_app.send_task = mock_send
        await client.emit("build_action", {"action_type": "destroy_world", "payload": {}})

    received = client.get_received()
    error = next((r for r in received if r["name"] == "error"), None)
    assert error is not None
    assert "Unknown" in error["args"][0]["message"]
    mock_send.assert_not_called()


async def test_build_action_missing_action_type_emits_error(joined_client):
    """Missing action_type emits error."""
    client, _ = joined_client
    await client.emit("build_action", {"payload": {}})
    received = client.get_received()
    assert any(r["name"] == "error" for r in received)


async def test_build_action_without_joining_city_emits_error(city_and_token):
    """Client connected but not joined to a city gets an error on build_action."""
    import asyncio
    token, _ = city_and_token
    client = socketio.AsyncTestClient(sio)
    await client.connect(auth={"token": token})
    # Deliberately skip join_city — session has user_id but no city_id
    await asyncio.sleep(0)

    await client.emit("build_action", {"action_type": "place_building", "payload": {}})
    await asyncio.sleep(0)

    received = client.get_received()
    assert any(r["name"] == "error" for r in received)
    await client.disconnect()
```

- [ ] **Step 2: Run — verify FAIL**

```bash
cd backend && uv run pytest tests/test_socket_build_action.py -v
```

Expected: FAIL — `ImportError` or event not handled (no `build_action` event registered yet).

- [ ] **Step 3: Add `build_action` handler to `backend/app/socket_handlers.py`**

Add the following imports near the top of `socket_handlers.py` (alongside existing imports):

```python
from app.constants import VALID_ACTION_TYPES
from workers.celery_app import celery_app as _celery_app
```

Then append the new event handler at the bottom of the file:

```python
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
```

- [ ] **Step 4: Run — verify PASS**

```bash
cd backend && uv run pytest tests/test_socket_build_action.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Run full test suite**

```bash
cd backend && uv run pytest -v
```

Expected: all tests pass (no regressions).

- [ ] **Step 6: Commit**

```bash
git add backend/app/socket_handlers.py backend/tests/test_socket_build_action.py
git commit -m "feat: add build_action Socket.IO handler wired to Celery queue"
```

---

## Verification

After all tasks are complete, verify the full pipeline runs end-to-end:

- [ ] **Start services**

```bash
# From project root
docker-compose up -d
```

- [ ] **Start backend**

```bash
cd backend && uv run uvicorn app.main:socket_app --reload
```

- [ ] **Start worker**

```bash
cd backend && uv run celery -A workers.celery_app worker -Q simulation,high_priority -l info
```

- [ ] **Start Beat (separate terminal)**

```bash
cd backend && uv run celery -A workers.celery_app beat -l info
```

Expected in Beat output: `tick-all-cities` fires every 10 seconds. Expected in worker output: `workers.simulation.tick_all_cities` task received and processed.

- [ ] **Run full test suite one final time**

```bash
cd backend && uv run pytest -v
```

Expected: all tests pass.

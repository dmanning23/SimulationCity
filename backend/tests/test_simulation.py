"""Unit tests for simulation rule functions (no DB required)."""
import pytest
from datetime import datetime, timezone
from bson import ObjectId
from unittest.mock import MagicMock, patch


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


# --- Integration tests (require pymongo_db fixture) ---

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
    assert 0 <= updated["global_stats"]["happiness"] <= 100
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

    stale_chunk = {
        "city_id": city_id,
        "coordinates": {"x": 0, "y": 0},
        "version": 5,  # stale snapshot the task will "read"
        "last_updated": now,
        "base": {"terrain": [[0] * 16 for _ in range(16)], "buildings": [], "roads": []},
        "layers": {"electricity": {}, "pollution": {"coverage": 0.5}, "water": {}},
    }
    chunk_id = pymongo_db.chunks.insert_one(stale_chunk.copy()).inserted_id
    stale_chunk["_id"] = chunk_id

    # Simulate concurrent update: DB is now at version=6 while task will see version=5
    pymongo_db.chunks.update_one({"_id": chunk_id}, {"$inc": {"version": 1}})

    # Give the task a stale find() result (version=5) while routing writes to the real DB.
    # The conditional update {version: 5} won't match the real DB (version=6) → skipped.
    mock_db = MagicMock()
    mock_db.chunks.find.return_value = [stale_chunk]
    mock_db.chunks.update_one.side_effect = pymongo_db.chunks.update_one
    mock_db.cities.find_one.side_effect = pymongo_db.cities.find_one
    mock_db.cities.update_one.side_effect = pymongo_db.cities.update_one

    with patch("workers.simulation._get_db", return_value=mock_db):
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

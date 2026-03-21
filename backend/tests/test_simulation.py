"""Unit tests for simulation rule functions (no DB required)."""
import pytest


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

"""Unit tests for change stream routing helpers."""
import pytest
from bson import ObjectId

_CITY_OID = ObjectId("000000000000000000000001")


# --- helpers ---

def _chunk_event(updated_fields: dict, full_doc: dict) -> dict:
    return {
        "operationType": "update",
        "_id": {"_data": "resume_token"},
        "updateDescription": {"updatedFields": updated_fields},
        "fullDocument": full_doc,
    }


def _city_event(updated_fields: dict, full_doc: dict) -> dict:
    return {
        "operationType": "update",
        "_id": {"_data": "resume_token"},
        "updateDescription": {"updatedFields": updated_fields},
        "fullDocument": full_doc,
    }


def _chunk_doc(city_id=_CITY_OID, x=2, y=3):
    return {
        "city_id": city_id,
        "coordinates": {"x": x, "y": y},
        "layers": {
            "electricity": {},
            "pollution": {"coverage": 0.3},
            "water": {},
        },
        "base": {
            "buildings": [{"id": "b1", "type": "residential"}],
            "roads": [],
            "terrain": [[0] * 16 for _ in range(16)],
        },
        "version": 1,
    }


def _city_doc(city_id=_CITY_OID):
    return {
        "_id": city_id,
        "global_stats": {"population": 11, "treasury": 1001.1, "happiness": 75},
        "last_updated": "...",
    }


# --- _route_chunk_event ---

def test_route_chunk_layers_returns_layers_update():
    from app.change_stream import _route_chunk_event
    event = _chunk_event(
        {"layers.pollution.coverage": 0.3, "last_updated": "..."},
        _chunk_doc(),
    )
    result = _route_chunk_event(event)
    assert result is not None
    name, payload = result
    assert name == "layers_update"
    assert payload["city_id"] == str(_CITY_OID)
    assert payload["chunk_x"] == 2
    assert payload["chunk_y"] == 3
    assert payload["layers"] == {
        "electricity": {},
        "pollution": {"coverage": 0.3},
        "water": {},
    }


def test_route_chunk_layers_not_suppressed_by_last_updated():
    """last_updated co-occurring with layers.* must not suppress the event."""
    from app.change_stream import _route_chunk_event
    event = _chunk_event(
        {"layers.pollution.coverage": 0.1, "last_updated": "...", "version": 2},
        _chunk_doc(),
    )
    result = _route_chunk_event(event)
    assert result is not None
    assert result[0] == "layers_update"


def test_route_chunk_push_buildings_returns_chunk_update():
    """$push generates base.buildings.<index> — must match the prefix."""
    from app.change_stream import _route_chunk_event
    doc = _chunk_doc()
    event = _chunk_event(
        {"base.buildings.0": {"id": "b1", "type": "residential"}, "last_updated": "..."},
        doc,
    )
    result = _route_chunk_event(event)
    assert result is not None
    name, payload = result
    assert name == "chunk_update"
    assert payload["city_id"] == str(_CITY_OID)
    assert payload["chunk_x"] == 2
    assert payload["chunk_y"] == 3
    assert payload["buildings"] == doc["base"]["buildings"]
    assert payload["roads"] == []
    assert "terrain" not in payload


def test_route_chunk_only_bookkeeping_skipped():
    from app.change_stream import _route_chunk_event
    event = _chunk_event({"last_updated": "...", "version": 2}, _chunk_doc())
    assert _route_chunk_event(event) is None


# --- _route_city_event ---

def test_route_city_global_stats_returns_stats_update():
    from app.change_stream import _route_city_event
    event = _city_event(
        {
            "global_stats.population": 11,
            "global_stats.treasury": 1001.1,
            "global_stats.happiness": 75,
            "last_updated": "...",
        },
        _city_doc(),
    )
    result = _route_city_event(event)
    assert result is not None
    name, payload = result
    assert name == "stats_update"
    assert payload["city_id"] == str(_CITY_OID)
    assert payload["population"] == 11
    assert payload["treasury"] == pytest.approx(1001.1)
    assert payload["happiness"] == 75


def test_route_city_only_last_updated_skipped():
    from app.change_stream import _route_city_event
    event = _city_event({"last_updated": "..."}, _city_doc())
    assert _route_city_event(event) is None

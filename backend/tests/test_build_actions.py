from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from bson import ObjectId


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


def test_unknown_action_type_returns_silently(caplog):
    """Unknown action_type logs a warning and returns — does not raise."""
    import logging
    from workers.build_actions import process_build_action

    with caplog.at_level(logging.WARNING):
        result = process_build_action.apply(
            kwargs={
                "city_id": "000000000000000000000001",
                "user_id": "000000000000000000000002",
                "action_type": "launch_missiles",
                "payload": {},
            }
        )
    assert result.successful()
    assert any("launch_missiles" in r.message for r in caplog.records)


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

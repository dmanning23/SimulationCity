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

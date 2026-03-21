# Canonical set of player action types.
# Validated at the Socket.IO boundary (socket_handlers.py) before enqueueing
# to the high_priority Celery queue.
VALID_ACTION_TYPES: frozenset[str] = frozenset({
    "place_building",
    "place_road",
    "place_zone",
    "demolish",
})

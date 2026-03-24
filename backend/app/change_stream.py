"""MongoDB change stream listener — broadcasts real-time events to Socket.IO city rooms.

Routing uses prefix matching against updateDescription.updatedFields keys:
  - chunks: "layers.*"         → layers_update
  - chunks: "base.buildings.*" → chunk_update  ($push generates "base.buildings.<N>")
  - cities: "global_stats.*"   → stats_update

Watchers and the public watch_changes() coroutine are in this same file (Task 2).
"""
import asyncio
import logging

import socketio

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Routing helpers — pure functions, no I/O
# ---------------------------------------------------------------------------

def _route_chunk_event(event: dict) -> tuple[str, dict] | None:
    """Return (socket_event_name, payload) for a chunk change event, or None to skip."""
    updated_fields = event.get("updateDescription", {}).get("updatedFields", {})
    keys = set(updated_fields.keys())

    full_doc = event.get("fullDocument") or {}
    city_id = str(full_doc.get("city_id", ""))
    coordinates = full_doc.get("coordinates", {})
    chunk_x = coordinates.get("x")
    chunk_y = coordinates.get("y")

    if any(k.startswith("layers.") for k in keys):
        return "layers_update", {
            "city_id": city_id,
            "chunk_x": chunk_x,
            "chunk_y": chunk_y,
            "layers": full_doc.get("layers", {}),
        }

    # $push to base.buildings generates keys like "base.buildings.3" — use prefix match
    if any(k.startswith("base.buildings.") for k in keys):
        base = full_doc.get("base", {})
        return "chunk_update", {
            "city_id": city_id,
            "chunk_x": chunk_x,
            "chunk_y": chunk_y,
            "buildings": base.get("buildings", []),
            "roads": base.get("roads", []),
        }

    return None


def _route_city_event(event: dict) -> tuple[str, dict] | None:
    """Return (socket_event_name, payload) for a city change event, or None to skip."""
    updated_fields = event.get("updateDescription", {}).get("updatedFields", {})
    keys = set(updated_fields.keys())

    if not any(k.startswith("global_stats.") for k in keys):
        return None

    full_doc = event.get("fullDocument") or {}
    city_id = str(full_doc.get("_id", ""))
    stats = full_doc.get("global_stats", {})

    return "stats_update", {
        "city_id": city_id,
        "population": stats.get("population", 0),
        "treasury": stats.get("treasury", 0.0),
        "happiness": stats.get("happiness", 0),
    }

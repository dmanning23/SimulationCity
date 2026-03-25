"""Per-session chunk subscription store.

Two in-memory indexes, kept in sync:
  session_subscriptions: session_id → set of chunk keys ("city_id:x:y")
  chunk_subscribers:     chunk_key  → set of session IDs

All access is from async coroutines on the same event loop — no locking needed.
"""

session_subscriptions: dict[str, set[str]] = {}
chunk_subscribers: dict[str, set[str]] = {}


def update_viewport(
    session_id: str,
    city_id: str,
    min_x: int,
    min_y: int,
    max_x: int,
    max_y: int,
) -> tuple[set[str], set[str]]:
    """Replace the subscription for session_id with the chunks in the given bbox.

    Returns (added_chunk_keys, removed_chunk_keys).
    """
    new_keys = {
        f"{city_id}:{x}:{y}"
        for x in range(min_x, max_x + 1)
        for y in range(min_y, max_y + 1)
    }
    old_keys = session_subscriptions.get(session_id, set())

    added = new_keys - old_keys
    removed = old_keys - new_keys

    session_subscriptions[session_id] = new_keys

    for key in added:
        chunk_subscribers.setdefault(key, set()).add(session_id)

    for key in removed:
        sids = chunk_subscribers.get(key)
        if sids:
            sids.discard(session_id)
            if not sids:
                del chunk_subscribers[key]

    return added, removed


def remove_session(session_id: str) -> None:
    """Remove session from both indexes. No-op if session not present."""
    keys = session_subscriptions.pop(session_id, set())
    for key in keys:
        sids = chunk_subscribers.get(key)
        if sids:
            sids.discard(session_id)
            if not sids:
                del chunk_subscribers[key]


def get_subscribers(chunk_key: str) -> set[str]:
    """Return a copy of the set of session IDs subscribed to chunk_key. O(1)."""
    return set(chunk_subscribers.get(chunk_key, set()))

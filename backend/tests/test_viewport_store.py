"""Unit tests for viewport_store — pure Python, no I/O."""
import pytest
import app.viewport_store as store
from app.viewport_store import update_viewport, remove_session, get_subscribers


@pytest.fixture(autouse=True)
def clear_store():
    store.session_subscriptions.clear()
    store.chunk_subscribers.clear()
    yield
    store.session_subscriptions.clear()
    store.chunk_subscribers.clear()


def test_first_call_adds_all_bbox_chunks():
    added, removed = update_viewport("sid1", "city1", 0, 0, 1, 1)
    expected = {"city1:0:0", "city1:0:1", "city1:1:0", "city1:1:1"}
    assert added == expected
    assert removed == set()
    assert store.session_subscriptions["sid1"] == expected
    for key in expected:
        assert "sid1" in store.chunk_subscribers[key]


def test_overlapping_move_only_diffs_change():
    update_viewport("sid1", "city1", 0, 0, 2, 2)   # 3×3 grid
    added, removed = update_viewport("sid1", "city1", 1, 1, 3, 3)  # shift right+down

    overlap = {"city1:1:1", "city1:1:2", "city1:2:1", "city1:2:2"}
    for key in overlap:
        assert key not in added and key not in removed

    assert "city1:3:3" in added    # new corner
    assert "city1:0:0" in removed  # old corner


def test_disjoint_move_replaces_all():
    update_viewport("sid1", "city1", 0, 0, 0, 0)
    added, removed = update_viewport("sid1", "city1", 5, 5, 5, 5)
    assert added == {"city1:5:5"}
    assert removed == {"city1:0:0"}
    assert "sid1" not in store.chunk_subscribers.get("city1:0:0", set())
    assert "sid1" in store.chunk_subscribers.get("city1:5:5", set())


def test_remove_session_clears_both_indexes():
    update_viewport("sid1", "city1", 0, 0, 1, 1)
    remove_session("sid1")
    assert "sid1" not in store.session_subscriptions
    for subscribers in store.chunk_subscribers.values():
        assert "sid1" not in subscribers


def test_remove_session_noop_for_unknown_session():
    remove_session("ghost-sid")  # must not raise


def test_get_subscribers_returns_all_watching_sessions():
    update_viewport("sid1", "city1", 0, 0, 0, 0)
    update_viewport("sid2", "city1", 0, 0, 0, 0)
    subs = get_subscribers("city1:0:0")
    assert "sid1" in subs and "sid2" in subs


def test_get_subscribers_unknown_key_returns_empty_set():
    assert get_subscribers("city1:99:99") == set()


def test_get_subscribers_isolates_non_watching_sessions():
    update_viewport("sid1", "city1", 0, 0, 0, 0)
    update_viewport("sid2", "city1", 5, 5, 5, 5)
    assert get_subscribers("city1:0:0") == {"sid1"}
    assert get_subscribers("city1:5:5") == {"sid2"}


def test_remove_session_does_not_affect_other_sessions():
    update_viewport("sid1", "city1", 0, 0, 0, 0)
    update_viewport("sid2", "city1", 0, 0, 0, 0)
    remove_session("sid1")
    assert get_subscribers("city1:0:0") == {"sid2"}

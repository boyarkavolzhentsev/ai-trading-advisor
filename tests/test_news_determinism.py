"""Determinism: identical inputs produce identical, order-independent results."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.core.models.news_item import NewsItem
from app.news.history import NewsItemHistory


def _item(now: datetime, **overrides: object) -> NewsItem:
    fields: dict[str, object] = {
        "provider": "testnews",
        "provider_item_id": "story-1",
        "headline": "Central bank holds rates steady",
        "published_at": now,
        "received_at": now,
    }
    fields.update(overrides)
    return NewsItem(**fields)


def test_model_construction_is_deterministic(now: datetime) -> None:
    first = _item(now)
    second = _item(now)
    assert first == second
    assert first.model_dump() == second.model_dump()


def test_history_ordering_is_independent_of_insertion_order(now: datetime) -> None:
    items = [
        _item(now + timedelta(hours=offset), provider_item_id=f"story-{offset}")
        for offset in (3, 1, 4, 0, 2)
    ]

    forward = NewsItemHistory()
    for item in items:
        forward.append(item)

    backward = NewsItemHistory()
    for item in reversed(items):
        backward.append(item)

    forward_ids = [i.provider_item_id for i in forward.all_items()]
    backward_ids = [i.provider_item_id for i in backward.all_items()]
    assert forward_ids == backward_ids == ["story-0", "story-1", "story-2", "story-3", "story-4"]


def test_history_append_twice_with_same_items_yields_same_state(now: datetime) -> None:
    items = [_item(now, provider_item_id=f"story-{i}") for i in range(5)]

    first = NewsItemHistory()
    second = NewsItemHistory()
    for item in items:
        first.append(item)
        second.append(item)

    assert [i.model_dump() for i in first.all_items()] == [i.model_dump() for i in second.all_items()]


def test_no_wall_clock_or_randomness_used_by_history() -> None:
    import inspect

    source = inspect.getsource(NewsItemHistory)
    for forbidden in ("datetime.now", "utcnow", "random.", "uuid."):
        assert forbidden not in source

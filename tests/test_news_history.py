"""Stage 4C ``NewsItemHistory`` append/duplicate/version/eviction/query semantics."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.core.models.news_item import NewsItem
from app.news.exceptions import DuplicateNewsItemError
from app.news.history import DEFAULT_CAPACITY, NewsItemHistory


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


def test_default_capacity_matches_siblings() -> None:
    assert DEFAULT_CAPACITY == 512


def test_append_a_new_identity_is_retained(now: datetime) -> None:
    history = NewsItemHistory()
    history.append(_item(now))
    assert len(history) == 1


def test_exact_semantic_repoll_raises_duplicate_and_leaves_history_unchanged(now: datetime) -> None:
    history = NewsItemHistory()
    history.append(_item(now))

    with pytest.raises(DuplicateNewsItemError):
        history.append(_item(now, received_at=now + timedelta(minutes=10)))

    assert len(history) == 1
    assert history.dropped_count == 0


def test_changed_content_under_same_identity_is_appended_not_rejected(now: datetime) -> None:
    """Required design decision: a corrected headline/body at the same
    identity is a legitimate new version, never a conflict."""
    history = NewsItemHistory()
    history.append(_item(now, headline="Central bank holds rates steady"))
    history.append(
        _item(
            now,
            headline="Central bank holds rates steady, signals cuts ahead",
            updated_at=now + timedelta(minutes=15),
            received_at=now + timedelta(minutes=15),
        )
    )
    assert len(history) == 2


def test_updated_at_earlier_than_published_at_does_not_block_append(now: datetime) -> None:
    """Required correction: history must not reject or repair an
    out-of-order updated_at/published_at pair - only preserve it."""
    history = NewsItemHistory()
    earlier = now - timedelta(days=1)
    item = _item(now, published_at=now, updated_at=earlier)
    history.append(item)
    assert len(history) == 1
    assert history.latest_version("testnews", "story-1").updated_at == earlier


def test_versions_for_preserves_append_order(now: datetime) -> None:
    history = NewsItemHistory()
    first = _item(now, headline="Initial report")
    second = _item(
        now,
        headline="Initial report, updated with details",
        received_at=now + timedelta(minutes=5),
    )
    third = _item(
        now,
        headline="Initial report, correction issued",
        received_at=now + timedelta(minutes=20),
    )
    history.append(first)
    history.append(second)
    history.append(third)

    versions = history.versions_for("testnews", "story-1")
    assert [v.headline for v in versions] == [
        "Initial report",
        "Initial report, updated with details",
        "Initial report, correction issued",
    ]


def test_latest_version_returns_most_recently_appended(now: datetime) -> None:
    history = NewsItemHistory()
    history.append(_item(now, headline="Initial report"))
    history.append(
        _item(now, headline="Updated report", received_at=now + timedelta(minutes=5))
    )
    latest = history.latest_version("testnews", "story-1")
    assert latest is not None
    assert latest.headline == "Updated report"


def test_latest_version_returns_none_for_unknown_identity(now: datetime) -> None:
    history = NewsItemHistory()
    history.append(_item(now))
    assert history.latest_version("testnews", "unknown-story") is None


def test_versions_for_returns_empty_list_for_unknown_identity(now: datetime) -> None:
    history = NewsItemHistory()
    history.append(_item(now))
    assert history.versions_for("testnews", "unknown-story") == []


def test_all_items_orders_by_published_at_then_provider_then_id(now: datetime) -> None:
    history = NewsItemHistory()
    history.append(_item(now + timedelta(hours=2), provider_item_id="story-b"))
    history.append(_item(now, provider_item_id="story-a"))
    history.append(_item(now + timedelta(hours=1), provider_item_id="story-c"))

    ordered_ids = [i.provider_item_id for i in history.all_items()]
    assert ordered_ids == ["story-a", "story-c", "story-b"]


def test_all_items_includes_every_retained_version_not_just_latest(now: datetime) -> None:
    history = NewsItemHistory()
    history.append(_item(now, headline="Initial report"))
    history.append(
        _item(now, headline="Updated report", received_at=now + timedelta(minutes=5))
    )
    assert len(history.all_items()) == 2


def test_by_provider_filters_to_one_provider(now: datetime) -> None:
    history = NewsItemHistory()
    history.append(_item(now, provider="providerA", provider_item_id="a-1"))
    history.append(_item(now, provider="providerB", provider_item_id="b-1"))

    results = history.by_provider("providerA")
    assert [i.provider for i in results] == ["providerA"]


def test_eviction_is_drop_oldest_and_tracked(now: datetime) -> None:
    history = NewsItemHistory(capacity=2)
    history.append(_item(now, provider_item_id="story-1"))
    history.append(_item(now, provider_item_id="story-2"))
    history.append(_item(now, provider_item_id="story-3"))

    assert len(history) == 2
    assert history.dropped_count == 1
    remaining_ids = {i.provider_item_id for i in history.all_items()}
    assert remaining_ids == {"story-2", "story-3"}


def test_history_instances_are_independent(now: datetime) -> None:
    first = NewsItemHistory()
    second = NewsItemHistory()
    first.append(_item(now))
    assert len(first) == 1
    assert len(second) == 0

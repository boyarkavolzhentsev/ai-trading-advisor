"""Stage 4D ``NewsSentimentObservationHistory`` append/duplicate/version/eviction/query semantics."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.core.models.news_sentiment_observation import NewsSentimentObservation
from app.news_intel.exceptions import DuplicateNewsSentimentError
from app.news_intel.sentiment_history import DEFAULT_CAPACITY, NewsSentimentObservationHistory


def _observation(now: datetime, **overrides: object) -> NewsSentimentObservation:
    fields: dict[str, object] = {
        "provider": "sentvendor",
        "source_provider": "testnews",
        "source_provider_item_id": "story-1",
        "source_received_at": now,
        "published_at": now,
        "received_at": now,
        "sentiment_label": "positive",
    }
    fields.update(overrides)
    return NewsSentimentObservation(**fields)


def test_default_capacity_matches_siblings() -> None:
    assert DEFAULT_CAPACITY == 512


def test_append_a_new_identity_is_retained(now: datetime) -> None:
    history = NewsSentimentObservationHistory()
    history.append(_observation(now))
    assert len(history) == 1


def test_exact_semantic_repoll_raises_duplicate_and_leaves_history_unchanged(now: datetime) -> None:
    history = NewsSentimentObservationHistory()
    history.append(_observation(now))

    with pytest.raises(DuplicateNewsSentimentError):
        history.append(_observation(now, received_at=now + timedelta(minutes=10)))

    assert len(history) == 1
    assert history.dropped_count == 0


def test_changed_sentiment_under_same_identity_is_appended_not_rejected(now: datetime) -> None:
    history = NewsSentimentObservationHistory()
    history.append(_observation(now, sentiment_score=Decimal("0.2")))
    history.append(
        _observation(
            now,
            sentiment_score=Decimal("0.6"),
            received_at=now + timedelta(minutes=15),
        )
    )
    assert len(history) == 2


def test_different_provider_is_a_different_identity(now: datetime) -> None:
    history = NewsSentimentObservationHistory()
    history.append(_observation(now, provider="sentvendorA"))
    history.append(_observation(now, provider="sentvendorB"))
    assert len(history) == 2


def test_different_source_provider_is_a_different_identity(now: datetime) -> None:
    history = NewsSentimentObservationHistory()
    history.append(_observation(now, source_provider="newsfeedA"))
    history.append(_observation(now, source_provider="newsfeedB"))
    assert len(history) == 2


def test_different_target_symbol_is_a_different_identity(now: datetime) -> None:
    history = NewsSentimentObservationHistory()
    history.append(_observation(now, target_symbol=None))
    history.append(_observation(now, target_symbol="BTCUSDT"))
    assert len(history) == 2


def test_versions_for_preserves_append_order(now: datetime) -> None:
    history = NewsSentimentObservationHistory()
    first = _observation(now, sentiment_score=Decimal("0.1"))
    second = _observation(now, sentiment_score=Decimal("0.5"), received_at=now + timedelta(minutes=5))
    third = _observation(now, sentiment_score=Decimal("0.9"), received_at=now + timedelta(minutes=20))
    history.append(first)
    history.append(second)
    history.append(third)

    versions = history.versions_for("sentvendor", "testnews", "story-1", None)
    assert [v.sentiment_score for v in versions] == [Decimal("0.1"), Decimal("0.5"), Decimal("0.9")]


def test_latest_version_returns_most_recently_appended(now: datetime) -> None:
    history = NewsSentimentObservationHistory()
    history.append(_observation(now, sentiment_score=Decimal("0.1")))
    history.append(
        _observation(now, sentiment_score=Decimal("0.9"), received_at=now + timedelta(minutes=5))
    )
    latest = history.latest_version("sentvendor", "testnews", "story-1", None)
    assert latest is not None
    assert latest.sentiment_score == Decimal("0.9")


def test_latest_version_returns_none_for_unknown_identity(now: datetime) -> None:
    history = NewsSentimentObservationHistory()
    history.append(_observation(now))
    assert history.latest_version("sentvendor", "testnews", "unknown-story", None) is None


def test_versions_for_returns_empty_list_for_unknown_identity(now: datetime) -> None:
    history = NewsSentimentObservationHistory()
    history.append(_observation(now))
    assert history.versions_for("sentvendor", "testnews", "unknown-story", None) == []


def test_all_observations_orders_by_published_at_then_provider(now: datetime) -> None:
    history = NewsSentimentObservationHistory()
    history.append(_observation(now + timedelta(hours=2), source_provider_item_id="story-b"))
    history.append(_observation(now, source_provider_item_id="story-a"))
    history.append(_observation(now + timedelta(hours=1), source_provider_item_id="story-c"))

    ordered_ids = [o.source_provider_item_id for o in history.all_observations()]
    assert ordered_ids == ["story-a", "story-c", "story-b"]


def test_all_observations_includes_every_retained_version_not_just_latest(now: datetime) -> None:
    history = NewsSentimentObservationHistory()
    history.append(_observation(now, sentiment_score=Decimal("0.1")))
    history.append(
        _observation(now, sentiment_score=Decimal("0.9"), received_at=now + timedelta(minutes=5))
    )
    assert len(history.all_observations()) == 2


def test_by_provider_filters_to_one_sentiment_provider(now: datetime) -> None:
    history = NewsSentimentObservationHistory()
    history.append(_observation(now, provider="sentvendorA"))
    history.append(_observation(now, provider="sentvendorB"))

    results = history.by_provider("sentvendorA")
    assert [o.provider for o in results] == ["sentvendorA"]


def test_eviction_is_drop_oldest_and_tracked(now: datetime) -> None:
    history = NewsSentimentObservationHistory(capacity=2)
    history.append(_observation(now, source_provider_item_id="story-1"))
    history.append(_observation(now, source_provider_item_id="story-2"))
    history.append(_observation(now, source_provider_item_id="story-3"))

    assert len(history) == 2
    assert history.dropped_count == 1
    remaining_ids = {o.source_provider_item_id for o in history.all_observations()}
    assert remaining_ids == {"story-2", "story-3"}


def test_history_instances_are_independent(now: datetime) -> None:
    first = NewsSentimentObservationHistory()
    second = NewsSentimentObservationHistory()
    first.append(_observation(now))
    assert len(first) == 1
    assert len(second) == 0


def test_ordering_is_independent_of_insertion_order(now: datetime) -> None:
    observations = [
        _observation(now + timedelta(hours=offset), source_provider_item_id=f"story-{offset}")
        for offset in (3, 1, 4, 0, 2)
    ]

    forward = NewsSentimentObservationHistory()
    for observation in observations:
        forward.append(observation)

    backward = NewsSentimentObservationHistory()
    for observation in reversed(observations):
        backward.append(observation)

    forward_ids = [o.source_provider_item_id for o in forward.all_observations()]
    backward_ids = [o.source_provider_item_id for o in backward.all_observations()]
    assert forward_ids == backward_ids == ["story-0", "story-1", "story-2", "story-3", "story-4"]


def test_no_wall_clock_or_randomness_used_by_history() -> None:
    import inspect

    source = inspect.getsource(NewsSentimentObservationHistory)
    for forbidden in ("datetime.now", "utcnow", "random.", "uuid."):
        assert forbidden not in source

"""Stage 4F ``classify_quality`` semantic-timestamp staleness semantics."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.core.enums.quality import FeatureQuality
from app.external_intelligence_analysts.base import classify_quality


def test_recent_source_time_is_valid(now: datetime) -> None:
    source_time = now - timedelta(hours=1)
    assert classify_quality(source_time, now, timedelta(hours=6)) is FeatureQuality.VALID


def test_source_time_older_than_threshold_is_stale(now: datetime) -> None:
    source_time = now - timedelta(hours=10)
    assert classify_quality(source_time, now, timedelta(hours=6)) is FeatureQuality.STALE


def test_source_time_exactly_at_threshold_is_valid(now: datetime) -> None:
    threshold = timedelta(hours=6)
    source_time = now - threshold
    assert classify_quality(source_time, now, threshold) is FeatureQuality.VALID


def test_source_time_one_second_past_threshold_is_stale(now: datetime) -> None:
    threshold = timedelta(hours=6)
    source_time = now - threshold - timedelta(seconds=1)
    assert classify_quality(source_time, now, threshold) is FeatureQuality.STALE


def test_future_source_time_is_valid_not_stale(now: datetime) -> None:
    """Required correction: staleness is strictly a 'too old' condition -
    a source_time in the future must never be classified STALE."""
    future_source_time = now + timedelta(days=365)
    assert classify_quality(future_source_time, now, timedelta(hours=1)) is FeatureQuality.VALID


def test_source_time_equal_to_analysis_time_is_valid(now: datetime) -> None:
    assert classify_quality(now, now, timedelta(seconds=0)) is FeatureQuality.VALID


def test_classify_quality_never_returns_partial(now: datetime) -> None:
    for delta_hours in (-1000, -1, 0, 1, 1000):
        result = classify_quality(now + timedelta(hours=delta_hours), now, timedelta(hours=1))
        assert result is not FeatureQuality.PARTIAL


def test_classify_quality_never_returns_unavailable(now: datetime) -> None:
    for delta_hours in (-1000, -1, 0, 1, 1000):
        result = classify_quality(now + timedelta(hours=delta_hours), now, timedelta(hours=1))
        assert result is not FeatureQuality.UNAVAILABLE


def test_classify_quality_is_deterministic(now: datetime) -> None:
    source_time = now - timedelta(hours=3)
    first = classify_quality(source_time, now, timedelta(hours=6))
    second = classify_quality(source_time, now, timedelta(hours=6))
    assert first is second


def test_classify_quality_does_not_read_wall_clock() -> None:
    import inspect

    source = inspect.getsource(classify_quality)
    for forbidden in ("datetime.now", "utcnow", "time.time", "random.", "uuid."):
        assert forbidden not in source

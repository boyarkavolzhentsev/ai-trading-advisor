"""Tests for app.flow.windows: UTC epoch-aligned window boundaries, membership, lookups."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from app.core.models.analytics_window import AnalyticsWindow
from app.flow.windows import (
    DEFAULT_WINDOWS,
    epoch_bucket_start,
    latest_at_or_before,
    select_window,
    validate_unique_labels,
    window_bounds,
)

# UTC midnight: 86400s/day is an exact multiple of every default window
# duration (10s/30s/1m/5m/15m all divide 86400), so this instant is
# simultaneously epoch-aligned for all of them - a clean, reusable anchor.
ANCHOR = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class _Timestamped:
    timestamp: datetime
    value: int


def test_default_windows_labels_and_durations() -> None:
    labels = {window.label: window.duration for window in DEFAULT_WINDOWS}
    assert labels == {
        "10s": timedelta(seconds=10),
        "30s": timedelta(seconds=30),
        "1m": timedelta(minutes=1),
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
    }


def test_analytics_window_rejects_non_positive_duration() -> None:
    with pytest.raises(ValueError, match="positive"):
        AnalyticsWindow(label="bad", duration=timedelta(0))
    with pytest.raises(ValueError, match="positive"):
        AnalyticsWindow(label="bad", duration=timedelta(seconds=-1))


# --- UTC epoch alignment, one case per approved default window -------------


def test_10s_epoch_alignment() -> None:
    observation_time = ANCHOR + timedelta(seconds=37)  # not on a 10s boundary
    start, end = window_bounds(observation_time, timedelta(seconds=10))
    assert end == ANCHOR + timedelta(seconds=30)
    assert start == ANCHOR + timedelta(seconds=20)


def test_30s_epoch_alignment() -> None:
    observation_time = ANCHOR + timedelta(seconds=47)  # not on a 30s boundary
    start, end = window_bounds(observation_time, timedelta(seconds=30))
    assert end == ANCHOR + timedelta(seconds=30)
    assert start == ANCHOR


def test_1m_epoch_alignment() -> None:
    observation_time = ANCHOR + timedelta(seconds=90)  # 1:30, not on a 1m boundary
    start, end = window_bounds(observation_time, timedelta(minutes=1))
    assert end == ANCHOR + timedelta(minutes=1)
    assert start == ANCHOR


def test_5m_epoch_alignment() -> None:
    observation_time = ANCHOR + timedelta(minutes=7, seconds=10)  # not on a 5m boundary
    start, end = window_bounds(observation_time, timedelta(minutes=5))
    assert end == ANCHOR + timedelta(minutes=5)
    assert start == ANCHOR


def test_15m_epoch_alignment() -> None:
    observation_time = ANCHOR + timedelta(minutes=20)  # not on a 15m boundary
    start, end = window_bounds(observation_time, timedelta(minutes=15))
    assert end == ANCHOR + timedelta(minutes=15)
    assert start == ANCHOR


def test_observation_time_exactly_on_a_boundary_is_its_own_window_end() -> None:
    observation_time = ANCHOR + timedelta(minutes=10)  # exact 5m grid line
    start, end = window_bounds(observation_time, timedelta(minutes=5))
    assert end == observation_time
    assert start == ANCHOR + timedelta(minutes=5)


# --- membership: (window_start, window_end] --------------------------------


def test_event_exactly_at_window_start_is_excluded() -> None:
    observation_time = ANCHOR + timedelta(seconds=37)
    duration = timedelta(seconds=10)
    window_start, _ = window_bounds(observation_time, duration)
    items = [_Timestamped(timestamp=window_start, value=1)]
    selected = select_window(items, timestamp_of=lambda i: i.timestamp, observation_time=observation_time, duration=duration)
    assert selected == []


def test_event_exactly_at_window_end_is_included() -> None:
    observation_time = ANCHOR + timedelta(seconds=37)
    duration = timedelta(seconds=10)
    _, window_end = window_bounds(observation_time, duration)
    items = [_Timestamped(timestamp=window_end, value=1)]
    selected = select_window(items, timestamp_of=lambda i: i.timestamp, observation_time=observation_time, duration=duration)
    assert [i.value for i in selected] == [1]


def test_event_after_aligned_window_end_is_excluded_even_if_before_observation_time() -> None:
    # observation_time=37s, duration=10s -> aligned window is (20s, 30s].
    # An event at 35s is after window_end but still before observation_time:
    # under the old trailing-window design this would have been included,
    # but it belongs to the next, not-yet-closed aligned bucket.
    observation_time = ANCHOR + timedelta(seconds=37)
    duration = timedelta(seconds=10)
    items = [_Timestamped(timestamp=ANCHOR + timedelta(seconds=35), value=1)]
    selected = select_window(items, timestamp_of=lambda i: i.timestamp, observation_time=observation_time, duration=duration)
    assert selected == []


def test_select_window_full_boundary_sweep() -> None:
    observation_time = ANCHOR + timedelta(seconds=37)
    duration = timedelta(seconds=10)
    window_start, window_end = window_bounds(observation_time, duration)
    items = [
        _Timestamped(timestamp=window_start, value=1),  # excluded: at window_start
        _Timestamped(timestamp=window_start + timedelta(microseconds=1), value=2),  # included: just inside
        _Timestamped(timestamp=window_start + timedelta(seconds=5), value=3),  # included: inside
        _Timestamped(timestamp=window_end, value=4),  # included: at window_end
        _Timestamped(timestamp=window_end + timedelta(microseconds=1), value=5),  # excluded: after window_end
    ]
    selected = select_window(items, timestamp_of=lambda i: i.timestamp, observation_time=observation_time, duration=duration)
    assert [item.value for item in selected] == [2, 3, 4]


def test_select_window_empty_when_nothing_qualifies() -> None:
    observation_time = ANCHOR + timedelta(seconds=37)
    items = [_Timestamped(timestamp=ANCHOR - timedelta(hours=1), value=1)]
    selected = select_window(
        items, timestamp_of=lambda i: i.timestamp, observation_time=observation_time, duration=timedelta(seconds=10)
    )
    assert selected == []


def test_select_window_tolerates_out_of_order_input() -> None:
    observation_time = ANCHOR + timedelta(seconds=37)
    duration = timedelta(seconds=10)
    items = [
        _Timestamped(timestamp=ANCHOR + timedelta(seconds=29), value=3),
        _Timestamped(timestamp=ANCHOR + timedelta(seconds=25), value=2),
        _Timestamped(timestamp=ANCHOR + timedelta(seconds=1), value=1),  # outside window
    ]
    selected = select_window(items, timestamp_of=lambda i: i.timestamp, observation_time=observation_time, duration=duration)
    assert {item.value for item in selected} == {2, 3}


# --- determinism / rollover -------------------------------------------------


def test_identical_observation_times_produce_identical_boundaries() -> None:
    observation_time = ANCHOR + timedelta(seconds=37)
    duration = timedelta(seconds=10)
    assert window_bounds(observation_time, duration) == window_bounds(observation_time, duration)


def test_different_observation_times_in_same_bucket_produce_identical_boundaries() -> None:
    duration = timedelta(seconds=10)
    a = window_bounds(ANCHOR + timedelta(seconds=31), duration)
    b = window_bounds(ANCHOR + timedelta(seconds=39, milliseconds=999), duration)
    assert a == b
    assert a == (ANCHOR + timedelta(seconds=20), ANCHOR + timedelta(seconds=30))


def test_rollover_into_next_bucket_produces_next_deterministic_boundary() -> None:
    duration = timedelta(seconds=10)
    just_before = window_bounds(ANCHOR + timedelta(seconds=39, milliseconds=999), duration)
    at_rollover = window_bounds(ANCHOR + timedelta(seconds=40), duration)
    assert just_before == (ANCHOR + timedelta(seconds=20), ANCHOR + timedelta(seconds=30))
    assert at_rollover == (ANCHOR + timedelta(seconds=30), ANCHOR + timedelta(seconds=40))
    assert just_before != at_rollover


# --- epoch_bucket_start primitive ------------------------------------------


def test_epoch_bucket_start_aligns_to_duration_grid() -> None:
    duration = timedelta(seconds=10)
    ts = datetime(2026, 1, 1, 12, 0, 37, tzinfo=UTC)
    bucket = epoch_bucket_start(ts, duration)
    assert bucket == datetime(2026, 1, 1, 12, 0, 30, tzinfo=UTC)


def test_epoch_bucket_start_on_exact_boundary_is_identity() -> None:
    duration = timedelta(minutes=1)
    ts = datetime(2026, 1, 1, 12, 5, 0, tzinfo=UTC)
    assert epoch_bucket_start(ts, duration) == ts


# --- latest_at_or_before -----------------------------------------------------


def test_latest_at_or_before_never_interpolates() -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    items = [
        _Timestamped(timestamp=now - timedelta(minutes=10), value=1),
        _Timestamped(timestamp=now - timedelta(minutes=5), value=2),
        _Timestamped(timestamp=now + timedelta(minutes=1), value=3),  # after cutoff: ignored
    ]
    result = latest_at_or_before(items, timestamp_of=lambda i: i.timestamp, cutoff=now)
    assert result is not None
    assert result.value == 2


def test_latest_at_or_before_none_when_nothing_qualifies() -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    items = [_Timestamped(timestamp=now + timedelta(seconds=1), value=1)]
    assert latest_at_or_before(items, timestamp_of=lambda i: i.timestamp, cutoff=now) is None


# --- label validation --------------------------------------------------------


def test_validate_unique_labels_allows_identical_duplicates() -> None:
    validate_unique_labels(
        [
            AnalyticsWindow(label="1m", duration=timedelta(minutes=1)),
            AnalyticsWindow(label="1m", duration=timedelta(minutes=1)),
        ]
    )


def test_validate_unique_labels_rejects_conflicting_durations() -> None:
    with pytest.raises(ValueError, match="1m"):
        validate_unique_labels(
            [
                AnalyticsWindow(label="1m", duration=timedelta(minutes=1)),
                AnalyticsWindow(label="1m", duration=timedelta(minutes=2)),
            ]
        )

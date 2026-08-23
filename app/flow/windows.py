"""Default analytics-window presets and deterministic UTC epoch-aligned
window boundaries.

``AnalyticsWindow`` is a distinct concept from ``Timeframe``
(``app.core.enums.market``): ``Timeframe`` is bound to candle-interval
provider mapping (``app.market_data.timeframes``) and has no sub-minute
members, whereas an analytics window is a free-form lookback duration with
no candle/kline equivalent. Calculators accept ``Sequence[AnalyticsWindow]``
explicitly and never hard-code a window.

``window_bounds`` is the single source of truth for turning an
``observation_time`` plus a ``duration`` into one deterministic, UTC
epoch-aligned ``(window_start, window_end)`` pair - the most recently
*completed* aligned window as of ``observation_time``, mirroring
``TakerFlowAggregator``'s own invariant that only a fully closed bucket is
ever reported, never a still-filling one:

    window_end = floor(observation_time_epoch / duration) * duration
    window_start = window_end - duration

Two observation times that fall in the same epoch bucket always produce the
identical ``(window_start, window_end)`` pair - the result depends only on
which aligned bucket ``observation_time`` falls in, never on the exact
instant within it. No calculator computes its own boundaries independently;
every windowed calculator in ``app.flow`` goes through ``window_bounds`` (or
``select_window``/``latest_at_or_before``, both built on it).

Window membership is right-closed, left-open: ``(window_start, window_end]``.
An event timestamped exactly at ``window_start`` is excluded (it belongs to
the *previous* aligned window); one timestamped exactly at ``window_end`` is
included; anything after ``window_end`` (including up to the live
``observation_time``) is excluded from this completed window - it belongs to
the next, not-yet-closed one. Event time drives membership throughout;
``observation_time`` is only ever used to pick which aligned bucket is
"most recently completed" - never as a live upper bound on membership.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import TypeVar

from app.core.models.analytics_window import AnalyticsWindow

T = TypeVar("T")

DEFAULT_WINDOWS: tuple[AnalyticsWindow, ...] = (
    AnalyticsWindow(label="10s", duration=timedelta(seconds=10)),
    AnalyticsWindow(label="30s", duration=timedelta(seconds=30)),
    AnalyticsWindow(label="1m", duration=timedelta(minutes=1)),
    AnalyticsWindow(label="5m", duration=timedelta(minutes=5)),
    AnalyticsWindow(label="15m", duration=timedelta(minutes=15)),
)
"""Configurable defaults only - never referenced positionally by calculators."""


def validate_unique_labels(windows: Sequence[AnalyticsWindow]) -> None:
    """Raise ``ValueError`` if two windows share a label with different durations.

    Two windows sharing a label with the *same* duration are tolerated
    (harmless duplicate); a label reused for two different durations would
    silently corrupt any lookup keyed by label, so it is rejected outright.
    """
    seen: dict[str, timedelta] = {}
    for window in windows:
        prior = seen.get(window.label)
        if prior is not None and prior != window.duration:
            raise ValueError(
                f"window label {window.label!r} is used for two different durations: "
                f"{prior} and {window.duration}"
            )
        seen[window.label] = window.duration


def epoch_bucket_start(timestamp: datetime, duration: timedelta) -> datetime:
    """Return the UTC epoch-aligned bucket start containing ``timestamp``.

    Low-level primitive: ``floor(timestamp_epoch / duration) * duration``.
    ``window_bounds`` is built directly on this and is the function
    calculators should use - this is exposed separately only because it is
    also useful on its own (e.g. to align an observation cadence).
    """
    duration_seconds = duration.total_seconds()
    epoch_seconds = timestamp.timestamp()
    bucket_index = int(epoch_seconds // duration_seconds)
    return datetime.fromtimestamp(bucket_index * duration_seconds, tz=UTC)


def window_bounds(observation_time: datetime, duration: timedelta) -> tuple[datetime, datetime]:
    """Return the UTC epoch-aligned ``(window_start, window_end)`` of the most
    recently completed ``duration``-wide window as of ``observation_time``.

    ``window_end = epoch_bucket_start(observation_time, duration)``;
    ``window_start = window_end - duration``. This is the single source of
    truth for window boundaries in ``app.flow`` - every windowed calculator
    computes its boundaries by calling this function (directly, or via
    ``select_window``/by using its result as a ``latest_at_or_before``
    cutoff), never by re-deriving alignment independently.
    """
    window_end = epoch_bucket_start(observation_time, duration)
    window_start = window_end - duration
    return window_start, window_end


def select_window(
    items: Sequence[T],
    *,
    timestamp_of: Callable[[T], datetime],
    observation_time: datetime,
    duration: timedelta,
) -> list[T]:
    """Select items in the aligned ``(window_start, window_end]`` from
    :func:`window_bounds`.

    ``items`` need not be pre-sorted: every item is checked independently so
    a history that tolerates late/out-of-order arrival upstream still
    windows correctly here.
    """
    window_start, window_end = window_bounds(observation_time, duration)
    return [item for item in items if window_start < timestamp_of(item) <= window_end]


def latest_at_or_before(
    items: Sequence[T],
    *,
    timestamp_of: Callable[[T], datetime],
    cutoff: datetime,
) -> T | None:
    """Return the item with the latest ``timestamp_of`` at or before ``cutoff``.

    Never interpolates: the result, if any, is always a real, previously
    observed item. ``None`` when no item qualifies.
    """
    candidates = [item for item in items if timestamp_of(item) <= cutoff]
    if not candidates:
        return None
    return max(candidates, key=timestamp_of)


__all__ = [
    "DEFAULT_WINDOWS",
    "epoch_bucket_start",
    "latest_at_or_before",
    "select_window",
    "validate_unique_labels",
    "window_bounds",
]

"""Deterministic UTC epoch-aligned candle/timeframe helpers (Stage 3A).

Deliberately independent of ``app.flow.windows``/``AnalyticsWindow``: a
candle ``Timeframe`` boundary is a different concept from a free-form
``AnalyticsWindow`` lookback bucket (see ``app.core.models.analytics_window``'s
own docstring on why the two are kept apart). The epoch-floor arithmetic is
the same idea one layer down, but this module keeps its own copy rather than
importing ``app.flow`` - Stage 3A must remain an independently testable
contour with no import edge into the flow contour.

Closed-candle policy: a candle is CLOSED as of ``as_of`` iff
``candle.timestamp + timeframe_duration(timeframe) <= as_of``. ``as_of``
must always be supplied explicitly by the caller - no helper here ever
reads the wall clock, so every result is reproducible given the same
inputs. No repainting: a candle that was CLOSED as of one ``as_of`` is
CLOSED as of any later ``as_of`` too (closedness is monotonic in
``as_of``).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from app.core.enums.market import Timeframe
from app.core.models.candle import OHLCVCandle
from app.market_data.timeframes import timeframe_duration


def expected_open_time(timestamp: datetime, timeframe: Timeframe) -> datetime:
    """Return the UTC epoch-aligned candle-open boundary containing ``timestamp``.

    ``floor(timestamp_epoch / duration) * duration``, mirroring
    ``app.flow.windows.epoch_bucket_start``'s algorithm without importing it.
    """
    duration_seconds = timeframe_duration(timeframe).total_seconds()
    epoch_seconds = timestamp.timestamp()
    bucket_index = int(epoch_seconds // duration_seconds)
    return datetime.fromtimestamp(bucket_index * duration_seconds, tz=UTC)


def is_aligned(timestamp: datetime, timeframe: Timeframe) -> bool:
    """Whether ``timestamp`` sits exactly on its timeframe's UTC epoch boundary."""
    return timestamp == expected_open_time(timestamp, timeframe)


def candle_close_time(candle: OHLCVCandle, timeframe: Timeframe) -> datetime:
    """Return the boundary at which ``candle`` closes."""
    return candle.timestamp + timeframe_duration(timeframe)


def is_closed(candle: OHLCVCandle, timeframe: Timeframe, as_of: datetime) -> bool:
    """Whether ``candle`` has fully closed as of ``as_of``."""
    return candle_close_time(candle, timeframe) <= as_of


def split_closed_and_forming(
    candles: Sequence[OHLCVCandle], timeframe: Timeframe, as_of: datetime
) -> tuple[list[OHLCVCandle], OHLCVCandle | None]:
    """Split a chronologically sorted candle sequence into (closed, live).

    ``candles`` must already be sorted ascending by timestamp. Returns every
    CLOSED candle (in order) plus the single most recent candle as
    ``live_candle`` only if that last candle is not yet closed as of
    ``as_of`` - never included in the closed list, never used by any
    rolling calculation. If more than the trailing candle is not yet closed
    (a malformed/inconsistent ``as_of`` relative to the supplied series),
    every non-closed candle is simply excluded from ``closed`` and only the
    very last one is ever exposed as ``live_candle`` - nothing is fabricated
    for the others.
    """
    if not candles:
        return [], None

    closed = [c for c in candles if is_closed(c, timeframe, as_of)]
    last = candles[-1]
    live_candle = last if not is_closed(last, timeframe, as_of) else None
    return closed, live_candle


def contiguous_tail(candles: Sequence[OHLCVCandle], timeframe: Timeframe) -> list[OHLCVCandle]:
    """Return the maximal trailing run of ``candles`` with no missing interval.

    ``candles`` must already be sorted ascending by timestamp with no
    duplicates. Walking backward from the most recent candle, the run stops
    at the first pair whose gap is not exactly one timeframe duration - the
    candles before that pair are excluded from every rolling calculation
    rather than silently bridged or forward-filled.
    """
    if not candles:
        return []
    duration = timeframe_duration(timeframe)
    tail = [candles[-1]]
    for candle in reversed(candles[:-1]):
        if tail[0].timestamp - candle.timestamp == duration:
            tail.insert(0, candle)
        else:
            break
    return tail


__all__ = [
    "candle_close_time",
    "contiguous_tail",
    "expected_open_time",
    "is_aligned",
    "is_closed",
    "split_closed_and_forming",
]

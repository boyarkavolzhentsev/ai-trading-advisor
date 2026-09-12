"""Pure H1 -> H4 resampling into canonical UTC buckets.

Input contract: a chronologically ascending, already-normalized-to-UTC list
of CLOSED H1 ``OHLCVCandle``s only - the caller (``MT5OHLCVProvider``) is
responsible for excluding the current forming H1 candle first (reusing
``app.market_data.candle_time.split_closed_and_forming`` with the SAME
authoritative cycle ``as_of`` its caller uses, per the Stage A corrective
review's ``as_of``-determinism finding - never this module's own
computation, and never a wall-clock read). This module never reads the wall
clock and never receives an ``as_of`` at all.

Fail-closed, never synthesized: a UTC 4-hour bucket produces an H4 candle
only when it holds exactly its 4 expected, distinct H1 members (``bucket``,
``bucket+1h``, ``bucket+2h``, ``bucket+3h``). A short bucket (missing
member), an over-full bucket (a duplicate timestamp), or any other
non-contiguous membership produces NO candle for that bucket - never a
partial/forward-filled one.

Bucket boundaries reuse ``app.market_data.candle_time.expected_open_time``
directly rather than a local reimplementation: that function is a generic,
provider-agnostic candle-time primitive that now lives at this same
``app.market_data`` layer (Stage A corrective review, dependency-direction
finding) - sharing it here is a same-layer, same-package import, not an
upward dependency onto Technical, so there is no longer a reason to keep a
second, independently-maintained copy of the identical epoch-floor
arithmetic.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal

from app.core.enums.market import Timeframe
from app.core.models.candle import OHLCVCandle
from app.market_data.candle_time import expected_open_time

_H1_HOUR = timedelta(hours=1)


def resample_h4(closed_h1_candles: Sequence[OHLCVCandle]) -> list[OHLCVCandle]:
    """Aggregate CLOSED H1 candles into canonical UTC H4 candles.

    ``closed_h1_candles`` need not be pre-sorted or gap-free - candles are
    grouped by their computed bucket start regardless of input order, and
    each bucket is independently judged for completeness. Returns candles in
    ascending bucket order.
    """
    buckets: dict[datetime, list[OHLCVCandle]] = {}
    for candle in closed_h1_candles:
        bucket_start = expected_open_time(candle.timestamp, Timeframe.H4)
        buckets.setdefault(bucket_start, []).append(candle)

    result: list[OHLCVCandle] = []
    for bucket_start in sorted(buckets):
        members = buckets[bucket_start]
        ordered = _complete_ordered_members(bucket_start, members)
        if ordered is None:
            continue
        result.append(
            OHLCVCandle(
                timestamp=bucket_start,
                open=ordered[0].open,
                high=max(candle.high for candle in ordered),
                low=min(candle.low for candle in ordered),
                close=ordered[-1].close,
                volume=sum((candle.volume for candle in ordered), Decimal(0)),
            )
        )
    return result


def _complete_ordered_members(bucket_start: datetime, members: list[OHLCVCandle]) -> list[OHLCVCandle] | None:
    """Return ``members`` sorted ascending iff they are exactly the 4
    expected distinct H1 slots for ``bucket_start``; ``None`` otherwise (a
    missing member, a duplicate timestamp, or any stray timestamp outside
    the expected 4 slots)."""
    expected = {bucket_start + i * _H1_HOUR for i in range(4)}
    timestamps = [candle.timestamp for candle in members]
    if len(timestamps) != len(set(timestamps)):
        return None
    if set(timestamps) != expected:
        return None
    return sorted(members, key=lambda candle: candle.timestamp)


__all__ = ["resample_h4"]

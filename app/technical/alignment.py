"""Deterministic UTC epoch-aligned candle/timeframe helpers (Stage 3A).

``expected_open_time``/``is_aligned``/``candle_close_time``/``is_closed``/
``split_closed_and_forming`` are re-exported, unchanged, from
``app.market_data.candle_time`` (MT5 Price Authority Stage A corrective
review, dependency-direction finding): those five are genuinely generic
candle-time primitives with zero Technical-domain concept, relocated one
layer down so market-data ingestion code can depend on them without an
upward dependency onto this contour. Every existing call site here
(``from app.technical.alignment import ...``) is unaffected - same names,
same behavior, same module path.

``contiguous_tail`` stays here: it is Stage-3-specific rolling-window logic
(used directly by every Stage 3B analyst's own lookback trimming), not a
generic candle-time primitive, so it was not moved.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.core.enums.market import Timeframe
from app.core.models.candle import OHLCVCandle
from app.market_data.candle_time import (
    candle_close_time,
    expected_open_time,
    is_aligned,
    is_closed,
    split_closed_and_forming,
)
from app.market_data.timeframes import timeframe_duration


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

"""Wall-clock duration of each timeframe.

Provider-agnostic: used to decide whether the latest candle of a series is
stale. Provider-specific interval strings live in the provider packages.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from types import MappingProxyType
from typing import Final

from app.core.enums.market import Timeframe
from app.market_data.exceptions import UnsupportedTimeframeError

TIMEFRAME_DURATIONS: Final[Mapping[Timeframe, timedelta]] = MappingProxyType(
    {
        Timeframe.M1: timedelta(minutes=1),
        Timeframe.M5: timedelta(minutes=5),
        Timeframe.M15: timedelta(minutes=15),
        Timeframe.M30: timedelta(minutes=30),
        Timeframe.H1: timedelta(hours=1),
        Timeframe.H4: timedelta(hours=4),
        Timeframe.D1: timedelta(days=1),
        Timeframe.W1: timedelta(weeks=1),
    }
)
"""Nominal duration of one candle per timeframe."""


def timeframe_duration(timeframe: Timeframe) -> timedelta:
    """Return the nominal candle duration of ``timeframe``.

    Raises:
        UnsupportedTimeframeError: if the timeframe has no known duration.
    """
    try:
        return TIMEFRAME_DURATIONS[timeframe]
    except KeyError as exc:
        raise UnsupportedTimeframeError(f"no known duration for timeframe {timeframe}") from exc


__all__ = ["TIMEFRAME_DURATIONS", "timeframe_duration"]

"""MT5 server-wall-clock -> canonical UTC timestamp normalization.

The live MT5 Price Authority audit found raw MT5 ``time`` values behave
empirically as broker-server wall-clock digits encoded as epoch seconds -
NOT a genuine UTC epoch instant. ``datetime.fromtimestamp(raw, UTC)`` alone
is therefore not a conversion; it only extracts those wall-clock digits.
Turning them into a real UTC instant requires knowing the broker/server's
actual IANA timezone and handling DST correctly for arbitrary past/future
dates - exactly the job the shared, generalized
``app.core.time_normalization.resolve_unambiguous_utc`` already does (see
that module's own docstring for why it is shared rather than duplicated).

No fixed ``timedelta`` offset, no hardcoded UTC+3: the previously measured
~UTC+3 is a symptom of one broker's current DST state, never the policy.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.core.models.base import Timestamp
from app.core.time_normalization import resolve_unambiguous_utc


def normalize_mt5_server_timestamp(raw_epoch_seconds: int, server_timezone: str) -> Timestamp:
    """Convert one raw MT5 ``time`` value to canonical UTC.

    1. Interpret the raw epoch numerically as broker-local wall-clock
       digits: ``datetime.fromtimestamp(raw, UTC).replace(tzinfo=None)``
       extracts those digits without asserting any UTC offset.
    2. Resolve those naive digits under ``ZoneInfo(server_timezone)`` via
       the shared fold-aware primitive.

    Raises:
        ValueError: if the wall-clock digits do not exist (DST
            spring-forward gap) or are ambiguous (DST fall-back fold) under
            ``server_timezone`` - never silently resolved either way.
    """
    naive_wall_clock = datetime.fromtimestamp(raw_epoch_seconds, tz=UTC).replace(tzinfo=None)
    return resolve_unambiguous_utc(naive_wall_clock, ZoneInfo(server_timezone))


__all__ = ["normalize_mt5_server_timestamp"]

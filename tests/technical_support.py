"""Shared candle builders for Stage 3A technical tests.

Not a test module itself (no ``test_`` prefix): pytest will not collect it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.models.candle import OHLCVCandle

BASE = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)


def candle(
    *,
    index: int,
    close: str,
    high: str | None = None,
    low: str | None = None,
    open_: str | None = None,
    interval: timedelta = timedelta(minutes=1),
    base: datetime = BASE,
) -> OHLCVCandle:
    """Build one M1-aligned candle at ``base + index * interval``.

    Defaults ``high``/``low``/``open`` to a small symmetric wick around
    ``close`` when not supplied, so callers focused only on close-price
    behavior (trend/momentum/moving-average tests) need not specify OHLC
    geometry by hand.
    """
    close_d = Decimal(close)
    high_d = Decimal(high) if high is not None else close_d + Decimal("1")
    low_d = Decimal(low) if low is not None else close_d - Decimal("1")
    open_d = Decimal(open_) if open_ is not None else close_d
    return OHLCVCandle(
        timestamp=base + interval * index,
        open=open_d,
        high=high_d,
        low=low_d,
        close=close_d,
        volume=Decimal("1"),
    )


def candles_from_closes(closes: list[str], *, base: datetime = BASE, interval: timedelta = timedelta(minutes=1)) -> list[OHLCVCandle]:
    return [candle(index=i, close=c, base=base, interval=interval) for i, c in enumerate(closes)]


__all__ = ["BASE", "candle", "candles_from_closes"]

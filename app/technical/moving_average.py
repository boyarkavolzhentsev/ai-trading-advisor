"""Deterministic Stage 3A moving-average calculator: SMA, EMA, distance from
SMA, and MA slope. Numeric facts only - no crossover signal, no bullish/
bearish label.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.models.candle import OHLCVCandle
from app.core.models.moving_average_features import MovingAverageFeatures
from app.technical.alignment import contiguous_tail
from app.technical.quality import partial, unavailable, valid

DEFAULT_MA_PERIODS: tuple[int, ...] = (20, 50)
MA_SLOPE_WINDOW = 3


def simple_moving_average(closes: Sequence[Decimal], period: int) -> Decimal | None:
    """Arithmetic mean of the last ``period`` closes. ``None`` if unavailable."""
    if period < 1:
        raise ValueError("period must be >= 1")
    if len(closes) < period:
        return None
    return sum(closes[-period:], Decimal(0)) / period


def exponential_moving_average(closes: Sequence[Decimal], period: int) -> list[Decimal]:
    """EMA series seeded with ``SMA(period)`` on the first full period.

    ``[]`` if fewer than ``period`` closes are supplied. Element 0 of the
    result is the seed SMA; every subsequent element applies the standard
    ``alpha = 2 / (period + 1)`` recursion.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    if len(closes) < period:
        return []
    alpha = Decimal(2) / (period + 1)
    seed = sum(closes[:period], Decimal(0)) / period
    result = [seed]
    prev = seed
    for close in closes[period:]:
        prev = (close - prev) * alpha + prev
        result.append(prev)
    return result


def _ols_slope(values: Sequence[Decimal]) -> Decimal | None:
    n = len(values)
    if n < 2:
        return None
    mean_i = Decimal(n - 1) / 2
    mean_v = sum(values, Decimal(0)) / n
    numerator = sum((Decimal(i) - mean_i) * (v - mean_v) for i, v in enumerate(values))
    denominator = sum((Decimal(i) - mean_i) ** 2 for i in range(n))
    if denominator == 0:
        return None
    return numerator / denominator


def compute_moving_average_features(
    *,
    symbol: str,
    contract_type: ContractType,
    timeframe: Timeframe,
    candles: Sequence[OHLCVCandle],
    periods: Sequence[int] = DEFAULT_MA_PERIODS,
    source: str,
) -> MovingAverageFeatures:
    """Compute deterministic SMA/EMA facts over CLOSED, contiguous candles."""
    if not periods:
        raise ValueError("periods must not be empty")
    if any(p < 1 for p in periods):
        raise ValueError("every period must be >= 1")

    tail = contiguous_tail(candles, timeframe)
    closes = [c.close for c in tail]

    sma: dict[int, Decimal] = {}
    ema: dict[int, Decimal] = {}
    distance_from_sma_pct: dict[int, Decimal] = {}
    ma_slope: dict[int, Decimal] = {}

    for period in periods:
        sma_value = simple_moving_average(closes, period)
        if sma_value is not None:
            sma[period] = sma_value
            if sma_value > 0:
                distance_from_sma_pct[period] = (closes[-1] - sma_value) / sma_value * 100

        ema_series = exponential_moving_average(closes, period)
        if ema_series:
            ema[period] = ema_series[-1]
            slope = _ols_slope(ema_series[-MA_SLOPE_WINDOW:])
            if slope is not None:
                ma_slope[period] = slope

    if not tail:
        status = unavailable("no contiguous closed candles available")
    elif not sma:
        status = partial(
            f"only {len(tail)} contiguous closed candles available, smallest requested period is {min(periods)}",
            sample_count=len(tail),
        )
    elif len(sma) < len(periods):
        missing = sorted(set(periods) - set(sma))
        status = partial(f"insufficient history for period(s) {missing}", sample_count=len(tail))
    else:
        status = valid(len(tail))

    return MovingAverageFeatures(
        symbol=symbol,
        contract_type=contract_type,
        timeframe=timeframe,
        periods=tuple(periods),
        sma=sma,
        ema=ema,
        distance_from_sma_pct=distance_from_sma_pct,
        ma_slope=ma_slope,
        status=status,
        source=source,
    )


__all__ = [
    "DEFAULT_MA_PERIODS",
    "MA_SLOPE_WINDOW",
    "compute_moving_average_features",
    "exponential_moving_average",
    "simple_moving_average",
]

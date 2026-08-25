"""Deterministic Stage 3A volatility calculator: true range, Wilder ATR,
realized volatility, rolling range, range-expansion ratio.

True range at candle ``t`` requires the previous candle's close (``t-1``);
the first candle of any supplied series therefore never contributes a valid
TR - it is excluded from ATR's warm-up entirely rather than silently
treated as a full-context high-low range (``TR = high - low`` alone would
understate true range whenever a gap exists between candles).

ATR warm-up (Wilder): ``initial_atr`` is the arithmetic mean of the first
``atr_period`` true ranges - each of which already required valid
previous-close context, i.e. ``atr_period + 1`` contiguous closed candles
are needed before any ATR value exists. Every subsequent value applies the
Wilder recursion ``atr_t = ((atr_(t-1) * (period - 1)) + tr_t) / period``.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.models.candle import OHLCVCandle
from app.core.models.volatility_features import VolatilityFeatures
from app.technical.alignment import contiguous_tail
from app.technical.quality import partial, unavailable, valid

DEFAULT_ATR_PERIOD = 14
DEFAULT_VOLATILITY_LOOKBACK = 20


def true_ranges(candles: Sequence[OHLCVCandle]) -> list[Decimal]:
    """True range for every candle in ``candles`` that has a preceding candle.

    Returns one fewer element than ``candles`` - the first candle
    contributes no TR since it has no previous close. ``candles`` must
    already be contiguous.
    """
    result: list[Decimal] = []
    for prev, curr in zip(candles, candles[1:]):
        result.append(max(curr.high - curr.low, abs(curr.high - prev.close), abs(curr.low - prev.close)))
    return result


def wilder_atr(true_range_series: Sequence[Decimal], period: int) -> list[Decimal]:
    """Wilder-smoothed ATR series aligned to ``true_range_series[period - 1:]``.

    ``[]`` if fewer than ``period`` true ranges are supplied. The first
    element is the arithmetic mean of the first ``period`` true ranges;
    every subsequent element applies the Wilder recursion.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    if len(true_range_series) < period:
        return []
    initial = sum(true_range_series[:period], Decimal(0)) / period
    result = [initial]
    prev = initial
    for tr in true_range_series[period:]:
        prev = ((prev * (period - 1)) + tr) / period
        result.append(prev)
    return result


def compute_volatility_features(
    *,
    symbol: str,
    contract_type: ContractType,
    timeframe: Timeframe,
    candles: Sequence[OHLCVCandle],
    atr_period: int = DEFAULT_ATR_PERIOD,
    volatility_lookback: int = DEFAULT_VOLATILITY_LOOKBACK,
    source: str,
) -> VolatilityFeatures:
    """Compute deterministic volatility facts over CLOSED, contiguous candles."""
    if atr_period < 1:
        raise ValueError("atr_period must be >= 1")
    if volatility_lookback < 2:
        raise ValueError("volatility_lookback must be >= 2")

    tail = contiguous_tail(candles, timeframe)

    trs = true_ranges(tail)
    current_true_range = trs[-1] if trs else None

    atr_series = wilder_atr(trs, atr_period)
    current_atr = atr_series[-1] if atr_series else None

    range_expansion_ratio = None
    if current_true_range is not None and current_atr is not None and current_atr != 0:
        range_expansion_ratio = current_true_range / current_atr

    vol_tail = tail[-volatility_lookback:] if len(tail) >= volatility_lookback else tail
    realized_volatility = None
    if len(vol_tail) >= 2:
        returns = [
            (curr.close - prev.close) / prev.close
            for prev, curr in zip(vol_tail, vol_tail[1:])
            if prev.close > 0
        ]
        if len(returns) >= 2:
            mean_return = sum(returns, Decimal(0)) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
            realized_volatility = variance.sqrt() if variance >= 0 else None

    rolling_range = None
    if vol_tail:
        rolling_range = max(c.high for c in vol_tail) - min(c.low for c in vol_tail)

    if not tail:
        status = unavailable("no contiguous closed candles available")
    elif current_atr is None:
        status = partial(
            f"only {len(trs)} true range(s) available (from {len(tail)} contiguous closed candles), "
            f"need {atr_period} for ATR warm-up",
            sample_count=len(tail),
        )
    else:
        status = valid(len(tail))

    return VolatilityFeatures(
        symbol=symbol,
        contract_type=contract_type,
        timeframe=timeframe,
        atr_period=atr_period,
        volatility_lookback=volatility_lookback,
        true_range=current_true_range,
        atr=current_atr,
        realized_volatility=realized_volatility,
        rolling_range=rolling_range,
        range_expansion_ratio=range_expansion_ratio,
        status=status,
        source=source,
    )


__all__ = [
    "DEFAULT_ATR_PERIOD",
    "DEFAULT_VOLATILITY_LOOKBACK",
    "compute_volatility_features",
    "true_ranges",
    "wilder_atr",
]

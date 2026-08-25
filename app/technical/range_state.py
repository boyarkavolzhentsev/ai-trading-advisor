"""Deterministic Stage 3A range/consolidation calculator: normalized_range
and directional_efficiency. Calibration-free numeric facts only - no
CONSOLIDATING/RANGING/TRENDING classification, no arbitrary threshold.

``normalized_range = rolling_range / ATR`` - ``None`` whenever ATR is
unavailable or exactly zero (never a fabricated zero/infinity).
``directional_efficiency = |close_t - close_(t-n)| / sum(|close_i -
close_(i-1)|)`` over the same window - ``None`` whenever the window's gross
path length is exactly zero (a perfectly flat window: both numerator and
denominator are zero, so the ratio is genuinely undefined).
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.models.candle import OHLCVCandle
from app.core.models.range_state_features import RangeStateFeatures
from app.technical.alignment import contiguous_tail
from app.technical.quality import partial, unavailable, valid
from app.technical.volatility import DEFAULT_ATR_PERIOD, true_ranges, wilder_atr

DEFAULT_RANGE_STATE_LOOKBACK = 20


def compute_range_state_features(
    *,
    symbol: str,
    contract_type: ContractType,
    timeframe: Timeframe,
    candles: Sequence[OHLCVCandle],
    lookback: int = DEFAULT_RANGE_STATE_LOOKBACK,
    atr_period: int = DEFAULT_ATR_PERIOD,
    source: str,
) -> RangeStateFeatures:
    """Compute deterministic, calibration-free range facts over CLOSED candles."""
    if lookback < 2:
        raise ValueError("lookback must be >= 2")
    if atr_period < 1:
        raise ValueError("atr_period must be >= 1")

    tail = contiguous_tail(candles, timeframe)
    window = tail[-lookback:] if len(tail) >= lookback else tail

    rolling_range = None
    if window:
        rolling_range = max(c.high for c in window) - min(c.low for c in window)

    trs = true_ranges(tail)
    atr_series = wilder_atr(trs, atr_period)
    current_atr = atr_series[-1] if atr_series else None

    normalized_range = None
    if rolling_range is not None and current_atr is not None and current_atr != 0:
        normalized_range = rolling_range / current_atr

    directional_efficiency = None
    if len(window) >= 2:
        net_change = abs(window[-1].close - window[0].close)
        gross_change = sum(abs(curr.close - prev.close) for prev, curr in zip(window, window[1:]))
        directional_efficiency = net_change / gross_change if gross_change > 0 else None

    if not tail:
        status = unavailable("no contiguous closed candles available")
    elif len(window) < lookback:
        status = partial(
            f"only {len(window)} contiguous closed candles available, need {lookback}",
            sample_count=len(window),
        )
    elif current_atr is None:
        status = partial(
            f"ATR not yet warmed up (need {atr_period} true ranges); normalized_range unavailable",
            sample_count=len(window),
        )
    else:
        status = valid(len(window))

    return RangeStateFeatures(
        symbol=symbol,
        contract_type=contract_type,
        timeframe=timeframe,
        lookback=lookback,
        atr_period=atr_period,
        rolling_range=rolling_range,
        normalized_range=normalized_range,
        directional_efficiency=directional_efficiency,
        status=status,
        source=source,
    )


__all__ = ["DEFAULT_RANGE_STATE_LOOKBACK", "compute_range_state_features"]

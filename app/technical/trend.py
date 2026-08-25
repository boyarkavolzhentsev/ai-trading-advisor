"""Deterministic Stage 3A trend-feature calculator.

Pure numeric facts only - return, OLS close-price slope, higher-high/
higher-low/lower-high/lower-low counts and directional persistence - never
a trend-state label. Computed over the maximal contiguous trailing run of
supplied CLOSED candles (see ``app.technical.alignment.contiguous_tail``); a
gap or insufficient history degrades quality rather than fabricating a
value.

``return_pct``/``slope`` require exactly ``lookback + 1`` contiguous closed
candles (``lookback`` closed intervals); with fewer than that but at least 2
candles, the higher-high/lower-low counts and slope are still computed over
whatever is available and the block is reported ``PARTIAL``.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.models.candle import OHLCVCandle
from app.core.models.trend_features import TrendFeatures
from app.technical.alignment import contiguous_tail
from app.technical.quality import partial, unavailable, valid

DEFAULT_TREND_LOOKBACK = 20


def _ols_slope(closes: Sequence[Decimal]) -> Decimal | None:
    """OLS slope of ``closes`` against their integer index (0, 1, 2, ...).

    Candle index is used rather than timestamp since contiguous candles are
    equally spaced by construction. ``None`` if fewer than 2 points.
    """
    n = len(closes)
    if n < 2:
        return None
    mean_i = Decimal(n - 1) / 2
    mean_c = sum(closes, Decimal(0)) / n
    numerator = sum((Decimal(i) - mean_i) * (c - mean_c) for i, c in enumerate(closes))
    denominator = sum((Decimal(i) - mean_i) ** 2 for i in range(n))
    if denominator == 0:
        return None
    return numerator / denominator


def compute_trend_features(
    *,
    symbol: str,
    contract_type: ContractType,
    timeframe: Timeframe,
    candles: Sequence[OHLCVCandle],
    lookback: int = DEFAULT_TREND_LOOKBACK,
    source: str,
) -> TrendFeatures:
    """Compute deterministic trend facts over up to ``lookback`` closed candles."""
    if lookback < 2:
        raise ValueError("lookback must be >= 2")

    tail = contiguous_tail(candles, timeframe)
    required = lookback + 1
    used = tail[-required:] if len(tail) >= required else tail
    count = len(used)

    if count < 2:
        status = unavailable(
            f"only {count} contiguous closed candle(s) available, need at least 2", sample_count=count
        )
        return TrendFeatures(
            symbol=symbol, contract_type=contract_type, timeframe=timeframe, lookback=lookback,
            status=status, source=source,
        )

    closes = [c.close for c in used]

    return_pct = None
    if count >= required and closes[0] > 0:
        return_pct = (closes[-1] - closes[0]) / closes[0] * 100

    slope = _ols_slope(closes)

    higher_high = higher_low = lower_high = lower_low = 0
    for prev, curr in zip(used, used[1:]):
        if curr.high > prev.high:
            higher_high += 1
        elif curr.high < prev.high:
            lower_high += 1
        if curr.low > prev.low:
            higher_low += 1
        elif curr.low < prev.low:
            lower_low += 1

    directional_persistence = None
    if return_pct is not None and return_pct != 0:
        overall_sign = 1 if return_pct > 0 else -1
        same_sign = 0
        pair_count = 0
        for prev, curr in zip(used, used[1:]):
            diff = curr.close - prev.close
            if diff == 0:
                continue
            pair_count += 1
            if (1 if diff > 0 else -1) == overall_sign:
                same_sign += 1
        directional_persistence = Decimal(same_sign) / pair_count if pair_count > 0 else None

    if count < required:
        status = partial(
            f"only {count} contiguous closed candles available, need {required} for lookback={lookback}",
            sample_count=count,
        )
    else:
        status = valid(count)

    return TrendFeatures(
        symbol=symbol,
        contract_type=contract_type,
        timeframe=timeframe,
        lookback=lookback,
        return_pct=return_pct,
        slope=slope,
        higher_high_count=higher_high,
        higher_low_count=higher_low,
        lower_high_count=lower_high,
        lower_low_count=lower_low,
        directional_persistence=directional_persistence,
        status=status,
        source=source,
    )


__all__ = ["DEFAULT_TREND_LOOKBACK", "compute_trend_features"]

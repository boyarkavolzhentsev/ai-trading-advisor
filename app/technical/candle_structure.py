"""Deterministic Stage 3A candle-geometry calculator for the single most
recent CLOSED candle. Pure geometric facts only - no named candlestick
patterns, no reversal/continuation interpretation. No contiguity/lookback
requirement: geometry of one candle needs no predecessor.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.models.candle import OHLCVCandle
from app.core.models.candle_structure_features import CandleStructureFeatures
from app.technical.quality import unavailable, valid


def compute_candle_structure_features(
    *,
    symbol: str,
    contract_type: ContractType,
    timeframe: Timeframe,
    candles: Sequence[OHLCVCandle],
    source: str,
) -> CandleStructureFeatures:
    """Compute geometric facts of the most recent CLOSED candle in ``candles``.

    ``candles`` is expected to already be CLOSED-only and sorted ascending;
    only the last element is used.
    """
    if not candles:
        return CandleStructureFeatures(
            symbol=symbol,
            contract_type=contract_type,
            timeframe=timeframe,
            status=unavailable("no closed candles available"),
            source=source,
        )

    candle = candles[-1]
    body_size = abs(candle.close - candle.open)
    upper_wick = candle.high - max(candle.open, candle.close)
    lower_wick = min(candle.open, candle.close) - candle.low
    range_size = candle.high - candle.low
    body_to_range_ratio = body_size / range_size if range_size > 0 else None
    close_location_value = (candle.close - candle.low) / range_size if range_size > 0 else None

    return CandleStructureFeatures(
        symbol=symbol,
        contract_type=contract_type,
        timeframe=timeframe,
        candle_time=candle.timestamp,
        body_size=body_size,
        upper_wick=upper_wick,
        lower_wick=lower_wick,
        range_size=range_size,
        body_to_range_ratio=body_to_range_ratio,
        close_location_value=close_location_value,
        status=valid(1),
        source=source,
    )


__all__ = ["compute_candle_structure_features"]

"""Tests for app.technical.range_state: normalized_range and directional_efficiency."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.enums.quality import FeatureQuality
from app.technical.range_state import compute_range_state_features
from app.technical.volatility import true_ranges, wilder_atr
from tests.technical_support import candle, candles_from_closes


def _compute(candles, *, lookback: int, atr_period: int):
    return compute_range_state_features(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1,
        candles=candles, lookback=lookback, atr_period=atr_period, source="test",
    )


def test_normalized_range_exact() -> None:
    candles = [
        candle(index=0, close="100", high="101", low="99"),
        candle(index=1, close="102", high="105", low="98"),
        candle(index=2, close="103", high="104", low="101"),
        candle(index=3, close="105", high="106", low="100"),
    ]
    result = _compute(candles, lookback=4, atr_period=3)
    trs = true_ranges(candles)
    atr = wilder_atr(trs, 3)[-1]
    rolling_range = max(c.high for c in candles) - min(c.low for c in candles)
    assert result.rolling_range == rolling_range
    assert result.normalized_range == rolling_range / atr


def test_directional_efficiency_exact() -> None:
    candles = candles_from_closes(["100", "102", "101", "105"])
    result = _compute(candles, lookback=4, atr_period=1)
    net = abs(Decimal("105") - Decimal("100"))
    gross = abs(Decimal("102") - Decimal("100")) + abs(Decimal("101") - Decimal("102")) + abs(Decimal("105") - Decimal("101"))
    assert result.directional_efficiency == net / gross


def test_zero_denominator_directional_efficiency_is_none() -> None:
    candles = candles_from_closes(["100", "100", "100"])
    result = _compute(candles, lookback=3, atr_period=1)
    assert result.directional_efficiency is None


def test_insufficient_history_is_partial() -> None:
    candles = candles_from_closes(["100", "102"])
    result = _compute(candles, lookback=5, atr_period=1)
    assert result.status.quality is FeatureQuality.PARTIAL
    assert result.directional_efficiency is not None  # still computed over what's available


def test_no_candles_is_unavailable() -> None:
    result = _compute([], lookback=5, atr_period=3)
    assert result.status.quality is FeatureQuality.UNAVAILABLE
    assert result.normalized_range is None
    assert result.directional_efficiency is None

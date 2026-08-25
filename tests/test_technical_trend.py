"""Tests for app.technical.trend.compute_trend_features."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.enums.quality import FeatureQuality
from app.technical.trend import compute_trend_features
from tests.technical_support import candle, candles_from_closes


def _compute(closes: list[str], lookback: int):
    candles = candles_from_closes(closes)
    return compute_trend_features(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1,
        candles=candles, lookback=lookback, source="test",
    )


def test_exact_return_and_slope_arithmetic() -> None:
    result = _compute(["100", "102", "104"], lookback=2)
    assert result.status.quality is FeatureQuality.VALID
    assert result.return_pct == Decimal("4")
    assert result.slope == Decimal("2")


def test_higher_high_higher_low_lower_high_lower_low_counts() -> None:
    candles = [
        candle(index=0, close="100", high="100", low="95"),
        candle(index=1, close="102", high="102", low="97"),
        candle(index=2, close="104", high="104", low="99"),
    ]
    result = compute_trend_features(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1,
        candles=candles, lookback=2, source="test",
    )
    assert result.higher_high_count == 2
    assert result.lower_high_count == 0
    assert result.higher_low_count == 2
    assert result.lower_low_count == 0


def test_directional_persistence_partial_agreement() -> None:
    result = _compute(["100", "105", "103", "110"], lookback=3)
    assert result.return_pct == Decimal("10")
    assert result.directional_persistence == Decimal("2") / Decimal("3")


def test_zero_return_yields_zero_not_unavailable_and_no_persistence() -> None:
    result = _compute(["100", "100", "100"], lookback=2)
    assert result.status.quality is FeatureQuality.VALID
    assert result.return_pct == Decimal("0")
    assert result.slope == Decimal("0")
    assert result.directional_persistence is None


def test_insufficient_history_single_candle_is_unavailable() -> None:
    result = _compute(["100"], lookback=5)
    assert result.status.quality is FeatureQuality.UNAVAILABLE
    assert result.return_pct is None
    assert result.slope is None


def test_insufficient_history_no_candles_is_unavailable() -> None:
    result = _compute([], lookback=5)
    assert result.status.quality is FeatureQuality.UNAVAILABLE
    assert result.status.sample_count == 0


def test_partial_when_fewer_than_lookback_plus_one_but_at_least_two() -> None:
    result = _compute(["100", "102"], lookback=5)
    assert result.status.quality is FeatureQuality.PARTIAL
    assert result.return_pct is None  # full lookback not available
    assert result.slope is not None  # still computed over what's available

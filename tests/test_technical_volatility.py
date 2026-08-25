"""Tests for app.technical.volatility: true range, Wilder ATR, realized
volatility, rolling range, range-expansion ratio."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.enums.quality import FeatureQuality
from app.technical.volatility import compute_volatility_features, true_ranges, wilder_atr
from tests.technical_support import candle


def test_exact_true_range() -> None:
    candles = [
        candle(index=0, close="100", high="100", low="100"),
        candle(index=1, close="102", high="105", low="98"),
    ]
    trs = true_ranges(candles)
    assert trs == [Decimal("7")]  # max(105-98, |105-100|, |98-100|) = max(7, 5, 2)


def test_wilder_atr_initial_is_mean_of_first_period_true_ranges() -> None:
    trs = [Decimal("7"), Decimal("3"), Decimal("6")]
    result = wilder_atr(trs, period=3)
    expected_initial = (Decimal("7") + Decimal("3") + Decimal("6")) / 3
    assert result == [expected_initial]


def test_wilder_atr_recursive_step() -> None:
    trs = [Decimal("7"), Decimal("3"), Decimal("6"), Decimal("4")]
    result = wilder_atr(trs, period=3)
    initial = (Decimal("7") + Decimal("3") + Decimal("6")) / 3
    expected_second = ((initial * 2) + Decimal("4")) / 3
    assert result == [initial, expected_second]


def test_wilder_atr_insufficient_true_ranges_returns_empty() -> None:
    assert wilder_atr([Decimal("7"), Decimal("3")], period=3) == []


def test_wilder_atr_rejects_nonpositive_period() -> None:
    with pytest.raises(ValueError):
        wilder_atr([], period=0)


def _candles_for_atr(closes_and_highs_lows: list[tuple[str, str, str]]):
    return [
        candle(index=i, close=c, high=h, low=low)
        for i, (c, h, low) in enumerate(closes_and_highs_lows)
    ]


def test_compute_volatility_features_full_warmup() -> None:
    # 4 candles -> 3 true ranges -> exactly enough for atr_period=3.
    candles = _candles_for_atr(
        [("100", "100", "100"), ("102", "105", "98"), ("103", "104", "101"), ("105", "106", "100")]
    )
    result = compute_volatility_features(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1,
        candles=candles, atr_period=3, volatility_lookback=4, source="test",
    )
    assert result.status.quality is FeatureQuality.VALID
    trs = true_ranges(candles)
    assert result.true_range == trs[-1]
    assert result.atr == wilder_atr(trs, 3)[-1]


def test_insufficient_atr_warmup_is_partial() -> None:
    candles = _candles_for_atr([("100", "100", "100"), ("102", "105", "98"), ("103", "104", "101")])
    result = compute_volatility_features(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1,
        candles=candles, atr_period=3, volatility_lookback=4, source="test",
    )
    assert result.status.quality is FeatureQuality.PARTIAL
    assert result.atr is None
    assert any("warm-up" in reason for reason in result.status.reasons)


def test_zero_atr_range_expansion_ratio_is_none_not_infinity() -> None:
    flat = [candle(index=i, close="100", high="100", low="100") for i in range(5)]
    result = compute_volatility_features(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1,
        candles=flat, atr_period=3, volatility_lookback=5, source="test",
    )
    assert result.atr == Decimal("0")
    assert result.true_range == Decimal("0")
    assert result.range_expansion_ratio is None


def test_realized_volatility_exact() -> None:
    candles = [candle(index=i, close=c) for i, c in enumerate(["100", "110", "99"])]
    result = compute_volatility_features(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1,
        candles=candles, atr_period=1, volatility_lookback=3, source="test",
    )
    r1 = (Decimal("110") - Decimal("100")) / Decimal("100")
    r2 = (Decimal("99") - Decimal("110")) / Decimal("110")
    mean_r = (r1 + r2) / 2
    variance = ((r1 - mean_r) ** 2 + (r2 - mean_r) ** 2) / 1
    assert result.realized_volatility == variance.sqrt()


def test_rolling_range_exact() -> None:
    candles = [
        candle(index=0, close="100", high="102", low="99"),
        candle(index=1, close="101", high="106", low="95"),
        candle(index=2, close="103", high="104", low="100"),
    ]
    result = compute_volatility_features(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1,
        candles=candles, atr_period=1, volatility_lookback=3, source="test",
    )
    assert result.rolling_range == Decimal("106") - Decimal("95")


def test_range_expansion_ratio_exact() -> None:
    candles = _candles_for_atr(
        [("100", "100", "100"), ("102", "105", "98"), ("103", "104", "101"), ("105", "106", "100")]
    )
    result = compute_volatility_features(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1,
        candles=candles, atr_period=3, volatility_lookback=4, source="test",
    )
    assert result.range_expansion_ratio == result.true_range / result.atr


def test_no_contiguous_candles_is_unavailable() -> None:
    result = compute_volatility_features(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1,
        candles=[], atr_period=3, volatility_lookback=4, source="test",
    )
    assert result.status.quality is FeatureQuality.UNAVAILABLE
    assert result.true_range is None
    assert result.atr is None

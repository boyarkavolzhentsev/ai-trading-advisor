"""Tests for app.technical.moving_average: SMA, EMA, distance-from-SMA, MA slope."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.enums.quality import FeatureQuality
from app.technical.moving_average import (
    compute_moving_average_features,
    exponential_moving_average,
    simple_moving_average,
)
from tests.technical_support import candles_from_closes


def test_exact_sma() -> None:
    closes = [Decimal("100"), Decimal("102"), Decimal("104")]
    assert simple_moving_average(closes, 3) == Decimal("102")


def test_sma_insufficient_history_is_none() -> None:
    closes = [Decimal("100"), Decimal("102")]
    assert simple_moving_average(closes, 3) is None


def test_exact_seeded_ema() -> None:
    closes = [Decimal("100"), Decimal("102"), Decimal("104"), Decimal("108")]
    series = exponential_moving_average(closes, 3)
    seed = (Decimal("100") + Decimal("102") + Decimal("104")) / 3  # 102
    step1 = (Decimal("108") - seed) * (Decimal(2) / 4) + seed  # alpha=0.5 -> 105
    assert series == [seed, step1]
    assert step1 == Decimal("105")


def test_recursive_ema() -> None:
    closes = [Decimal("100"), Decimal("102"), Decimal("104"), Decimal("108"), Decimal("110")]
    series = exponential_moving_average(closes, 3)
    assert len(series) == 3
    assert series[0] == Decimal("102")
    assert series[1] == Decimal("105")
    assert series[2] == Decimal("107.5")


def test_ema_insufficient_history_is_empty_list() -> None:
    assert exponential_moving_average([Decimal("100"), Decimal("102")], 3) == []


def _compute(closes: list[str], periods: tuple[int, ...]):
    candles = candles_from_closes(closes)
    return compute_moving_average_features(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1,
        candles=candles, periods=periods, source="test",
    )


def test_distance_from_sma_pct() -> None:
    result = _compute(["100", "102", "104"], periods=(3,))
    sma = Decimal("102")
    expected = (Decimal("104") - sma) / sma * 100
    assert result.sma[3] == sma
    assert result.distance_from_sma_pct[3] == expected


def test_ma_slope_exact() -> None:
    result = _compute(["100", "102", "104", "108", "110"], periods=(3,))
    # 3-point OLS slope over the trailing EMA window simplifies to (last - first) / 2.
    ema_series = exponential_moving_average([Decimal(c) for c in ["100", "102", "104", "108", "110"]], 3)
    expected_slope = (ema_series[-1] - ema_series[0]) / 2
    assert result.ma_slope[3] == expected_slope
    assert expected_slope == Decimal("2.75")


def test_insufficient_period_reports_partial_and_omits_that_period() -> None:
    result = _compute(["100", "102", "104"], periods=(3, 5))
    assert 3 in result.sma
    assert 5 not in result.sma
    assert result.status.quality is FeatureQuality.PARTIAL


def test_no_candles_is_unavailable() -> None:
    result = _compute([], periods=(3,))
    assert result.status.quality is FeatureQuality.UNAVAILABLE
    assert result.sma == {}
    assert result.ema == {}


def test_full_valid_status_when_all_periods_available() -> None:
    result = _compute(["100", "102", "104", "106"], periods=(2, 3))
    assert result.status.quality is FeatureQuality.VALID
    assert set(result.sma) == {2, 3}

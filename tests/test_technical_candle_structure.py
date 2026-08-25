"""Tests for app.technical.candle_structure: single-closed-candle geometry."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.enums.quality import FeatureQuality
from app.technical.candle_structure import compute_candle_structure_features
from tests.technical_support import candle


def _compute(candles):
    return compute_candle_structure_features(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1,
        candles=candles, source="test",
    )


def test_body_upper_lower_wick_and_range() -> None:
    c = candle(index=0, close="103", open_="101", high="105", low="99")
    result = _compute([c])
    assert result.body_size == Decimal("2")  # |103 - 101|
    assert result.upper_wick == Decimal("2")  # 105 - max(101, 103)
    assert result.lower_wick == Decimal("2")  # min(101, 103) - 99
    assert result.range_size == Decimal("6")  # 105 - 99


def test_body_to_range_ratio_and_close_location_value() -> None:
    c = candle(index=0, close="103", open_="101", high="105", low="99")
    result = _compute([c])
    assert result.body_to_range_ratio == Decimal("2") / Decimal("6")
    assert result.close_location_value == (Decimal("103") - Decimal("99")) / Decimal("6")


def test_zero_range_candle() -> None:
    c = candle(index=0, close="100", open_="100", high="100", low="100")
    result = _compute([c])
    assert result.body_size == Decimal("0")
    assert result.upper_wick == Decimal("0")
    assert result.lower_wick == Decimal("0")
    assert result.range_size == Decimal("0")
    assert result.body_to_range_ratio is None
    assert result.close_location_value is None
    assert result.status.quality is FeatureQuality.VALID  # zero geometry is a real fact


def test_uses_most_recent_closed_candle() -> None:
    first = candle(index=0, close="100", open_="100", high="101", low="99")
    second = candle(index=1, close="110", open_="108", high="112", low="107")
    result = _compute([first, second])
    assert result.candle_time == second.timestamp
    assert result.body_size == Decimal("2")  # |110 - 108|


def test_no_closed_candles_is_unavailable() -> None:
    result = _compute([])
    assert result.status.quality is FeatureQuality.UNAVAILABLE
    assert result.candle_time is None
    assert result.body_size is None

"""Serialization/round-trip tests for TechnicalFeatureSnapshot and friends."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.models.technical_feature_snapshot import TechnicalFeatureSnapshot
from app.technical.engine import TechnicalFeatureEngine
from tests.technical_support import candle, candles_from_closes


def _rich_snapshot() -> TechnicalFeatureSnapshot:
    """Build a snapshot with a confirmed swing and a structural break."""
    engine = TechnicalFeatureEngine(left_bars=2, right_bars=2, trend_lookback=3, ma_periods=(3,), atr_period=2, rsi_period=2, roc_period=2, volatility_lookback=3, range_state_lookback=3)
    highs = ["100", "101", "105", "102", "101"]
    series = [candle(index=i, close=str(Decimal(h) - 1), high=h, low="90") for i, h in enumerate(highs)]
    breaking = candle(index=5, close="105.5", high="106", low="104", open_="105")
    candles = [*series, breaking]
    engine.record_candles("BTCUSDT", ContractType.PERPETUAL, Timeframe.M1, candles)
    return engine.build_snapshot(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1,
        as_of=candles[-1].timestamp + timedelta(minutes=1), source="test",
    )


def test_snapshot_has_a_confirmed_swing_and_break_for_this_fixture() -> None:
    snapshot = _rich_snapshot()
    assert len(snapshot.market_structure.swings) == 1
    assert len(snapshot.market_structure.breaks) == 1


def test_python_round_trip_preserves_decimal_and_structure() -> None:
    snapshot = _rich_snapshot()
    round_tripped = TechnicalFeatureSnapshot.model_validate(snapshot.model_dump())
    assert round_tripped == snapshot
    assert isinstance(round_tripped.volatility.atr, Decimal)


def test_json_round_trip_preserves_decimal_and_structure() -> None:
    snapshot = _rich_snapshot()
    round_tripped = TechnicalFeatureSnapshot.model_validate_json(snapshot.model_dump_json())
    assert round_tripped == snapshot
    assert round_tripped.volatility.atr == snapshot.volatility.atr
    assert isinstance(round_tripped.volatility.atr, Decimal)


def test_swing_point_confirmed_at_preserved_through_round_trip() -> None:
    snapshot = _rich_snapshot()
    swing = snapshot.market_structure.swings[0]
    round_tripped = TechnicalFeatureSnapshot.model_validate_json(snapshot.model_dump_json())
    round_tripped_swing = round_tripped.market_structure.swings[0]
    assert round_tripped_swing.confirmed_at == swing.confirmed_at
    assert round_tripped_swing.candle_time == swing.candle_time


def test_structural_break_broken_swing_reference_preserved() -> None:
    snapshot = _rich_snapshot()
    brk = snapshot.market_structure.breaks[0]
    round_tripped = TechnicalFeatureSnapshot.model_validate_json(snapshot.model_dump_json())
    round_tripped_break = round_tripped.market_structure.breaks[0]
    assert round_tripped_break.broken_swing == brk.broken_swing


def test_quality_status_preserved_through_round_trip() -> None:
    snapshot = _rich_snapshot()
    round_tripped = TechnicalFeatureSnapshot.model_validate_json(snapshot.model_dump_json())
    assert round_tripped.status.quality == snapshot.status.quality
    assert round_tripped.trend.status == snapshot.trend.status


def test_swing_point_rejects_confirmed_at_not_after_candle_time() -> None:
    from app.core.enums.technical import SwingKind
    from app.core.models.market_structure_features import SwingPoint

    ts = candles_from_closes(["100"])[0].timestamp
    with pytest.raises(ValueError):
        SwingPoint(kind=SwingKind.HIGH, candle_time=ts, price=Decimal("100"), confirmed_at=ts, left_bars=2, right_bars=2)


def test_live_candle_must_be_after_last_closed_candle_time() -> None:
    snapshot = _rich_snapshot()
    # index 5 matches the last closed candle's own timestamp - equal, not
    # strictly after, so this must be rejected rather than silently accepted.
    same_time_candle = candle(index=5, close="999")
    data = snapshot.model_dump()
    data["live_candle"] = same_time_candle.model_dump()
    with pytest.raises(ValueError):
        TechnicalFeatureSnapshot.model_validate(data)

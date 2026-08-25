"""Tests for app.technical.engine.TechnicalFeatureEngine: composition, isolation, ingestion."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.enums.quality import FeatureQuality
from app.technical.engine import TechnicalFeatureEngine
from app.technical.errors import DuplicateCandleTimestampError, MisalignedCandleError
from app.technical.market_structure import DEFAULT_LEFT_BARS, DEFAULT_RIGHT_BARS
from app.technical.moving_average import DEFAULT_MA_PERIODS
from app.technical.trend import DEFAULT_TREND_LOOKBACK
from app.technical.volatility import DEFAULT_ATR_PERIOD
from tests.technical_support import BASE, candle, candles_from_closes

REQUIRED = max(DEFAULT_TREND_LOOKBACK, DEFAULT_ATR_PERIOD, max(DEFAULT_MA_PERIODS), DEFAULT_LEFT_BARS + DEFAULT_RIGHT_BARS) + 5


def _fully_warmed_engine() -> tuple[TechnicalFeatureEngine, list]:
    engine = TechnicalFeatureEngine()
    closes = [str(100 + i) for i in range(REQUIRED)]
    candles = candles_from_closes(closes)
    engine.record_candles("BTCUSDT", ContractType.PERPETUAL, Timeframe.M1, candles)
    return engine, candles


def test_multi_symbol_state_isolation_no_leakage() -> None:
    engine = TechnicalFeatureEngine()
    engine.record_candle("BTCUSDT", ContractType.PERPETUAL, Timeframe.M1, candle(index=0, close="100"))
    engine.record_candle("ETHUSDT", ContractType.PERPETUAL, Timeframe.M1, candle(index=0, close="3000"))

    assert len(engine.history_for("BTCUSDT", ContractType.PERPETUAL, Timeframe.M1).candles) == 1
    assert len(engine.history_for("ETHUSDT", ContractType.PERPETUAL, Timeframe.M1).candles) == 1
    btc = engine.history_for("BTCUSDT", ContractType.PERPETUAL, Timeframe.M1).candles.latest()[0]
    assert btc.close == Decimal("100")


def test_spot_and_perpetual_isolated_for_same_symbol() -> None:
    engine = TechnicalFeatureEngine()
    engine.record_candle("BTCUSDT", ContractType.PERPETUAL, Timeframe.M1, candle(index=0, close="100"))
    engine.record_candle("BTCUSDT", ContractType.SPOT, Timeframe.M1, candle(index=0, close="99"))

    perp = engine.history_for("BTCUSDT", ContractType.PERPETUAL, Timeframe.M1).candles.latest()[0]
    spot = engine.history_for("BTCUSDT", ContractType.SPOT, Timeframe.M1).candles.latest()[0]
    assert perp.close == Decimal("100")
    assert spot.close == Decimal("99")


def test_timeframe_isolated_for_same_symbol_and_contract_type() -> None:
    engine = TechnicalFeatureEngine()
    engine.record_candle("BTCUSDT", ContractType.PERPETUAL, Timeframe.M1, candle(index=0, close="100"))
    engine.record_candle(
        "BTCUSDT", ContractType.PERPETUAL, Timeframe.M5,
        candle(index=0, close="105", interval=timedelta(minutes=5)),
    )
    m1 = engine.history_for("BTCUSDT", ContractType.PERPETUAL, Timeframe.M1).candles.latest()[0]
    m5 = engine.history_for("BTCUSDT", ContractType.PERPETUAL, Timeframe.M5).candles.latest()[0]
    assert m1.close == Decimal("100")
    assert m5.close == Decimal("105")


def test_duplicate_candle_timestamp_rejected() -> None:
    engine = TechnicalFeatureEngine()
    engine.record_candle("BTCUSDT", ContractType.PERPETUAL, Timeframe.M1, candle(index=0, close="100"))
    with pytest.raises(DuplicateCandleTimestampError):
        engine.record_candle("BTCUSDT", ContractType.PERPETUAL, Timeframe.M1, candle(index=0, close="101"))


def test_misaligned_candle_rejected() -> None:
    engine = TechnicalFeatureEngine()
    misaligned = candle(index=0, close="100", base=BASE + timedelta(seconds=17))
    with pytest.raises(MisalignedCandleError):
        engine.record_candle("BTCUSDT", ContractType.PERPETUAL, Timeframe.M1, misaligned)


def test_out_of_order_insertion_normalized_before_use() -> None:
    engine = TechnicalFeatureEngine()
    candles = candles_from_closes(["100", "101", "102"])
    for c in [candles[2], candles[0], candles[1]]:  # deliberately out of order
        engine.record_candle("BTCUSDT", ContractType.PERPETUAL, Timeframe.M1, c)

    snapshot = engine.build_snapshot(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1,
        as_of=candles[-1].timestamp + timedelta(minutes=1), source="test",
    )
    assert snapshot.last_closed_candle_time == candles[-1].timestamp
    assert snapshot.candle_structure.candle_time == candles[-1].timestamp


def test_missing_candle_gap_detected_and_degrades_quality() -> None:
    engine = TechnicalFeatureEngine()
    engine.record_candles("BTCUSDT", ContractType.PERPETUAL, Timeframe.M1, candles_from_closes(["100", "101"]))
    # Deliberate 5-minute gap before the next candle.
    gapped = candle(index=10, close="105")
    engine.record_candle("BTCUSDT", ContractType.PERPETUAL, Timeframe.M1, gapped)

    snapshot = engine.build_snapshot(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1,
        as_of=gapped.timestamp + timedelta(minutes=1), source="test",
    )
    # Only the single post-gap candle is contiguous with itself - trend needs >= 2.
    assert snapshot.trend.status.quality is FeatureQuality.UNAVAILABLE
    assert any("contiguous" in reason for reason in snapshot.trend.status.reasons)


def test_forming_candle_excluded_from_snapshot_rolling_features() -> None:
    engine, candles = _fully_warmed_engine()
    as_of_all_closed = candles[-1].timestamp + timedelta(minutes=1)
    closed_snapshot = engine.build_snapshot(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1,
        as_of=as_of_all_closed, source="test",
    )

    forming = candle(index=REQUIRED, close="9999")  # wildly different value
    engine.record_candle("BTCUSDT", ContractType.PERPETUAL, Timeframe.M1, forming)
    as_of_forming = forming.timestamp + timedelta(seconds=1)  # forming candle not yet closed
    with_forming_snapshot = engine.build_snapshot(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1,
        as_of=as_of_forming, source="test",
    )

    assert with_forming_snapshot.live_candle is not None
    assert with_forming_snapshot.live_candle.timestamp == forming.timestamp
    # Every rolling feature is identical to the closed-only snapshot - the
    # forming candle contributed nothing to trend/volatility/momentum/MA.
    assert with_forming_snapshot.trend == closed_snapshot.trend
    assert with_forming_snapshot.volatility == closed_snapshot.volatility
    assert with_forming_snapshot.momentum == closed_snapshot.momentum
    assert with_forming_snapshot.moving_average == closed_snapshot.moving_average
    assert with_forming_snapshot.market_structure == closed_snapshot.market_structure


def test_bounded_eviction_via_engine_history() -> None:
    engine = TechnicalFeatureEngine()
    history = engine.history_for("BTCUSDT", ContractType.PERPETUAL, Timeframe.M1)
    from app.technical.candle_store import ChronologicalCandleStore

    history.candles = ChronologicalCandleStore(capacity=2)
    engine.record_candle("BTCUSDT", ContractType.PERPETUAL, Timeframe.M1, candle(index=0, close="100"))
    engine.record_candle("BTCUSDT", ContractType.PERPETUAL, Timeframe.M1, candle(index=1, close="101"))
    engine.record_candle("BTCUSDT", ContractType.PERPETUAL, Timeframe.M1, candle(index=2, close="102"))
    assert history.candles.dropped_count == 1
    assert len(history.candles) == 2


def test_repeated_build_snapshot_calls_are_deterministic() -> None:
    engine, candles = _fully_warmed_engine()
    as_of = candles[-1].timestamp + timedelta(minutes=1)
    first = engine.build_snapshot(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1, as_of=as_of, source="test"
    )
    second = engine.build_snapshot(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1, as_of=as_of, source="test"
    )
    assert first == second


def test_feature_calculations_unchanged_for_equivalent_chronological_data_regardless_of_insertion_order() -> None:
    ordered_engine, candles = _fully_warmed_engine()
    as_of = candles[-1].timestamp + timedelta(minutes=1)
    ordered_snapshot = ordered_engine.build_snapshot(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1, as_of=as_of, source="test"
    )

    shuffled_engine = TechnicalFeatureEngine()
    shuffled = list(candles)
    shuffled[0], shuffled[-1] = shuffled[-1], shuffled[0]
    shuffled[1], shuffled[-2] = shuffled[-2], shuffled[1]
    shuffled_engine.record_candles("BTCUSDT", ContractType.PERPETUAL, Timeframe.M1, shuffled)
    shuffled_snapshot = shuffled_engine.build_snapshot(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1, as_of=as_of, source="test"
    )

    assert shuffled_snapshot.trend == ordered_snapshot.trend
    assert shuffled_snapshot.market_structure == ordered_snapshot.market_structure
    assert shuffled_snapshot.volatility == ordered_snapshot.volatility
    assert shuffled_snapshot.momentum == ordered_snapshot.momentum
    assert shuffled_snapshot.moving_average == ordered_snapshot.moving_average
    assert shuffled_snapshot.candle_structure == ordered_snapshot.candle_structure
    assert shuffled_snapshot.range_state == ordered_snapshot.range_state


def test_no_windows_or_symbols_hardcoded_custom_config_honored() -> None:
    engine = TechnicalFeatureEngine(trend_lookback=3, ma_periods=(4,))
    candles = candles_from_closes([str(100 + i) for i in range(10)], interval=timedelta(hours=4))
    engine.record_candles("ETHUSDT", ContractType.SPOT, Timeframe.H4, candles)
    snapshot = engine.build_snapshot(
        symbol="ETHUSDT", contract_type=ContractType.SPOT, timeframe=Timeframe.H4,
        as_of=candles[-1].timestamp + timedelta(hours=4), source="test",
    )
    assert snapshot.symbol == "ETHUSDT"
    assert snapshot.contract_type is ContractType.SPOT
    assert snapshot.timeframe is Timeframe.H4
    assert snapshot.trend.lookback == 3
    assert snapshot.moving_average.periods == (4,)

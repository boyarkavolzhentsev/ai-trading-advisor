"""Tests for app.flow.engine.FlowFeatureEngine: composition, isolation, alignment."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.enums.instrument import ContractType
from app.core.enums.order import OrderSide
from app.core.enums.quality import FeatureQuality
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.funding import FundingRate
from app.core.models.liquidation import LiquidationEvent
from app.core.models.open_interest import OpenInterest
from app.core.models.order_book import OrderBookLevel, OrderBookSnapshot
from app.core.models.trade_event import TradeEvent
from app.flow.engine import FlowFeatureEngine

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
WINDOWS = (
    AnalyticsWindow(label="10s", duration=timedelta(seconds=10)),
    AnalyticsWindow(label="1m", duration=timedelta(minutes=1)),
)


def _trade(symbol: str, *, seconds_ago: float, side: OrderSide, price: str, quantity: str, trade_id: int) -> TradeEvent:
    return TradeEvent(
        symbol=symbol,
        contract_type=ContractType.PERPETUAL,
        trade_id=trade_id,
        price=Decimal(price),
        quantity=Decimal(quantity),
        side=side,
        timestamp=NOW - timedelta(seconds=seconds_ago),
        source="test:trade",
    )


def _engine() -> FlowFeatureEngine:
    return FlowFeatureEngine(windows=WINDOWS, depth_bands=())


def test_snapshot_shares_one_observation_time_and_windows_across_domains() -> None:
    engine = _engine()
    engine.record_trade(_trade("BTCUSDT", seconds_ago=1, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    snapshot = engine.build_snapshot(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, observation_time=NOW, default_source="test"
    )
    assert snapshot.observation_time == NOW
    assert snapshot.windows == WINDOWS
    assert set(snapshot.taker_flow) == {"10s", "1m"}
    assert set(snapshot.price_context) == {"10s", "1m"}
    assert set(snapshot.cross_features) == {"10s", "1m"}
    for window_label in ("10s", "1m"):
        assert snapshot.taker_flow[window_label].window_end == NOW
        assert snapshot.price_context[window_label].window_end == NOW


def test_multi_symbol_state_isolation_no_leakage() -> None:
    engine = _engine()
    engine.record_trade(_trade("BTCUSDT", seconds_ago=1, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    engine.record_trade(_trade("ETHUSDT", seconds_ago=1, side=OrderSide.SELL, price="3000", quantity="5", trade_id=1))

    btc = engine.build_snapshot(symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, observation_time=NOW, default_source="test")
    eth = engine.build_snapshot(symbol="ETHUSDT", contract_type=ContractType.PERPETUAL, observation_time=NOW, default_source="test")

    assert btc.symbol == "BTCUSDT"
    assert btc.taker_flow["10s"].delta == Decimal("1")
    assert eth.symbol == "ETHUSDT"
    assert eth.taker_flow["10s"].delta == Decimal("-5")
    # BTC's history must not contain the ETH trade
    assert len(engine.history_for("BTCUSDT", ContractType.PERPETUAL).trades) == 1
    assert len(engine.history_for("ETHUSDT", ContractType.PERPETUAL).trades) == 1


def test_multiple_contract_types_isolated_for_same_symbol() -> None:
    engine = _engine()
    engine.record_trade(
        _trade("BTCUSDT", seconds_ago=1, side=OrderSide.BUY, price="100", quantity="1", trade_id=1)
    )
    spot_trade = TradeEvent(
        symbol="BTCUSDT",
        contract_type=ContractType.SPOT,
        trade_id=1,
        price=Decimal("100"),
        quantity=Decimal("9"),
        side=OrderSide.SELL,
        timestamp=NOW - timedelta(seconds=1),
        source="test:trade",
    )
    engine.record_trade(spot_trade)

    perp = engine.build_snapshot(symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, observation_time=NOW, default_source="test")
    spot = engine.build_snapshot(symbol="BTCUSDT", contract_type=ContractType.SPOT, observation_time=NOW, default_source="test")

    assert perp.taker_flow["10s"].delta == Decimal("1")
    assert spot.taker_flow["10s"].delta == Decimal("-9")


def test_provenance_propagation() -> None:
    # Each domain's source is derived from its own retained events - never a
    # single flat label - so taker_flow/liquidation trace back to their real
    # per-event source while untouched domains fall back to default_source.
    engine = _engine()
    engine.record_trade(
        TradeEvent(
            symbol="BTCUSDT",
            contract_type=ContractType.PERPETUAL,
            trade_id=1,
            price=Decimal("100"),
            quantity=Decimal("1"),
            side=OrderSide.BUY,
            timestamp=NOW - timedelta(seconds=1),
            source="binance:agg_trade",
        )
    )
    engine.record_liquidation(
        LiquidationEvent(
            symbol="BTCUSDT",
            contract_type=ContractType.PERPETUAL,
            side=OrderSide.SELL,
            price=Decimal("100"),
            quantity=Decimal("1"),
            timestamp=NOW,
            source="binance:liquidation",
        )
    )
    snapshot = engine.build_snapshot(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, observation_time=NOW, default_source="unavailable"
    )
    assert snapshot.provenance["taker_flow"] == "binance:agg_trade"
    assert snapshot.provenance["price_context"] == "binance:agg_trade"
    assert snapshot.provenance["liquidation"] == "binance:liquidation"
    assert snapshot.provenance["order_book"] == "unavailable"
    assert snapshot.provenance["open_interest"] == "unavailable"
    assert snapshot.provenance["funding"] == "unavailable"


def test_quality_propagation_no_data_is_unavailable_not_zero() -> None:
    engine = _engine()
    snapshot = engine.build_snapshot(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, observation_time=NOW, default_source="test"
    )
    assert snapshot.taker_flow["10s"].status.quality is FeatureQuality.UNAVAILABLE
    assert snapshot.open_interest.status.quality is FeatureQuality.UNAVAILABLE
    assert snapshot.funding.status.quality is FeatureQuality.UNAVAILABLE
    assert snapshot.order_book.status.quality is FeatureQuality.UNAVAILABLE
    # Liquidations on a healthy (implicitly assumed) stream with zero events is a real zero.
    assert snapshot.liquidation["10s"].status.quality is FeatureQuality.VALID
    assert snapshot.liquidation["10s"].total_liquidation_volume == Decimal("0")


def test_dropped_count_from_bounded_history_flows_into_partial_status() -> None:
    engine = FlowFeatureEngine(windows=WINDOWS, depth_bands=())
    history = engine.history_for("BTCUSDT", ContractType.PERPETUAL)
    # Force a tiny capacity to trigger eviction deterministically.
    from app.market_data.realtime.buffers import BoundedBuffer

    history.trades = BoundedBuffer(maxlen=1)
    engine.record_trade(_trade("BTCUSDT", seconds_ago=90, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    engine.record_trade(_trade("BTCUSDT", seconds_ago=30, side=OrderSide.BUY, price="100", quantity="1", trade_id=2))
    snapshot = engine.build_snapshot(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, observation_time=NOW, default_source="test"
    )
    assert history.trades.dropped_count == 1
    assert snapshot.taker_flow["1m"].status.quality is FeatureQuality.PARTIAL


def test_cross_feature_correlation_builds_over_snapshot_history() -> None:
    # With UTC epoch-aligned windows, "sample i" must land in a distinct
    # aligned 10s bucket - otherwise repeated calls within the same bucket
    # observe the identical most-recently-completed window and produce a
    # constant (non-correlatable) series. BASE is a 10s-grid-aligned anchor
    # (UTC midnight) so each iteration's two trades sit inside their own,
    # fully separate, already-closed 10s window.
    base = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    engine = _engine()
    snapshot = None
    for i in range(4):
        bucket_start = base + timedelta(seconds=10 * i)
        observation_time = bucket_start + timedelta(seconds=10)  # exact end of bucket i
        engine.record_trade(
            TradeEvent(
                symbol="BTCUSDT",
                contract_type=ContractType.PERPETUAL,
                trade_id=i * 2,
                price=Decimal("100"),
                quantity=Decimal(str(1 + i)),
                side=OrderSide.BUY,
                timestamp=bucket_start + timedelta(seconds=3),
                source="test:trade",
            )
        )
        engine.record_trade(
            TradeEvent(
                symbol="BTCUSDT",
                contract_type=ContractType.PERPETUAL,
                trade_id=i * 2 + 1,
                price=Decimal(str(100 + (1 + i) * 2)),
                quantity=Decimal(str(1 + i)),
                side=OrderSide.BUY,
                timestamp=bucket_start + timedelta(seconds=8),
                source="test:trade",
            )
        )
        snapshot = engine.build_snapshot(
            symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, observation_time=observation_time, default_source="test"
        )
    assert snapshot is not None
    assert snapshot.cross_features["10s"].sample_count >= 3
    assert snapshot.cross_features["10s"].status.quality is FeatureQuality.VALID
    assert snapshot.cross_features["10s"].correlation == pytest.approx(1.0)


def test_no_windows_hardcoded_custom_window_set_honored() -> None:
    custom = (AnalyticsWindow(label="2s", duration=timedelta(seconds=2)),)
    engine = FlowFeatureEngine(windows=custom, depth_bands=())
    snapshot = engine.build_snapshot(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, observation_time=NOW, default_source="test"
    )
    assert set(snapshot.taker_flow) == {"2s"}
    assert snapshot.windows == custom

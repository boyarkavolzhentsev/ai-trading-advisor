"""Tests for app.flow.taker_flow.compute_taker_flow_features."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.order import OrderSide
from app.core.enums.quality import FeatureQuality
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.trade_event import TradeEvent
from app.flow.taker_flow import compute_taker_flow_features

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
WINDOWS = (
    AnalyticsWindow(label="10s", duration=timedelta(seconds=10)),
    AnalyticsWindow(label="1m", duration=timedelta(minutes=1)),
)


def _trade(*, seconds_ago: float, side: OrderSide, quantity: str, trade_id: int) -> TradeEvent:
    return TradeEvent(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        trade_id=trade_id,
        price=Decimal("50000"),
        quantity=Decimal(quantity),
        side=side,
        timestamp=NOW - timedelta(seconds=seconds_ago),
        source="test:trade",
    )


def test_exact_arithmetic_single_window() -> None:
    trades = [
        _trade(seconds_ago=5, side=OrderSide.BUY, quantity="2", trade_id=1),
        _trade(seconds_ago=3, side=OrderSide.SELL, quantity="1", trade_id=2),
        _trade(seconds_ago=1, side=OrderSide.BUY, quantity="0.5", trade_id=3),
    ]
    features = compute_taker_flow_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        trades=trades,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:trade",
    )
    f10s = features["10s"]
    assert f10s.buy_volume == Decimal("2.5")
    assert f10s.sell_volume == Decimal("1")
    assert f10s.total_volume == Decimal("3.5")
    assert f10s.delta == Decimal("1.5")
    assert f10s.buy_ratio == 2.5 / 3.5
    assert f10s.sell_ratio == 1 - (2.5 / 3.5)
    assert f10s.delta_rate == Decimal("1.5") / Decimal("10")
    assert f10s.trade_count == 3
    assert f10s.status.quality is FeatureQuality.VALID
    assert f10s.cumulative_delta == Decimal("1.5")


def test_empty_window_is_unavailable_not_zero_ratio() -> None:
    trades = [_trade(seconds_ago=50, side=OrderSide.BUY, quantity="1", trade_id=1)]
    features = compute_taker_flow_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        trades=trades,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:trade",
    )
    f10s = features["10s"]
    assert f10s.trade_count == 0
    assert f10s.buy_volume == Decimal("0")
    assert f10s.total_volume == Decimal("0")
    assert f10s.buy_ratio is None
    assert f10s.sell_ratio is None
    assert f10s.status.quality is FeatureQuality.UNAVAILABLE
    assert f10s.status.reasons == ["no trades in window"]


def test_no_history_at_all_is_unavailable_with_no_cumulative_origin() -> None:
    features = compute_taker_flow_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        trades=[],
        windows=WINDOWS,
        observation_time=NOW,
        source="test:trade",
    )
    f1m = features["1m"]
    assert f1m.status.quality is FeatureQuality.UNAVAILABLE
    assert f1m.cumulative_delta == Decimal("0")
    assert f1m.cumulative_delta_since is None


def test_cumulative_delta_spans_whole_retained_history_not_just_window() -> None:
    trades = [
        _trade(seconds_ago=55, side=OrderSide.BUY, quantity="10", trade_id=1),  # outside both windows
        _trade(seconds_ago=5, side=OrderSide.SELL, quantity="1", trade_id=2),   # inside 10s window
    ]
    features = compute_taker_flow_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        trades=trades,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:trade",
    )
    f10s = features["10s"]
    assert f10s.delta == Decimal("-1")  # window-local: only the sell counts
    assert f10s.cumulative_delta == Decimal("9")  # whole history: 10 buy - 1 sell
    assert f10s.cumulative_delta_since == NOW - timedelta(seconds=55)


def test_late_future_dated_trade_is_excluded_deterministically() -> None:
    trades = [
        _trade(seconds_ago=5, side=OrderSide.BUY, quantity="1", trade_id=1),
        TradeEvent(
            symbol="BTCUSDT",
            contract_type=ContractType.PERPETUAL,
            trade_id=2,
            price=Decimal("50000"),
            quantity=Decimal("100"),
            side=OrderSide.BUY,
            timestamp=NOW + timedelta(seconds=1),  # after observation_time
            source="test:trade",
        ),
    ]
    features = compute_taker_flow_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        trades=trades,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:trade",
    )
    assert features["10s"].buy_volume == Decimal("1")
    assert features["10s"].cumulative_delta == Decimal("1")


def test_truncated_history_marks_partial() -> None:
    # Only trade retained starts well inside the 1m window's start boundary,
    # simulating a bounded buffer that evicted older trades.
    trades = [_trade(seconds_ago=30, side=OrderSide.BUY, quantity="1", trade_id=1)]
    features = compute_taker_flow_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        trades=trades,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:trade",
        dropped_count=5,
    )
    f1m = features["1m"]
    assert f1m.trade_count == 1
    assert f1m.status.quality is FeatureQuality.PARTIAL
    f10s = features["10s"]  # trade is outside 10s window entirely -> UNAVAILABLE, not PARTIAL
    assert f10s.status.quality is FeatureQuality.UNAVAILABLE


def test_no_truncation_flag_when_nothing_dropped() -> None:
    trades = [_trade(seconds_ago=5, side=OrderSide.BUY, quantity="1", trade_id=1)]
    features = compute_taker_flow_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        trades=trades,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:trade",
        dropped_count=0,
    )
    assert features["10s"].status.quality is FeatureQuality.VALID


def test_multiple_symbols_do_not_leak_into_each_other() -> None:
    btc_trades = [_trade(seconds_ago=1, side=OrderSide.BUY, quantity="1", trade_id=1)]
    eth_trade = TradeEvent(
        symbol="ETHUSDT",
        contract_type=ContractType.PERPETUAL,
        trade_id=1,
        price=Decimal("3000"),
        quantity=Decimal("5"),
        side=OrderSide.SELL,
        timestamp=NOW,
        source="test:trade",
    )
    btc_features = compute_taker_flow_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        trades=btc_trades,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:trade",
    )
    eth_features = compute_taker_flow_features(
        symbol="ETHUSDT",
        contract_type=ContractType.PERPETUAL,
        trades=[eth_trade],
        windows=WINDOWS,
        observation_time=NOW,
        source="test:trade",
    )
    assert btc_features["10s"].symbol == "BTCUSDT"
    assert btc_features["10s"].delta == Decimal("1")
    assert eth_features["10s"].symbol == "ETHUSDT"
    assert eth_features["10s"].delta == Decimal("-5")


def test_uses_shared_utc_epoch_aligned_window_not_raw_trailing() -> None:
    # observation_time is deliberately not on a 10s grid line; the aligned
    # 10s window is (NOW+20s, NOW+30s]. A trade placed after that aligned
    # window_end but still before observation_time must be excluded - under
    # the old trailing-to-now design it would have counted.
    observation_time = NOW + timedelta(seconds=37)
    trades = [
        _trade(seconds_ago=-3, side=OrderSide.BUY, quantity="1", trade_id=1),  # NOW+3s: outside window
        _trade(seconds_ago=-25, side=OrderSide.BUY, quantity="2", trade_id=2),  # NOW+25s: inside (20,30]
        _trade(seconds_ago=-30, side=OrderSide.BUY, quantity="4", trade_id=3),  # NOW+30s: at window_end, included
        _trade(seconds_ago=-20, side=OrderSide.SELL, quantity="1", trade_id=4),  # NOW+20s: at window_start, excluded
    ]
    features = compute_taker_flow_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        trades=trades,
        windows=WINDOWS,
        observation_time=observation_time,
        source="test:trade",
    )
    f10s = features["10s"]
    assert f10s.window_start == NOW + timedelta(seconds=20)
    assert f10s.window_end == NOW + timedelta(seconds=30)
    assert f10s.buy_volume == Decimal("6")  # trades 2 and 3 only
    assert f10s.sell_volume == Decimal("0")  # trade 4 excluded (at window_start)
    assert f10s.trade_count == 2


def test_source_propagation() -> None:
    trades = [_trade(seconds_ago=1, side=OrderSide.BUY, quantity="1", trade_id=1)]
    features = compute_taker_flow_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        trades=trades,
        windows=WINDOWS,
        observation_time=NOW,
        source="binance:agg_trade",
    )
    assert features["10s"].source == "binance:agg_trade"

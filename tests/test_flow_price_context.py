"""Tests for app.flow.price_context.compute_price_context_features."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.order import OrderSide
from app.core.enums.quality import FeatureQuality
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.funding import FundingRate
from app.core.models.trade_event import TradeEvent
from app.flow.price_context import compute_price_context_features

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
WINDOWS = (AnalyticsWindow(label="10s", duration=timedelta(seconds=10)),)


def _trade(*, seconds_ago: float, price: str, trade_id: int) -> TradeEvent:
    return TradeEvent(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        trade_id=trade_id,
        price=Decimal(price),
        quantity=Decimal("1"),
        side=OrderSide.BUY,
        timestamp=NOW - timedelta(seconds=seconds_ago),
        source="test:trade",
    )


def _mark(*, seconds_ago: float, price: str) -> FundingRate:
    return FundingRate(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        funding_rate=Decimal("0.0001"),
        mark_price=Decimal(price),
        index_price=Decimal(price),
        source="test:mark_price",
        timestamp=NOW - timedelta(seconds=seconds_ago),
    )


def test_return_absolute_change_and_range_exact() -> None:
    trades = [
        _trade(seconds_ago=8, price="100", trade_id=1),
        _trade(seconds_ago=5, price="105", trade_id=2),
        _trade(seconds_ago=1, price="98", trade_id=3),
    ]
    features = compute_price_context_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        trades=trades,
        mark_prices=[],
        windows=WINDOWS,
        observation_time=NOW,
        source="test:trade",
    )
    f = features["10s"]
    assert f.absolute_change == Decimal("98") - Decimal("100")
    assert f.return_pct == (Decimal("98") - Decimal("100")) / Decimal("100") * 100
    assert f.realized_range == Decimal("105") - Decimal("98")
    assert f.trade_count == 3
    assert f.status.quality is FeatureQuality.VALID


def test_empty_window_unavailable() -> None:
    features = compute_price_context_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        trades=[],
        mark_prices=[],
        windows=WINDOWS,
        observation_time=NOW,
        source="test:trade",
    )
    f = features["10s"]
    assert f.status.quality is FeatureQuality.UNAVAILABLE
    assert f.return_pct is None
    assert f.realized_range is None


def test_single_trade_marks_partial_with_zero_range() -> None:
    trades = [_trade(seconds_ago=1, price="100", trade_id=1)]
    features = compute_price_context_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        trades=trades,
        mark_prices=[],
        windows=WINDOWS,
        observation_time=NOW,
        source="test:trade",
    )
    f = features["10s"]
    assert f.status.quality is FeatureQuality.PARTIAL
    assert f.return_pct is None
    assert f.absolute_change is None
    assert f.realized_range == Decimal("0")


def test_mark_price_change_exact() -> None:
    # window is 10s; the baseline is the mark at/before window_start, so one
    # observation must sit before that boundary.
    marks = [_mark(seconds_ago=15, price="50000"), _mark(seconds_ago=1, price="50050")]
    features = compute_price_context_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        trades=[],
        mark_prices=marks,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:trade",
    )
    f = features["10s"]
    assert f.mark_price_change == Decimal("50")


def test_mark_price_change_uses_aligned_endpoints_not_raw_trailing() -> None:
    # window=10s; observation_time=NOW+13s -> aligned window is (NOW, NOW+10s].
    # A mark price after window_end (but before observation_time) must NOT
    # be used as the window's "end" comparison point.
    marks = [
        _mark(seconds_ago=1, price="50000"),  # NOW-1s: at/before window_start(NOW)
        _mark(seconds_ago=-8, price="50100"),  # NOW+8s: at/before window_end(NOW+10s)
        _mark(seconds_ago=-11, price="99999"),  # NOW+11s: after window_end, before observation_time
    ]
    observation_time = NOW + timedelta(seconds=13)
    features = compute_price_context_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        trades=[],
        mark_prices=marks,
        windows=WINDOWS,
        observation_time=observation_time,
        source="test:trade",
    )
    f = features["10s"]
    assert f.window_start == NOW
    assert f.window_end == NOW + timedelta(seconds=10)
    assert f.mark_price_change == Decimal("100")  # 50100 - 50000, not 99999-based


def test_mark_price_change_none_when_no_prior_mark() -> None:
    marks = [_mark(seconds_ago=1, price="50050")]
    features = compute_price_context_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        trades=[],
        mark_prices=marks,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:trade",
    )
    assert features["10s"].mark_price_change is None

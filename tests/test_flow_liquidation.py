"""Tests for app.flow.liquidation.compute_liquidation_features."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.order import OrderSide
from app.core.enums.quality import FeatureQuality
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.liquidation import LiquidationEvent
from app.flow.liquidation import compute_liquidation_features

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
WINDOWS = (
    AnalyticsWindow(label="10s", duration=timedelta(seconds=10)),
    AnalyticsWindow(label="1m", duration=timedelta(minutes=1)),
)


def _liq(*, seconds_ago: float, side: OrderSide, quantity: str) -> LiquidationEvent:
    return LiquidationEvent(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        side=side,
        price=Decimal("50000"),
        quantity=Decimal(quantity),
        timestamp=NOW - timedelta(seconds=seconds_ago),
        source="test:liquidation",
    )


def test_forced_sell_counts_as_long_liquidation() -> None:
    events = [_liq(seconds_ago=1, side=OrderSide.SELL, quantity="1")]
    features = compute_liquidation_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        liquidations=events,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:liquidation",
    )
    f = features["10s"]
    assert f.long_liquidation_volume == Decimal("1")
    assert f.short_liquidation_volume == Decimal("0")
    assert f.liquidation_count_long == 1
    assert f.liquidation_count_short == 0


def test_forced_buy_counts_as_short_liquidation() -> None:
    events = [_liq(seconds_ago=1, side=OrderSide.BUY, quantity="2")]
    features = compute_liquidation_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        liquidations=events,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:liquidation",
    )
    f = features["10s"]
    assert f.short_liquidation_volume == Decimal("2")
    assert f.long_liquidation_volume == Decimal("0")
    assert f.liquidation_count_short == 1


def test_exact_arithmetic_mixed_sides() -> None:
    events = [
        _liq(seconds_ago=1, side=OrderSide.SELL, quantity="3"),
        _liq(seconds_ago=2, side=OrderSide.SELL, quantity="2"),
        _liq(seconds_ago=3, side=OrderSide.BUY, quantity="1"),
    ]
    features = compute_liquidation_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        liquidations=events,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:liquidation",
    )
    f = features["10s"]
    assert f.long_liquidation_volume == Decimal("5")
    assert f.short_liquidation_volume == Decimal("1")
    assert f.total_liquidation_volume == Decimal("6")
    assert f.liquidation_imbalance == Decimal("4")
    assert f.liquidation_count == 3
    assert f.average_liquidation_size == Decimal("6") / 3
    assert f.largest_liquidation == Decimal("3")


def test_empty_window_on_healthy_stream_is_valid_zero_not_unavailable() -> None:
    features = compute_liquidation_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        liquidations=[],
        windows=WINDOWS,
        observation_time=NOW,
        source="test:liquidation",
    )
    f = features["10s"]
    assert f.status.quality is FeatureQuality.VALID
    assert f.total_liquidation_volume == Decimal("0")
    assert f.liquidation_count == 0
    assert f.average_liquidation_size is None
    assert f.largest_liquidation is None


def test_truncated_history_marks_partial() -> None:
    events = [_liq(seconds_ago=30, side=OrderSide.SELL, quantity="1")]
    features = compute_liquidation_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        liquidations=events,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:liquidation",
        dropped_count=3,
    )
    assert features["1m"].status.quality is FeatureQuality.PARTIAL


def test_multiple_contract_types_are_independent_calls() -> None:
    spot_events = [_liq(seconds_ago=1, side=OrderSide.SELL, quantity="1")]
    perp_features = compute_liquidation_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        liquidations=spot_events,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:liquidation",
    )
    assert perp_features["10s"].contract_type is ContractType.PERPETUAL


def test_uses_shared_utc_epoch_aligned_window_not_raw_trailing() -> None:
    # Aligned 10s window for observation_time=NOW+37s is (NOW+20s, NOW+30s].
    # An event after that aligned window_end but before observation_time
    # must be excluded.
    observation_time = NOW + timedelta(seconds=37)
    events = [
        _liq(seconds_ago=-3, side=OrderSide.SELL, quantity="9"),  # NOW+3s: outside window
        _liq(seconds_ago=-25, side=OrderSide.SELL, quantity="1"),  # NOW+25s: inside
        _liq(seconds_ago=-30, side=OrderSide.SELL, quantity="2"),  # NOW+30s: at window_end, included
        _liq(seconds_ago=-20, side=OrderSide.BUY, quantity="5"),  # NOW+20s: at window_start, excluded
    ]
    features = compute_liquidation_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        liquidations=events,
        windows=WINDOWS,
        observation_time=observation_time,
        source="test:liquidation",
    )
    f10s = features["10s"]
    assert f10s.window_start == NOW + timedelta(seconds=20)
    assert f10s.window_end == NOW + timedelta(seconds=30)
    assert f10s.long_liquidation_volume == Decimal("3")  # events 2 and 3 only
    assert f10s.short_liquidation_volume == Decimal("0")  # event 4 excluded (at window_start)


def test_source_propagation() -> None:
    events = [_liq(seconds_ago=1, side=OrderSide.SELL, quantity="1")]
    features = compute_liquidation_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        liquidations=events,
        windows=WINDOWS,
        observation_time=NOW,
        source="binance:liquidation",
    )
    assert features["10s"].source == "binance:liquidation"

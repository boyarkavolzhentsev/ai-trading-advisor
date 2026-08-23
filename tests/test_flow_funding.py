"""Tests for app.flow.funding.compute_funding_features."""

from __future__ import annotations

import statistics
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.quality import FeatureQuality
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.funding import FundingRate
from app.flow.funding import compute_funding_features

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
WINDOWS = (AnalyticsWindow(label="5m", duration=timedelta(minutes=5)),)


def _funding(
    *, seconds_ago: float, rate: str, mark: str = "50000", index: str = "50000", next_funding_in: float | None = None
) -> FundingRate:
    ts = NOW - timedelta(seconds=seconds_ago)
    return FundingRate(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        funding_rate=Decimal(rate),
        funding_interval_hours=None,
        mark_price=Decimal(mark),
        index_price=Decimal(index),
        next_funding_time=(ts + timedelta(hours=next_funding_in)) if next_funding_in is not None else None,
        source="test:mark_price",
        timestamp=ts,
    )


def test_no_history_is_unavailable() -> None:
    features = compute_funding_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=[],
        windows=WINDOWS,
        observation_time=NOW,
        source="test:mark_price",
    )
    assert features.status.quality is FeatureQuality.UNAVAILABLE


def test_mark_index_basis_and_bps() -> None:
    history = [_funding(seconds_ago=0, rate="0.0001", mark="50010", index="50000")]
    features = compute_funding_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=history,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:mark_price",
    )
    assert features.mark_index_basis == Decimal("10")
    assert features.mark_index_basis_bps == Decimal("10") / Decimal("50000") * 10000


def test_no_hardcoded_funding_interval_time_to_next_funding_none_when_undisclosed() -> None:
    history = [_funding(seconds_ago=0, rate="0.0001")]  # next_funding_time not set
    features = compute_funding_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=history,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:mark_price",
    )
    assert features.time_to_next_funding is None


def test_time_to_next_funding_when_disclosed() -> None:
    history = [_funding(seconds_ago=0, rate="0.0001", next_funding_in=2.0)]
    features = compute_funding_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=history,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:mark_price",
    )
    assert features.time_to_next_funding == timedelta(hours=2)


def test_funding_trend_exact() -> None:
    # window is 5m (300s); the baseline for "trend" is the observation at/before
    # window_start, so one sample must sit before that boundary.
    history = [
        _funding(seconds_ago=400, rate="0.0001"),
        _funding(seconds_ago=100, rate="0.00015"),
        _funding(seconds_ago=0, rate="0.0002"),
    ]
    features = compute_funding_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=history,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:mark_price",
    )
    w5m = features.windows["5m"]
    assert w5m.funding_trend == Decimal("0.0002") - Decimal("0.0001")


def test_rolling_mean_and_stddev_exact() -> None:
    rates = [Decimal("0.0001"), Decimal("0.00015"), Decimal("0.0002")]
    history = [_funding(seconds_ago=200 - i * 90, rate=str(r)) for i, r in enumerate(rates)]
    features = compute_funding_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=history,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:mark_price",
    )
    w5m = features.windows["5m"]
    assert w5m.rolling_mean == statistics.mean(rates)
    assert w5m.rolling_stddev == statistics.pstdev(rates)
    assert w5m.status.quality is FeatureQuality.VALID


def test_single_sample_window_stddev_undefined_marks_partial() -> None:
    history = [_funding(seconds_ago=0, rate="0.0001")]
    features = compute_funding_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=history,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:mark_price",
    )
    w5m = features.windows["5m"]
    assert w5m.sample_count == 1
    assert w5m.rolling_stddev is None
    assert w5m.rolling_mean is not None
    assert w5m.status.quality is FeatureQuality.PARTIAL


def test_stale_funding_keeps_last_known_value() -> None:
    history = [_funding(seconds_ago=600, rate="0.0001")]
    features = compute_funding_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=history,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:mark_price",
        max_staleness=timedelta(minutes=5),
    )
    assert features.status.quality is FeatureQuality.STALE
    assert features.latest_funding_rate == Decimal("0.0001")


def test_funding_trend_uses_aligned_endpoints_not_top_level_latest() -> None:
    # window=5m(300s); observation_time=NOW+310s -> aligned window is (NOW, NOW+300s].
    # An observation after window_end (but before observation_time) must NOT
    # be used as the window's "end" comparison point, even though it *is*
    # legitimately the top-level "current" latest_funding_rate.
    history = [
        _funding(seconds_ago=10, rate="0.0001"),  # NOW-10s: at/before window_start(NOW)
        _funding(seconds_ago=-250, rate="0.00015"),  # NOW+250s: at/before window_end(NOW+300s)
        _funding(seconds_ago=-305, rate="0.9999"),  # NOW+305s: after window_end, before observation_time
    ]
    observation_time = NOW + timedelta(seconds=310)
    features = compute_funding_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=history,
        windows=WINDOWS,
        observation_time=observation_time,
        source="test:mark_price",
    )
    assert features.latest_funding_rate == Decimal("0.9999")  # top-level: true "now", unaligned
    w5m = features.windows["5m"]
    assert w5m.funding_trend == Decimal("0.00015") - Decimal("0.0001")


def test_multiple_symbols_independent() -> None:
    btc_features = compute_funding_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=[_funding(seconds_ago=0, rate="0.0001")],
        windows=WINDOWS,
        observation_time=NOW,
        source="test:mark_price",
    )
    eth_history = [
        FundingRate(
            symbol="ETHUSDT",
            contract_type=ContractType.PERPETUAL,
            funding_rate=Decimal("-0.0002"),
            mark_price=Decimal("3000"),
            index_price=Decimal("3000"),
            source="test:mark_price",
            timestamp=NOW,
        )
    ]
    eth_features = compute_funding_features(
        symbol="ETHUSDT",
        contract_type=ContractType.PERPETUAL,
        history=eth_history,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:mark_price",
    )
    assert btc_features.latest_funding_rate == Decimal("0.0001")
    assert eth_features.latest_funding_rate == Decimal("-0.0002")

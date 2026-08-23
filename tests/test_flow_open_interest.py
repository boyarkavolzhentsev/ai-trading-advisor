"""Tests for app.flow.open_interest.compute_open_interest_features."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.quality import FeatureQuality
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.open_interest import OpenInterest
from app.flow.open_interest import compute_open_interest_features

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
WINDOWS = (
    AnalyticsWindow(label="1m", duration=timedelta(minutes=1)),
    AnalyticsWindow(label="5m", duration=timedelta(minutes=5)),
)


def _oi(*, seconds_ago: float, value: str) -> OpenInterest:
    return OpenInterest(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        open_interest=Decimal(value),
        source="test:open_interest",
        timestamp=NOW - timedelta(seconds=seconds_ago),
    )


def test_no_history_is_unavailable() -> None:
    features = compute_open_interest_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=[],
        windows=WINDOWS,
        observation_time=NOW,
        source="test:open_interest",
    )
    assert features.status.quality is FeatureQuality.UNAVAILABLE
    assert features.latest_open_interest is None


def test_absolute_and_percent_change_exact() -> None:
    history = [_oi(seconds_ago=90, value="1000"), _oi(seconds_ago=0, value="1100")]
    features = compute_open_interest_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=history,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:open_interest",
    )
    w1m = features.windows["1m"]
    assert w1m.absolute_change == Decimal("100")
    assert w1m.percent_change == Decimal("100") / Decimal("1000") * 100
    assert w1m.oi_velocity == Decimal("100") / Decimal("60")


def test_no_prior_observation_before_window_is_unavailable() -> None:
    history = [_oi(seconds_ago=0, value="1000")]
    features = compute_open_interest_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=history,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:open_interest",
    )
    w1m = features.windows["1m"]
    assert w1m.status.quality is FeatureQuality.UNAVAILABLE
    assert w1m.absolute_change is None
    assert w1m.percent_change is None


def test_never_interpolates_uses_last_known_value_and_staleness() -> None:
    history = [_oi(seconds_ago=600, value="1000")]  # 10 minutes old
    features = compute_open_interest_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=history,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:open_interest",
        max_staleness=timedelta(minutes=5),
    )
    assert features.status.quality is FeatureQuality.STALE
    assert features.latest_open_interest == Decimal("1000")  # not blanked
    assert features.staleness_seconds == 600.0


def test_zero_prior_open_interest_percent_change_undefined() -> None:
    history = [_oi(seconds_ago=90, value="0"), _oi(seconds_ago=0, value="50")]
    features = compute_open_interest_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=history,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:open_interest",
    )
    w1m = features.windows["1m"]
    assert w1m.absolute_change == Decimal("50")
    assert w1m.percent_change is None


def test_window_change_uses_aligned_endpoints_not_top_level_latest() -> None:
    # window=1m(60s); observation_time=NOW+70s -> aligned window is (NOW, NOW+60s].
    # An observation after window_end (but before observation_time) must NOT
    # be used as the window's "end" comparison point, even though it *is*
    # legitimately the top-level "current" latest_open_interest.
    history = [
        _oi(seconds_ago=10, value="1000"),  # NOW-10s: at/before window_start(NOW) -> start_value
        _oi(seconds_ago=-30, value="1050"),  # NOW+30s: at/before window_end(NOW+60s) -> end_value
        _oi(seconds_ago=-65, value="9999"),  # NOW+65s: after window_end, before observation_time
    ]
    observation_time = NOW + timedelta(seconds=70)
    features = compute_open_interest_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=history,
        windows=WINDOWS,
        observation_time=observation_time,
        source="test:open_interest",
    )
    assert features.latest_open_interest == Decimal("9999")  # top-level: true "now", unaligned
    w1m = features.windows["1m"]
    assert w1m.absolute_change == Decimal("50")  # 1050 - 1000, aligned endpoints only


def test_multiple_symbols_independent() -> None:
    btc_features = compute_open_interest_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=[_oi(seconds_ago=0, value="1000")],
        windows=WINDOWS,
        observation_time=NOW,
        source="test:open_interest",
    )
    eth_history = [
        OpenInterest(
            symbol="ETHUSDT",
            contract_type=ContractType.PERPETUAL,
            open_interest=Decimal("500"),
            source="test:open_interest",
            timestamp=NOW,
        )
    ]
    eth_features = compute_open_interest_features(
        symbol="ETHUSDT",
        contract_type=ContractType.PERPETUAL,
        history=eth_history,
        windows=WINDOWS,
        observation_time=NOW,
        source="test:open_interest",
    )
    assert btc_features.symbol == "BTCUSDT"
    assert btc_features.latest_open_interest == Decimal("1000")
    assert eth_features.symbol == "ETHUSDT"
    assert eth_features.latest_open_interest == Decimal("500")

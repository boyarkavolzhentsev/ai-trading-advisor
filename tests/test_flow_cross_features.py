"""Tests for app.flow.cross_features.compute_cross_feature_observation."""

from __future__ import annotations

import statistics
from datetime import timedelta

from app.core.enums.instrument import ContractType
from app.core.enums.quality import FeatureQuality
from app.core.models.analytics_window import AnalyticsWindow
from app.flow.cross_features import compute_cross_feature_observation

WINDOW = AnalyticsWindow(label="1m", duration=timedelta(minutes=1))


def test_exact_correlation_perfect_positive() -> None:
    series_a = [1.0, 2.0, 3.0, 4.0]
    series_b = [10.0, 20.0, 30.0, 40.0]
    obs = compute_cross_feature_observation(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        window=WINDOW,
        pair_label="return_pct_vs_delta",
        series_a=series_a,
        series_b=series_b,
    )
    assert obs.correlation == statistics.correlation(series_a, series_b)
    assert obs.correlation == 1.0
    assert obs.sample_count == 4
    assert obs.status.quality is FeatureQuality.VALID


def test_below_minimum_samples_is_unavailable() -> None:
    obs = compute_cross_feature_observation(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        window=WINDOW,
        pair_label="return_pct_vs_delta",
        series_a=[1.0, 2.0],
        series_b=[1.0, 2.0],
    )
    assert obs.status.quality is FeatureQuality.UNAVAILABLE
    assert obs.correlation is None
    assert obs.sample_count == 2


def test_none_entries_are_dropped_before_pairing() -> None:
    series_a = [1.0, None, 3.0, 4.0, 5.0]
    series_b = [10.0, 99.0, 30.0, 40.0, 50.0]
    obs = compute_cross_feature_observation(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        window=WINDOW,
        pair_label="pair",
        series_a=series_a,
        series_b=series_b,
    )
    assert obs.sample_count == 4  # index 1 dropped from both
    assert obs.status.quality is FeatureQuality.VALID
    assert obs.correlation == 1.0


def test_zero_variance_series_is_unavailable_not_a_crash() -> None:
    obs = compute_cross_feature_observation(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        window=WINDOW,
        pair_label="pair",
        series_a=[1.0, 1.0, 1.0],
        series_b=[1.0, 2.0, 3.0],
    )
    assert obs.status.quality is FeatureQuality.UNAVAILABLE
    assert obs.correlation is None

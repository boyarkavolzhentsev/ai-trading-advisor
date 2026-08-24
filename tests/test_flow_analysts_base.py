"""Tests for app.flow_analysts.base: shared deterministic primitives."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from app.core.enums.flow_analysis import AgreementVerdict, OrdinalTrend
from app.core.enums.quality import FeatureQuality
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.feature_status import FeatureStatus
from app.flow_analysts.base import agreement_of, make_evidence, ordinal_trend, qualifies, shortest_and_longest, sign_category, worse_of_many


class _Category(StrEnum):
    POS = "POS"
    NEG = "NEG"
    ZERO = "ZERO"


def test_qualifies_true_for_valid_partial_stale_false_for_unavailable() -> None:
    assert qualifies(FeatureStatus(quality=FeatureQuality.VALID))
    assert qualifies(FeatureStatus(quality=FeatureQuality.PARTIAL))
    assert qualifies(FeatureStatus(quality=FeatureQuality.STALE))
    assert not qualifies(FeatureStatus(quality=FeatureQuality.UNAVAILABLE))


def test_sign_category_positive_negative_zero_and_none() -> None:
    assert sign_category(Decimal("1"), positive=_Category.POS, negative=_Category.NEG, zero=_Category.ZERO) is _Category.POS
    assert sign_category(Decimal("-1"), positive=_Category.POS, negative=_Category.NEG, zero=_Category.ZERO) is _Category.NEG
    assert sign_category(Decimal("0"), positive=_Category.POS, negative=_Category.NEG, zero=_Category.ZERO) is _Category.ZERO
    assert sign_category(None, positive=_Category.POS, negative=_Category.NEG, zero=_Category.ZERO) is None


def test_sign_category_zero_is_never_none() -> None:
    # A genuine zero must never be conflated with a missing value.
    result = sign_category(Decimal("0"), positive=_Category.POS, negative=_Category.NEG, zero=_Category.ZERO)
    assert result is _Category.ZERO
    assert result is not None


def test_agreement_of_requires_at_least_two_entries() -> None:
    assert agreement_of([]) is AgreementVerdict.INSUFFICIENT_DATA
    assert agreement_of([_Category.POS]) is AgreementVerdict.INSUFFICIENT_DATA


def test_agreement_of_all_agree() -> None:
    assert agreement_of([_Category.POS, _Category.POS, _Category.POS]) is AgreementVerdict.ALL_AGREE


def test_agreement_of_mixed() -> None:
    assert agreement_of([_Category.POS, _Category.NEG]) is AgreementVerdict.MIXED


def test_ordinal_trend_increasing_decreasing_stable_insufficient() -> None:
    assert ordinal_trend(Decimal("5"), Decimal("1")) is OrdinalTrend.INCREASING
    assert ordinal_trend(Decimal("1"), Decimal("5")) is OrdinalTrend.DECREASING
    assert ordinal_trend(Decimal("5"), Decimal("5")) is OrdinalTrend.STABLE
    assert ordinal_trend(None, Decimal("5")) is OrdinalTrend.INSUFFICIENT_DATA
    assert ordinal_trend(Decimal("5"), None) is OrdinalTrend.INSUFFICIENT_DATA


def test_shortest_and_longest_picks_by_duration() -> None:
    windows = {
        "1m": AnalyticsWindow(label="1m", duration=timedelta(minutes=1)),
        "10s": AnalyticsWindow(label="10s", duration=timedelta(seconds=10)),
        "5m": AnalyticsWindow(label="5m", duration=timedelta(minutes=5)),
    }
    assert shortest_and_longest(windows) == ("10s", "5m")


def test_shortest_and_longest_none_when_fewer_than_two() -> None:
    assert shortest_and_longest({}) is None
    assert shortest_and_longest({"10s": AnalyticsWindow(label="10s", duration=timedelta(seconds=10))}) is None


def test_worse_of_many_folds_severity() -> None:
    assert worse_of_many([FeatureQuality.VALID, FeatureQuality.VALID]) is FeatureQuality.VALID
    assert worse_of_many([FeatureQuality.VALID, FeatureQuality.PARTIAL]) is FeatureQuality.PARTIAL
    assert worse_of_many([FeatureQuality.PARTIAL, FeatureQuality.STALE]) is FeatureQuality.STALE
    assert worse_of_many([FeatureQuality.STALE, FeatureQuality.UNAVAILABLE]) is FeatureQuality.UNAVAILABLE
    assert worse_of_many([]) is FeatureQuality.VALID


def test_make_evidence_stringifies_values_and_preserves_fields() -> None:
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    evidence = make_evidence(
        feature_name="taker_flow.delta",
        window="1m",
        observed_value=Decimal("1.5"),
        reference_value=Decimal("0.5"),
        quality=FeatureQuality.VALID,
        source_timestamp=ts,
        provenance="binance:agg_trade",
    )
    assert evidence.feature_name == "taker_flow.delta"
    assert evidence.window == "1m"
    assert evidence.observed_value == "1.5"
    assert evidence.reference_value == "0.5"
    assert evidence.quality is FeatureQuality.VALID
    assert evidence.source_timestamp == ts
    assert evidence.provenance == "binance:agg_trade"


def test_make_evidence_none_reference_stays_none() -> None:
    evidence = make_evidence(
        feature_name="taker_flow.delta",
        window=None,
        observed_value=Decimal("1"),
        reference_value=None,
        quality=FeatureQuality.VALID,
        source_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        provenance="test",
    )
    assert evidence.reference_value is None
    assert evidence.window is None

"""Tests for ``app.technical_analysts.volatility.VolatilityAnalyst``."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.quality import FeatureQuality
from app.core.enums.technical_analysis import ReferenceComparison, TechnicalAnalysisDimension, TechnicalAnalystOutcome
from app.technical_analysts.volatility import VolatilityAnalyst
from tests.technical_analysts_support import make_snapshot, make_volatility, status


def _observation(result, dimension):
    matches = [o for o in result.observations if o.dimension is dimension]
    assert len(matches) == 1
    return matches[0]


def test_ratio_above_one() -> None:
    snapshot = make_snapshot(volatility=make_volatility(range_expansion_ratio=Decimal("1.5")))
    result = VolatilityAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.RANGE_EXPANSION_REFERENCE).value == ReferenceComparison.ABOVE_REFERENCE.value


def test_ratio_below_one() -> None:
    snapshot = make_snapshot(volatility=make_volatility(range_expansion_ratio=Decimal("0.5")))
    result = VolatilityAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.RANGE_EXPANSION_REFERENCE).value == ReferenceComparison.BELOW_REFERENCE.value


def test_ratio_exactly_one() -> None:
    snapshot = make_snapshot(volatility=make_volatility(range_expansion_ratio=Decimal("1")))
    result = VolatilityAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.RANGE_EXPANSION_REFERENCE).value == ReferenceComparison.AT_REFERENCE.value


def test_ratio_none_causes_abstention() -> None:
    snapshot = make_snapshot(volatility=make_volatility(range_expansion_ratio=None))
    result = VolatilityAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ABSTAINED
    assert result.quality is FeatureQuality.UNAVAILABLE


def test_partial_quality_propagates() -> None:
    snapshot = make_snapshot(volatility=make_volatility(range_expansion_ratio=Decimal("2"), block_status=status(FeatureQuality.PARTIAL, sample_count=3)))
    result = VolatilityAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ANALYZED
    assert result.quality is FeatureQuality.PARTIAL


def test_stale_quality_propagates() -> None:
    snapshot = make_snapshot(volatility=make_volatility(range_expansion_ratio=Decimal("2"), block_status=status(FeatureQuality.STALE, sample_count=3)))
    result = VolatilityAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ANALYZED
    assert result.quality is FeatureQuality.STALE


def test_unavailable_block_causes_abstention() -> None:
    snapshot = make_snapshot(volatility=make_volatility(block_status=status(FeatureQuality.UNAVAILABLE, sample_count=0), range_expansion_ratio=None, true_range=None, atr=None, rolling_range=None))
    result = VolatilityAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ABSTAINED
    assert result.observations == ()


def test_no_high_low_extreme_unusual_labels() -> None:
    snapshot = make_snapshot(volatility=make_volatility(range_expansion_ratio=Decimal("3")))
    result = VolatilityAnalyst().analyze(snapshot)
    forbidden = ("HIGH", "LOW", "EXTREME", "UNUSUAL")
    for observation in result.observations:
        for term in forbidden:
            assert term not in observation.value.upper()

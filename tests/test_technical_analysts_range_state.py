"""Tests for ``app.technical_analysts.range_state.RangeStateAnalyst``."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.quality import FeatureQuality
from app.core.enums.technical_analysis import BoundaryPosition, ReferenceComparison, TechnicalAnalysisDimension, TechnicalAnalystOutcome
from app.technical_analysts.range_state import RangeStateAnalyst
from tests.technical_analysts_support import make_range_state, make_snapshot, status


def _observation(result, dimension):
    matches = [o for o in result.observations if o.dimension is dimension]
    assert len(matches) == 1
    return matches[0]


def test_normalized_range_above_one() -> None:
    snapshot = make_snapshot(range_state=make_range_state(normalized_range=Decimal("2")))
    result = RangeStateAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.NORMALIZED_RANGE_REFERENCE).value == ReferenceComparison.ABOVE_REFERENCE.value


def test_normalized_range_below_one() -> None:
    snapshot = make_snapshot(range_state=make_range_state(normalized_range=Decimal("0.5")))
    result = RangeStateAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.NORMALIZED_RANGE_REFERENCE).value == ReferenceComparison.BELOW_REFERENCE.value


def test_normalized_range_exactly_one() -> None:
    snapshot = make_snapshot(range_state=make_range_state(normalized_range=Decimal("1")))
    result = RangeStateAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.NORMALIZED_RANGE_REFERENCE).value == ReferenceComparison.AT_REFERENCE.value


def test_normalized_range_none_omits_dimension() -> None:
    snapshot = make_snapshot(range_state=make_range_state(normalized_range=None))
    result = RangeStateAnalyst().analyze(snapshot)
    dims = [o.dimension for o in result.observations]
    assert TechnicalAnalysisDimension.NORMALIZED_RANGE_REFERENCE not in dims


def test_efficiency_at_minimum() -> None:
    snapshot = make_snapshot(range_state=make_range_state(directional_efficiency=Decimal("0")))
    result = RangeStateAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.DIRECTIONAL_EFFICIENCY_BOUNDARY).value == BoundaryPosition.AT_MINIMUM.value


def test_efficiency_at_maximum() -> None:
    snapshot = make_snapshot(range_state=make_range_state(directional_efficiency=Decimal("1")))
    result = RangeStateAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.DIRECTIONAL_EFFICIENCY_BOUNDARY).value == BoundaryPosition.AT_MAXIMUM.value


def test_efficiency_strictly_between_bounds() -> None:
    snapshot = make_snapshot(range_state=make_range_state(directional_efficiency=Decimal("0.5")))
    result = RangeStateAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.DIRECTIONAL_EFFICIENCY_BOUNDARY).value == BoundaryPosition.BETWEEN_BOUNDS.value


def test_efficiency_none_omits_dimension() -> None:
    snapshot = make_snapshot(range_state=make_range_state(directional_efficiency=None))
    result = RangeStateAnalyst().analyze(snapshot)
    dims = [o.dimension for o in result.observations]
    assert TechnicalAnalysisDimension.DIRECTIONAL_EFFICIENCY_BOUNDARY not in dims


def test_both_none_causes_abstention() -> None:
    snapshot = make_snapshot(range_state=make_range_state(normalized_range=None, directional_efficiency=None))
    result = RangeStateAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ABSTAINED
    assert result.observations == ()


def test_partial_quality_propagates() -> None:
    snapshot = make_snapshot(range_state=make_range_state(block_status=status(FeatureQuality.PARTIAL, sample_count=3)))
    result = RangeStateAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ANALYZED
    assert result.quality is FeatureQuality.PARTIAL


def test_stale_quality_propagates() -> None:
    snapshot = make_snapshot(range_state=make_range_state(block_status=status(FeatureQuality.STALE, sample_count=3)))
    result = RangeStateAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ANALYZED
    assert result.quality is FeatureQuality.STALE


def test_unavailable_block_causes_abstention() -> None:
    snapshot = make_snapshot(
        range_state=make_range_state(
            normalized_range=None, directional_efficiency=None, rolling_range=None,
            block_status=status(FeatureQuality.UNAVAILABLE, sample_count=0),
        )
    )
    result = RangeStateAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ABSTAINED
    assert result.observations == ()


def test_no_consolidation_ranging_trending_labels() -> None:
    snapshot = make_snapshot(range_state=make_range_state(normalized_range=Decimal("1.5"), directional_efficiency=Decimal("0.5")))
    result = RangeStateAnalyst().analyze(snapshot)
    forbidden = ("CONSOLIDAT", "RANGING", "TRENDING", "BREAKOUT", "COMPRESSION")
    for observation in result.observations:
        for term in forbidden:
            assert term not in observation.value.upper()

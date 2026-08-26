"""Tests for ``app.technical_analysts.candle_structure.CandleStructureAnalyst``."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.quality import FeatureQuality
from app.core.enums.technical_analysis import (
    BodyWickDominance,
    MidpointRelation,
    RangeSizeState,
    TechnicalAnalysisDimension,
    TechnicalAnalystOutcome,
    WickSideComparison,
)
from app.technical_analysts.candle_structure import CandleStructureAnalyst
from tests.technical_analysts_support import make_candle_structure, make_snapshot, status


def _observation(result, dimension):
    matches = [o for o in result.observations if o.dimension is dimension]
    assert len(matches) == 1
    return matches[0]


def test_zero_range() -> None:
    snapshot = make_snapshot(
        candle_structure=make_candle_structure(
            range_size=Decimal("0"), body_size=Decimal("0"), upper_wick=Decimal("0"), lower_wick=Decimal("0"),
            body_to_range_ratio=None, close_location_value=None,
        )
    )
    result = CandleStructureAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.RANGE_SIZE_STATE).value == RangeSizeState.ZERO_RANGE.value


def test_non_zero_range() -> None:
    snapshot = make_snapshot(candle_structure=make_candle_structure(range_size=Decimal("3")))
    result = CandleStructureAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.RANGE_SIZE_STATE).value == RangeSizeState.NON_ZERO_RANGE.value


def test_body_dominant() -> None:
    snapshot = make_snapshot(candle_structure=make_candle_structure(body_size=Decimal("5"), upper_wick=Decimal("1"), lower_wick=Decimal("1")))
    result = CandleStructureAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.BODY_WICK_DOMINANCE).value == BodyWickDominance.BODY_DOMINANT.value


def test_wick_dominant() -> None:
    snapshot = make_snapshot(candle_structure=make_candle_structure(body_size=Decimal("1"), upper_wick=Decimal("3"), lower_wick=Decimal("3")))
    result = CandleStructureAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.BODY_WICK_DOMINANCE).value == BodyWickDominance.WICK_DOMINANT.value


def test_body_equals_wick_sum() -> None:
    snapshot = make_snapshot(candle_structure=make_candle_structure(body_size=Decimal("2"), upper_wick=Decimal("1"), lower_wick=Decimal("1")))
    result = CandleStructureAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.BODY_WICK_DOMINANCE).value == BodyWickDominance.EQUAL.value


def test_upper_wick_larger() -> None:
    snapshot = make_snapshot(candle_structure=make_candle_structure(upper_wick=Decimal("3"), lower_wick=Decimal("1")))
    result = CandleStructureAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.WICK_SIDE_COMPARISON).value == WickSideComparison.UPPER_WICK_LARGER.value


def test_lower_wick_larger() -> None:
    snapshot = make_snapshot(candle_structure=make_candle_structure(upper_wick=Decimal("1"), lower_wick=Decimal("3")))
    result = CandleStructureAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.WICK_SIDE_COMPARISON).value == WickSideComparison.LOWER_WICK_LARGER.value


def test_equal_wicks() -> None:
    snapshot = make_snapshot(candle_structure=make_candle_structure(upper_wick=Decimal("2"), lower_wick=Decimal("2")))
    result = CandleStructureAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.WICK_SIDE_COMPARISON).value == WickSideComparison.EQUAL.value


def test_close_location_above_midpoint() -> None:
    snapshot = make_snapshot(candle_structure=make_candle_structure(close_location_value=Decimal("0.75")))
    result = CandleStructureAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.CLOSE_LOCATION_RELATION).value == MidpointRelation.ABOVE_MIDPOINT.value


def test_close_location_below_midpoint() -> None:
    snapshot = make_snapshot(candle_structure=make_candle_structure(close_location_value=Decimal("0.25")))
    result = CandleStructureAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.CLOSE_LOCATION_RELATION).value == MidpointRelation.BELOW_MIDPOINT.value


def test_close_location_exactly_midpoint() -> None:
    snapshot = make_snapshot(candle_structure=make_candle_structure(close_location_value=Decimal("0.5")))
    result = CandleStructureAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.CLOSE_LOCATION_RELATION).value == MidpointRelation.AT_MIDPOINT.value


def test_close_location_none_omits_dimension() -> None:
    snapshot = make_snapshot(candle_structure=make_candle_structure(close_location_value=None))
    result = CandleStructureAnalyst().analyze(snapshot)
    dims = [o.dimension for o in result.observations]
    assert TechnicalAnalysisDimension.CLOSE_LOCATION_RELATION not in dims


def test_partial_quality_propagates() -> None:
    snapshot = make_snapshot(candle_structure=make_candle_structure(block_status=status(FeatureQuality.PARTIAL, sample_count=1)))
    result = CandleStructureAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ANALYZED
    assert result.quality is FeatureQuality.PARTIAL


def test_stale_quality_propagates() -> None:
    snapshot = make_snapshot(candle_structure=make_candle_structure(block_status=status(FeatureQuality.STALE, sample_count=1)))
    result = CandleStructureAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ANALYZED
    assert result.quality is FeatureQuality.STALE


def test_unavailable_block_causes_abstention() -> None:
    snapshot = make_snapshot(
        candle_structure=make_candle_structure(
            candle_time=None, body_size=None, upper_wick=None, lower_wick=None, range_size=None,
            body_to_range_ratio=None, close_location_value=None, block_status=status(FeatureQuality.UNAVAILABLE, sample_count=0),
        )
    )
    result = CandleStructureAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ABSTAINED
    assert result.observations == ()


def test_no_named_candle_patterns() -> None:
    snapshot = make_snapshot(candle_structure=make_candle_structure())
    result = CandleStructureAnalyst().analyze(snapshot)
    forbidden = ("HAMMER", "DOJI", "ENGULFING", "REVERSAL", "CONTINUATION")
    for observation in result.observations:
        for term in forbidden:
            assert term not in observation.value.upper()

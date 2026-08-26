"""Tests for ``app.technical_analysts.trend.TrendAnalyst``."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.quality import FeatureQuality
from app.core.enums.technical_analysis import (
    StructuralSequenceBalance,
    TechnicalAgreementVerdict,
    TechnicalAnalysisDimension,
    TechnicalAnalystOutcome,
    TrendDirection,
)
from app.technical_analysts.trend import TrendAnalyst
from tests.technical_analysts_support import make_snapshot, make_trend, status


def _observation(result, dimension):
    matches = [o for o in result.observations if o.dimension is dimension]
    assert len(matches) == 1, f"expected exactly one {dimension} observation, got {len(matches)}"
    return matches[0]


def test_positive_return_is_upward() -> None:
    snapshot = make_snapshot(trend=make_trend(return_pct=Decimal("5")))
    result = TrendAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.RETURN_DIRECTION).value == TrendDirection.UPWARD.value


def test_negative_return_is_downward() -> None:
    snapshot = make_snapshot(trend=make_trend(return_pct=Decimal("-5")))
    result = TrendAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.RETURN_DIRECTION).value == TrendDirection.DOWNWARD.value


def test_zero_return_is_flat() -> None:
    snapshot = make_snapshot(trend=make_trend(return_pct=Decimal("0")))
    result = TrendAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.RETURN_DIRECTION).value == TrendDirection.FLAT.value


def test_positive_slope_is_upward() -> None:
    snapshot = make_snapshot(trend=make_trend(slope=Decimal("0.5")))
    result = TrendAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.SLOPE_DIRECTION).value == TrendDirection.UPWARD.value


def test_negative_slope_is_downward() -> None:
    snapshot = make_snapshot(trend=make_trend(slope=Decimal("-0.5")))
    result = TrendAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.SLOPE_DIRECTION).value == TrendDirection.DOWNWARD.value


def test_zero_slope_is_flat() -> None:
    snapshot = make_snapshot(trend=make_trend(slope=Decimal("0")))
    result = TrendAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.SLOPE_DIRECTION).value == TrendDirection.FLAT.value


def test_upward_structural_sequence_balance() -> None:
    snapshot = make_snapshot(trend=make_trend(higher_high_count=3, higher_low_count=2, lower_high_count=0, lower_low_count=1))
    result = TrendAnalyst().analyze(snapshot)
    observation = _observation(result, TechnicalAnalysisDimension.STRUCTURAL_SEQUENCE_BALANCE)
    assert observation.value == StructuralSequenceBalance.UPWARD_STRUCTURE.value
    assert observation.evidence_refs == (0, 1, 2, 3) or len(observation.evidence_refs) == 4


def test_downward_structural_sequence_balance() -> None:
    snapshot = make_snapshot(trend=make_trend(higher_high_count=0, higher_low_count=1, lower_high_count=3, lower_low_count=2))
    result = TrendAnalyst().analyze(snapshot)
    observation = _observation(result, TechnicalAnalysisDimension.STRUCTURAL_SEQUENCE_BALANCE)
    assert observation.value == StructuralSequenceBalance.DOWNWARD_STRUCTURE.value


def test_mixed_structural_sequence_balance_on_exact_tie() -> None:
    snapshot = make_snapshot(trend=make_trend(higher_high_count=2, higher_low_count=1, lower_high_count=1, lower_low_count=2))
    result = TrendAnalyst().analyze(snapshot)
    observation = _observation(result, TechnicalAnalysisDimension.STRUCTURAL_SEQUENCE_BALANCE)
    assert observation.value == StructuralSequenceBalance.MIXED_STRUCTURE.value


def test_trend_primitive_agreement_when_both_upward() -> None:
    snapshot = make_snapshot(trend=make_trend(return_pct=Decimal("5"), slope=Decimal("1")))
    result = TrendAnalyst().analyze(snapshot)
    observation = _observation(result, TechnicalAnalysisDimension.TREND_PRIMITIVE_AGREEMENT)
    assert observation.value == TechnicalAgreementVerdict.ALL_AGREE.value


def test_trend_primitive_conflict_when_directions_differ() -> None:
    snapshot = make_snapshot(trend=make_trend(return_pct=Decimal("5"), slope=Decimal("-1")))
    result = TrendAnalyst().analyze(snapshot)
    observation = _observation(result, TechnicalAnalysisDimension.TREND_PRIMITIVE_AGREEMENT)
    assert observation.value == TechnicalAgreementVerdict.MIXED.value


def test_flat_primitive_yields_insufficient_agreement() -> None:
    snapshot = make_snapshot(trend=make_trend(return_pct=Decimal("0"), slope=Decimal("1")))
    result = TrendAnalyst().analyze(snapshot)
    observation = _observation(result, TechnicalAnalysisDimension.TREND_PRIMITIVE_AGREEMENT)
    assert observation.value == TechnicalAgreementVerdict.INSUFFICIENT_DATA.value


def test_both_flat_yields_insufficient_agreement() -> None:
    snapshot = make_snapshot(trend=make_trend(return_pct=Decimal("0"), slope=Decimal("0")))
    result = TrendAnalyst().analyze(snapshot)
    observation = _observation(result, TechnicalAnalysisDimension.TREND_PRIMITIVE_AGREEMENT)
    assert observation.value == TechnicalAgreementVerdict.INSUFFICIENT_DATA.value


def test_missing_slope_primitive_still_reports_agreement_as_insufficient() -> None:
    snapshot = make_snapshot(trend=make_trend(return_pct=Decimal("5"), slope=None))
    result = TrendAnalyst().analyze(snapshot)
    observation = _observation(result, TechnicalAnalysisDimension.TREND_PRIMITIVE_AGREEMENT)
    assert observation.value == TechnicalAgreementVerdict.INSUFFICIENT_DATA.value
    assert result.observations  # still ANALYZED, return direction present


def test_missing_both_primitives_omits_agreement_dimension() -> None:
    snapshot = make_snapshot(trend=make_trend(return_pct=None, slope=None))
    result = TrendAnalyst().analyze(snapshot)
    dims = [o.dimension for o in result.observations]
    assert TechnicalAnalysisDimension.TREND_PRIMITIVE_AGREEMENT not in dims


def test_directional_persistence_exact_value_preserved_in_evidence() -> None:
    persistence = Decimal("2") / Decimal("3")
    snapshot = make_snapshot(trend=make_trend(return_pct=Decimal("5"), directional_persistence=persistence))
    result = TrendAnalyst().analyze(snapshot)
    observation = _observation(result, TechnicalAnalysisDimension.DIRECTIONAL_PERSISTENCE)
    evidence = result.evidence[observation.evidence_refs[0]]
    assert evidence.observed_value == str(persistence)
    assert evidence.feature_name == "trend.directional_persistence"


def test_directional_persistence_between_bounds() -> None:
    snapshot = make_snapshot(trend=make_trend(directional_persistence=Decimal("0.5")))
    result = TrendAnalyst().analyze(snapshot)
    observation = _observation(result, TechnicalAnalysisDimension.DIRECTIONAL_PERSISTENCE)
    assert observation.value == "BETWEEN_BOUNDS"


def test_directional_persistence_at_minimum() -> None:
    snapshot = make_snapshot(trend=make_trend(directional_persistence=Decimal("0")))
    result = TrendAnalyst().analyze(snapshot)
    observation = _observation(result, TechnicalAnalysisDimension.DIRECTIONAL_PERSISTENCE)
    assert observation.value == "AT_MINIMUM"


def test_directional_persistence_at_maximum() -> None:
    snapshot = make_snapshot(trend=make_trend(directional_persistence=Decimal("1")))
    result = TrendAnalyst().analyze(snapshot)
    observation = _observation(result, TechnicalAnalysisDimension.DIRECTIONAL_PERSISTENCE)
    assert observation.value == "AT_MAXIMUM"


def test_directional_persistence_never_labeled_strength() -> None:
    snapshot = make_snapshot(trend=make_trend(directional_persistence=Decimal("0.9")))
    result = TrendAnalyst().analyze(snapshot)
    observation = _observation(result, TechnicalAnalysisDimension.DIRECTIONAL_PERSISTENCE)
    for forbidden in ("HIGH", "LOW", "STRONG", "WEAK"):
        assert forbidden not in observation.value


def test_missing_directional_persistence_omits_dimension() -> None:
    snapshot = make_snapshot(trend=make_trend(directional_persistence=None))
    result = TrendAnalyst().analyze(snapshot)
    dims = [o.dimension for o in result.observations]
    assert TechnicalAnalysisDimension.DIRECTIONAL_PERSISTENCE not in dims


def test_partial_quality_propagates() -> None:
    snapshot = make_snapshot(trend=make_trend(return_pct=Decimal("1"), block_status=status(FeatureQuality.PARTIAL, sample_count=3)))
    result = TrendAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ANALYZED
    assert result.quality is FeatureQuality.PARTIAL
    assert all(o.quality is FeatureQuality.PARTIAL for o in result.observations)


def test_stale_quality_propagates() -> None:
    snapshot = make_snapshot(trend=make_trend(return_pct=Decimal("1"), block_status=status(FeatureQuality.STALE, sample_count=3)))
    result = TrendAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ANALYZED
    assert result.quality is FeatureQuality.STALE


def test_unavailable_block_causes_abstention() -> None:
    snapshot = make_snapshot(trend=make_trend(block_status=status(FeatureQuality.UNAVAILABLE, sample_count=0)))
    result = TrendAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ABSTAINED
    assert result.quality is FeatureQuality.UNAVAILABLE
    assert result.observations == ()
    assert result.abstention_reasons


def test_no_uptrend_downtrend_or_bullish_bearish_vocabulary() -> None:
    snapshot = make_snapshot(trend=make_trend(return_pct=Decimal("5"), slope=Decimal("5"), directional_persistence=Decimal("1")))
    result = TrendAnalyst().analyze(snapshot)
    forbidden = ("UPTREND", "DOWNTREND", "BULLISH", "BEARISH", "STRENGTH")
    for observation in result.observations:
        for term in forbidden:
            assert term not in observation.value.upper()

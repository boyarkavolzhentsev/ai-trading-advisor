"""Tests for ``app.technical_analysts.momentum.MomentumAnalyst``."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.quality import FeatureQuality
from app.core.enums.technical_analysis import MidpointRelation, ROCSign, TechnicalAgreementVerdict, TechnicalAnalysisDimension, TechnicalAnalystOutcome
from app.technical_analysts.momentum import MomentumAnalyst
from tests.technical_analysts_support import make_momentum, make_snapshot, status


def _observation(result, dimension):
    matches = [o for o in result.observations if o.dimension is dimension]
    assert len(matches) == 1
    return matches[0]


def test_positive_roc() -> None:
    snapshot = make_snapshot(momentum=make_momentum(roc=Decimal("2")))
    result = MomentumAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.ROC_SIGN).value == ROCSign.POSITIVE.value


def test_negative_roc() -> None:
    snapshot = make_snapshot(momentum=make_momentum(roc=Decimal("-2")))
    result = MomentumAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.ROC_SIGN).value == ROCSign.NEGATIVE.value


def test_zero_roc() -> None:
    snapshot = make_snapshot(momentum=make_momentum(roc=Decimal("0")))
    result = MomentumAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.ROC_SIGN).value == ROCSign.ZERO.value


def test_rsi_above_fifty() -> None:
    snapshot = make_snapshot(momentum=make_momentum(rsi=Decimal("70")))
    result = MomentumAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.RSI_MIDPOINT_RELATION).value == MidpointRelation.ABOVE_MIDPOINT.value


def test_rsi_below_fifty() -> None:
    snapshot = make_snapshot(momentum=make_momentum(rsi=Decimal("30")))
    result = MomentumAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.RSI_MIDPOINT_RELATION).value == MidpointRelation.BELOW_MIDPOINT.value


def test_rsi_exactly_fifty() -> None:
    snapshot = make_snapshot(momentum=make_momentum(rsi=Decimal("50")))
    result = MomentumAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.RSI_MIDPOINT_RELATION).value == MidpointRelation.AT_MIDPOINT.value


def test_agreement_when_both_upward() -> None:
    snapshot = make_snapshot(momentum=make_momentum(roc=Decimal("2"), rsi=Decimal("70")))
    result = MomentumAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.MOMENTUM_PRIMITIVE_AGREEMENT).value == TechnicalAgreementVerdict.ALL_AGREE.value


def test_agreement_when_both_downward() -> None:
    snapshot = make_snapshot(momentum=make_momentum(roc=Decimal("-2"), rsi=Decimal("30")))
    result = MomentumAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.MOMENTUM_PRIMITIVE_AGREEMENT).value == TechnicalAgreementVerdict.ALL_AGREE.value


def test_conflict_when_opposite_sides() -> None:
    snapshot = make_snapshot(momentum=make_momentum(roc=Decimal("2"), rsi=Decimal("30")))
    result = MomentumAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.MOMENTUM_PRIMITIVE_AGREEMENT).value == TechnicalAgreementVerdict.MIXED.value


def test_zero_roc_yields_insufficient_agreement() -> None:
    snapshot = make_snapshot(momentum=make_momentum(roc=Decimal("0"), rsi=Decimal("70")))
    result = MomentumAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.MOMENTUM_PRIMITIVE_AGREEMENT).value == TechnicalAgreementVerdict.INSUFFICIENT_DATA.value


def test_midpoint_rsi_yields_insufficient_agreement() -> None:
    snapshot = make_snapshot(momentum=make_momentum(roc=Decimal("2"), rsi=Decimal("50")))
    result = MomentumAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.MOMENTUM_PRIMITIVE_AGREEMENT).value == TechnicalAgreementVerdict.INSUFFICIENT_DATA.value


def test_missing_rsi_yields_insufficient_agreement() -> None:
    snapshot = make_snapshot(momentum=make_momentum(roc=Decimal("2"), rsi=None))
    result = MomentumAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.MOMENTUM_PRIMITIVE_AGREEMENT).value == TechnicalAgreementVerdict.INSUFFICIENT_DATA.value


def test_missing_both_omits_agreement_dimension() -> None:
    snapshot = make_snapshot(momentum=make_momentum(roc=None, rsi=None))
    result = MomentumAnalyst().analyze(snapshot)
    dims = [o.dimension for o in result.observations]
    assert TechnicalAnalysisDimension.MOMENTUM_PRIMITIVE_AGREEMENT not in dims


def test_partial_quality_propagates() -> None:
    snapshot = make_snapshot(momentum=make_momentum(roc=Decimal("1"), block_status=status(FeatureQuality.PARTIAL, sample_count=3)))
    result = MomentumAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ANALYZED
    assert result.quality is FeatureQuality.PARTIAL


def test_stale_quality_propagates() -> None:
    snapshot = make_snapshot(momentum=make_momentum(roc=Decimal("1"), block_status=status(FeatureQuality.STALE, sample_count=3)))
    result = MomentumAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ANALYZED
    assert result.quality is FeatureQuality.STALE


def test_unavailable_block_causes_abstention() -> None:
    snapshot = make_snapshot(momentum=make_momentum(roc=None, rsi=None, block_status=status(FeatureQuality.UNAVAILABLE, sample_count=0)))
    result = MomentumAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ABSTAINED
    assert result.observations == ()


def test_no_seventy_thirty_overbought_oversold_behavior() -> None:
    for rsi in (Decimal("69"), Decimal("71"), Decimal("29"), Decimal("31")):
        snapshot = make_snapshot(momentum=make_momentum(rsi=rsi))
        result = MomentumAnalyst().analyze(snapshot)
        observation = _observation(result, TechnicalAnalysisDimension.RSI_MIDPOINT_RELATION)
        assert observation.value in {MidpointRelation.ABOVE_MIDPOINT.value, MidpointRelation.BELOW_MIDPOINT.value}
        for observation in result.observations:
            assert "OVERBOUGHT" not in observation.value.upper()
            assert "OVERSOLD" not in observation.value.upper()

"""Tests for app.core.models.flow_analysis_result: FlowAnalysisObservation/FlowAnalysisResult."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.core.enums.flow_analysis import AnalysisDimension, AnalystOutcome, AnalystType, TakerFlowPressure
from app.core.enums.instrument import ContractType
from app.core.enums.quality import FeatureQuality
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.flow_analysis_result import FlowAnalysisObservation, FlowAnalysisResult
from app.core.models.flow_evidence import FlowEvidence

NOW = datetime(2026, 1, 1, tzinfo=UTC)
WINDOW = AnalyticsWindow(label="1m", duration=timedelta(minutes=1))


def _evidence() -> FlowEvidence:
    return FlowEvidence(
        feature_name="taker_flow.delta",
        window="1m",
        observed_value="1",
        quality=FeatureQuality.VALID,
        source_timestamp=NOW,
        provenance="test",
    )


def _observation(*, evidence_refs: tuple[int, ...] = (0,)) -> FlowAnalysisObservation:
    return FlowAnalysisObservation(
        dimension=AnalysisDimension.DIRECTIONAL_PRESSURE,
        window="1m",
        value=TakerFlowPressure.BUY_DOMINANT.value,
        quality=FeatureQuality.VALID,
        evidence_refs=evidence_refs,
    )


def _analyzed(**overrides: object) -> FlowAnalysisResult:
    fields = dict(
        analyst_type=AnalystType.TAKER_FLOW,
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        observation_time=NOW,
        windows=(WINDOW,),
        status=AnalystOutcome.ANALYZED,
        observations=(_observation(),),
        evidence=(_evidence(),),
        quality=FeatureQuality.VALID,
    )
    fields.update(overrides)
    return FlowAnalysisResult(**fields)


def test_valid_analyzed_result_roundtrips() -> None:
    result = _analyzed()
    restored = FlowAnalysisResult.model_validate(result.model_dump())
    assert restored == result


def test_observation_requires_at_least_one_evidence_ref() -> None:
    with pytest.raises(ValidationError):
        FlowAnalysisObservation(
            dimension=AnalysisDimension.DIRECTIONAL_PRESSURE,
            value=TakerFlowPressure.BUY_DOMINANT.value,
            quality=FeatureQuality.VALID,
            evidence_refs=(),
        )


def test_invalid_evidence_reference_rejected() -> None:
    with pytest.raises(ValidationError):
        _analyzed(observations=(_observation(evidence_refs=(5,)),))


def test_negative_evidence_reference_rejected() -> None:
    with pytest.raises(ValidationError):
        _analyzed(observations=(_observation(evidence_refs=(-1,)),))


def test_abstained_result_must_have_no_observations() -> None:
    with pytest.raises(ValidationError):
        FlowAnalysisResult(
            analyst_type=AnalystType.TAKER_FLOW,
            symbol="BTCUSDT",
            contract_type=ContractType.PERPETUAL,
            observation_time=NOW,
            windows=(WINDOW,),
            status=AnalystOutcome.ABSTAINED,
            observations=(_observation(),),
            evidence=(_evidence(),),
            quality=FeatureQuality.UNAVAILABLE,
            abstention_reasons=("no data",),
        )


def test_abstained_result_must_have_reasons() -> None:
    with pytest.raises(ValidationError):
        FlowAnalysisResult(
            analyst_type=AnalystType.TAKER_FLOW,
            symbol="BTCUSDT",
            contract_type=ContractType.PERPETUAL,
            observation_time=NOW,
            windows=(WINDOW,),
            status=AnalystOutcome.ABSTAINED,
            quality=FeatureQuality.UNAVAILABLE,
        )


def test_abstained_result_must_have_unavailable_quality() -> None:
    with pytest.raises(ValidationError):
        FlowAnalysisResult(
            analyst_type=AnalystType.TAKER_FLOW,
            symbol="BTCUSDT",
            contract_type=ContractType.PERPETUAL,
            observation_time=NOW,
            windows=(WINDOW,),
            status=AnalystOutcome.ABSTAINED,
            quality=FeatureQuality.VALID,
            abstention_reasons=("no data",),
        )


def test_valid_abstained_result() -> None:
    result = FlowAnalysisResult(
        analyst_type=AnalystType.TAKER_FLOW,
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        observation_time=NOW,
        windows=(WINDOW,),
        status=AnalystOutcome.ABSTAINED,
        quality=FeatureQuality.UNAVAILABLE,
        abstention_reasons=("no data",),
    )
    assert result.observations == ()
    assert result.evidence == ()


def test_analyzed_result_must_not_have_abstention_reasons() -> None:
    with pytest.raises(ValidationError):
        _analyzed(abstention_reasons=("should not be here",))


def test_result_is_frozen() -> None:
    result = _analyzed()
    with pytest.raises(ValidationError):
        result.quality = FeatureQuality.STALE  # type: ignore[misc]


def test_no_trade_direction_field_anywhere() -> None:
    forbidden = {"direction", "confidence", "stop_loss", "take_profit", "position_size", "risk_percent", "entry", "target"}
    assert forbidden.isdisjoint(FlowAnalysisResult.model_fields)
    assert forbidden.isdisjoint(FlowAnalysisObservation.model_fields)
    assert forbidden.isdisjoint(FlowEvidence.model_fields)


def test_no_free_text_summary_field() -> None:
    assert "summary" not in FlowAnalysisResult.model_fields

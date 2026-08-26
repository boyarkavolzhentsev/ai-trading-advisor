"""Tests for the Stage 3B model family: ``TechnicalEvidence``,
``TechnicalAnalysisObservation``, ``TechnicalAnalysisResult``."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.enums.quality import FeatureQuality
from app.core.enums.technical_analysis import TechnicalAnalysisDimension, TechnicalAnalystOutcome, TechnicalAnalystType
from app.core.models.technical_analysis_result import TechnicalAnalysisObservation, TechnicalAnalysisResult
from app.core.models.technical_evidence import TechnicalEvidence

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def _evidence(**overrides) -> TechnicalEvidence:
    defaults = dict(
        feature_name="trend.return_pct",
        observed_value="1.5",
        reference_value="0",
        quality=FeatureQuality.VALID,
        source_timestamp=NOW,
        provenance="test",
    )
    defaults.update(overrides)
    return TechnicalEvidence(**defaults)


def _observation(**overrides) -> TechnicalAnalysisObservation:
    defaults = dict(
        dimension=TechnicalAnalysisDimension.RETURN_DIRECTION,
        value="UPWARD",
        quality=FeatureQuality.VALID,
        evidence_refs=(0,),
    )
    defaults.update(overrides)
    return TechnicalAnalysisObservation(**defaults)


def _analyzed_result(**overrides) -> TechnicalAnalysisResult:
    defaults = dict(
        analyst_type=TechnicalAnalystType.TREND,
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        timeframe=Timeframe.M1,
        observation_time=NOW,
        last_closed_candle_time=NOW,
        status=TechnicalAnalystOutcome.ANALYZED,
        observations=(_observation(),),
        evidence=(_evidence(),),
        quality=FeatureQuality.VALID,
        provenance={"trend": "test"},
    )
    defaults.update(overrides)
    return TechnicalAnalysisResult(**defaults)


def test_technical_evidence_serialization_round_trip() -> None:
    evidence = _evidence()
    payload = evidence.model_dump()
    restored = TechnicalEvidence(**payload)
    assert restored == evidence


def test_technical_evidence_requires_nonempty_feature_name() -> None:
    with pytest.raises(ValidationError):
        _evidence(feature_name="")


def test_technical_analysis_observation_serialization_round_trip() -> None:
    observation = _observation(subject="20")
    payload = observation.model_dump()
    restored = TechnicalAnalysisObservation(**payload)
    assert restored == observation


def test_technical_analysis_observation_requires_at_least_one_evidence_ref() -> None:
    with pytest.raises(ValidationError):
        _observation(evidence_refs=())


def test_technical_analysis_result_serialization_round_trip() -> None:
    result = _analyzed_result()
    payload = result.model_dump()
    restored = TechnicalAnalysisResult(**payload)
    assert restored == result


def test_timeframe_is_preserved() -> None:
    result = _analyzed_result(timeframe=Timeframe.H4)
    assert result.timeframe is Timeframe.H4


def test_last_closed_candle_time_is_preserved() -> None:
    result = _analyzed_result(last_closed_candle_time=NOW)
    assert result.last_closed_candle_time == NOW


def test_last_closed_candle_time_may_be_none() -> None:
    result = _analyzed_result(last_closed_candle_time=None)
    assert result.last_closed_candle_time is None


def test_provenance_is_preserved() -> None:
    result = _analyzed_result(provenance={"trend": "technical_engine"})
    assert result.provenance == {"trend": "technical_engine"}


def test_valid_evidence_refs_accepted() -> None:
    result = _analyzed_result(
        evidence=(_evidence(), _evidence(feature_name="trend.slope")),
        observations=(_observation(evidence_refs=(0, 1)),),
    )
    assert result.observations[0].evidence_refs == (0, 1)


def test_out_of_range_evidence_ref_rejected() -> None:
    with pytest.raises(ValidationError):
        _analyzed_result(observations=(_observation(evidence_refs=(5,)),))


def test_negative_evidence_ref_rejected() -> None:
    with pytest.raises(ValidationError):
        _analyzed_result(observations=(_observation(evidence_refs=(-1,)),))


def test_analyzed_with_abstention_reasons_rejected() -> None:
    with pytest.raises(ValidationError):
        _analyzed_result(abstention_reasons=("should not be here",))


def test_abstained_must_have_no_observations() -> None:
    with pytest.raises(ValidationError):
        TechnicalAnalysisResult(
            analyst_type=TechnicalAnalystType.TREND,
            symbol="BTCUSDT",
            contract_type=ContractType.PERPETUAL,
            timeframe=Timeframe.M1,
            observation_time=NOW,
            status=TechnicalAnalystOutcome.ABSTAINED,
            observations=(_observation(),),
            evidence=(_evidence(),),
            quality=FeatureQuality.UNAVAILABLE,
            abstention_reasons=("no data",),
        )


def test_abstained_requires_at_least_one_reason() -> None:
    with pytest.raises(ValidationError):
        TechnicalAnalysisResult(
            analyst_type=TechnicalAnalystType.TREND,
            symbol="BTCUSDT",
            contract_type=ContractType.PERPETUAL,
            timeframe=Timeframe.M1,
            observation_time=NOW,
            status=TechnicalAnalystOutcome.ABSTAINED,
            quality=FeatureQuality.UNAVAILABLE,
        )


def test_abstained_must_have_unavailable_quality() -> None:
    with pytest.raises(ValidationError):
        TechnicalAnalysisResult(
            analyst_type=TechnicalAnalystType.TREND,
            symbol="BTCUSDT",
            contract_type=ContractType.PERPETUAL,
            timeframe=Timeframe.M1,
            observation_time=NOW,
            status=TechnicalAnalystOutcome.ABSTAINED,
            quality=FeatureQuality.PARTIAL,
            abstention_reasons=("no data",),
        )


def test_abstained_consistent_result_accepted() -> None:
    result = TechnicalAnalysisResult(
        analyst_type=TechnicalAnalystType.TREND,
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        timeframe=Timeframe.M1,
        observation_time=NOW,
        status=TechnicalAnalystOutcome.ABSTAINED,
        quality=FeatureQuality.UNAVAILABLE,
        abstention_reasons=("no usable trend evidence available",),
    )
    assert result.status is TechnicalAnalystOutcome.ABSTAINED
    assert result.observations == ()


def test_results_are_frozen() -> None:
    result = _analyzed_result()
    with pytest.raises(ValidationError):
        result.quality = FeatureQuality.PARTIAL

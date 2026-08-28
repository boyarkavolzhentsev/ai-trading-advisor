"""Stage 4F shared output models: schema, scope validation, evidence-ref
bounds, ANALYZED/ABSTAINED invariants, immutability.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.core.enums.external_intelligence_analysis import (
    ExternalIntelligenceAnalystType,
    ExternalIntelligenceDimension,
    ExternalIntelligenceOutcome,
)
from app.core.enums.quality import FeatureQuality
from app.core.models.external_intelligence_analysis_result import (
    ExternalIntelligenceAnalysisObservation,
    ExternalIntelligenceAnalysisResult,
)
from app.core.models.external_intelligence_evidence import ExternalIntelligenceEvidence


def _evidence(now: datetime, **overrides: object) -> ExternalIntelligenceEvidence:
    fields: dict[str, object] = {
        "feature_name": "economic_event.actual_vs_forecast",
        "observed_value": "3.2",
        "reference_value": "3.0",
        "quality": FeatureQuality.VALID,
        "source_timestamp": now,
        "source_provider": "tradingeconomics",
        "source_record_id": "cpi-2026-01",
        "source_received_at": now,
        "provenance": "app.macro:tradingeconomics",
    }
    fields.update(overrides)
    return ExternalIntelligenceEvidence(**fields)


def _observation(**overrides: object) -> ExternalIntelligenceAnalysisObservation:
    fields: dict[str, object] = {
        "dimension": ExternalIntelligenceDimension.SURPRISE,
        "value": "ABOVE_FORECAST",
        "quality": FeatureQuality.VALID,
        "evidence_refs": (0,),
    }
    fields.update(overrides)
    return ExternalIntelligenceAnalysisObservation(**fields)


def _result(now: datetime, **overrides: object) -> ExternalIntelligenceAnalysisResult:
    fields: dict[str, object] = {
        "analyst_type": ExternalIntelligenceAnalystType.MACRO_EVENT,
        "currency": "USD",
        "analysis_time": now,
        "status": ExternalIntelligenceOutcome.ANALYZED,
        "observations": (_observation(),),
        "evidence": (_evidence(now),),
        "quality": FeatureQuality.VALID,
    }
    fields.update(overrides)
    return ExternalIntelligenceAnalysisResult(**fields)


# --- Evidence schema ---


def test_evidence_required_fields(now: datetime) -> None:
    evidence = _evidence(now)
    assert evidence.source_provider == "tradingeconomics"
    assert evidence.source_record_id == "cpi-2026-01"
    assert evidence.source_received_at == now


def test_evidence_reference_value_optional(now: datetime) -> None:
    evidence = _evidence(now, reference_value=None)
    assert evidence.reference_value is None


def test_evidence_is_frozen(now: datetime) -> None:
    evidence = _evidence(now)
    with pytest.raises(ValidationError):
        evidence.observed_value = "changed"  # type: ignore[misc]


def test_evidence_forbids_unknown_fields(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _evidence(now, unexpected_field="value")


# --- Observation schema ---


def test_observation_requires_at_least_one_evidence_ref() -> None:
    with pytest.raises(ValidationError):
        _observation(evidence_refs=())


def test_observation_subject_optional() -> None:
    observation = _observation()
    assert observation.subject is None


def test_observation_is_frozen() -> None:
    observation = _observation()
    with pytest.raises(ValidationError):
        observation.value = "CHANGED"  # type: ignore[misc]


# --- Scope validation ---


def test_macro_event_result_requires_currency(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _result(now, currency=None)


def test_macro_event_result_forbids_symbol_asset_network(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _result(now, symbol="BTCUSDT")
    with pytest.raises(ValidationError):
        _result(now, asset="BTC")
    with pytest.raises(ValidationError):
        _result(now, network="bitcoin")


def test_rates_yield_result_requires_currency(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _result(now, analyst_type=ExternalIntelligenceAnalystType.RATES_YIELD, currency=None)


def test_news_sentiment_result_requires_symbol(now: datetime) -> None:
    result = _result(
        now,
        analyst_type=ExternalIntelligenceAnalystType.NEWS_SENTIMENT,
        currency=None,
        symbol="BTCUSDT",
    )
    assert result.symbol == "BTCUSDT"
    with pytest.raises(ValidationError):
        _result(now, analyst_type=ExternalIntelligenceAnalystType.NEWS_SENTIMENT, currency=None)


def test_news_sentiment_result_forbids_currency_asset_network(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _result(
            now,
            analyst_type=ExternalIntelligenceAnalystType.NEWS_SENTIMENT,
            symbol="BTCUSDT",
            currency="USD",
        )


def test_on_chain_result_requires_asset_and_network(now: datetime) -> None:
    result = _result(
        now,
        analyst_type=ExternalIntelligenceAnalystType.ON_CHAIN,
        currency=None,
        asset="BTC",
        network="bitcoin",
    )
    assert result.asset == "BTC"
    assert result.network == "bitcoin"
    with pytest.raises(ValidationError):
        _result(now, analyst_type=ExternalIntelligenceAnalystType.ON_CHAIN, currency=None, asset="BTC")
    with pytest.raises(ValidationError):
        _result(now, analyst_type=ExternalIntelligenceAnalystType.ON_CHAIN, currency=None, network="bitcoin")


def test_on_chain_result_forbids_currency_and_symbol(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _result(
            now,
            analyst_type=ExternalIntelligenceAnalystType.ON_CHAIN,
            asset="BTC",
            network="bitcoin",
            currency="USD",
        )


# --- Evidence-ref bounds ---


def test_evidence_ref_out_of_bounds_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _result(now, observations=(_observation(evidence_refs=(5,)),))


def test_evidence_ref_negative_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _result(now, observations=(_observation(evidence_refs=(-1,)),))


def test_evidence_ref_valid_index_is_accepted(now: datetime) -> None:
    result = _result(now)
    assert result.observations[0].evidence_refs == (0,)


# --- ANALYZED/ABSTAINED invariants ---


def test_abstained_result_must_have_no_observations(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _result(
            now,
            status=ExternalIntelligenceOutcome.ABSTAINED,
            quality=FeatureQuality.UNAVAILABLE,
            abstention_reasons=("no data",),
        )


def test_abstained_result_requires_abstention_reason(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _result(
            now,
            status=ExternalIntelligenceOutcome.ABSTAINED,
            observations=(),
            quality=FeatureQuality.UNAVAILABLE,
        )


def test_abstained_result_requires_unavailable_quality(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _result(
            now,
            status=ExternalIntelligenceOutcome.ABSTAINED,
            observations=(),
            quality=FeatureQuality.VALID,
            abstention_reasons=("no data",),
        )


def test_valid_abstained_result(now: datetime) -> None:
    result = _result(
        now,
        status=ExternalIntelligenceOutcome.ABSTAINED,
        observations=(),
        evidence=(),
        quality=FeatureQuality.UNAVAILABLE,
        abstention_reasons=("no data",),
    )
    assert result.status is ExternalIntelligenceOutcome.ABSTAINED


def test_analyzed_result_must_not_carry_abstention_reasons(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _result(now, abstention_reasons=("should not be here",))


# --- Immutability ---


def test_result_is_frozen(now: datetime) -> None:
    result = _result(now)
    with pytest.raises(ValidationError):
        result.status = ExternalIntelligenceOutcome.ABSTAINED  # type: ignore[misc]


def test_result_forbids_unknown_fields(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _result(now, unexpected_field="value")


# --- No generic provenance dict ---


def test_result_has_no_provenance_field() -> None:
    assert "provenance" not in ExternalIntelligenceAnalysisResult.model_fields

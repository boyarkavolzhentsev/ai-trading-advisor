"""Shared builders for Stage 4G external-intelligence-supervisor tests.

Builds ``ExternalIntelligenceAnalysisResult`` fixtures directly rather than
via a real Stage 4F analyst: Stage 4G aggregates already-produced Stage 4F
contracts, independent of how those contracts were produced - that path is
already covered by Stage 4F's own test suite. Not a test module itself (no
``test_`` prefix): pytest will not collect it. Mirrors
``tests/flow_supervisor_support.py`` one contour over.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.enums.external_intelligence_analysis import (
    ExternalIntelligenceAnalystType,
    ExternalIntelligenceDimension,
    ExternalIntelligenceOutcome,
)
from app.core.enums.quality import FeatureQuality
from app.core.models.base import Timestamp
from app.core.models.external_intelligence_analysis_result import (
    ExternalIntelligenceAnalysisObservation,
    ExternalIntelligenceAnalysisResult,
)
from app.core.models.external_intelligence_evidence import ExternalIntelligenceEvidence

NOW: Timestamp = datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)

CURRENCY = "USD"
OTHER_CURRENCY = "EUR"
SYMBOL = "BTCUSDT"
OTHER_SYMBOL = "ETHUSDT"
ASSET = "BTC"
OTHER_ASSET = "ETH"
NETWORK = "bitcoin"
OTHER_NETWORK = "ethereum"

_DEFAULT_SCOPE: dict[ExternalIntelligenceAnalystType, dict[str, str]] = {
    ExternalIntelligenceAnalystType.MACRO_EVENT: {"currency": CURRENCY},
    ExternalIntelligenceAnalystType.RATES_YIELD: {"currency": CURRENCY},
    ExternalIntelligenceAnalystType.NEWS_SENTIMENT: {"symbol": SYMBOL},
    ExternalIntelligenceAnalystType.ON_CHAIN: {"asset": ASSET, "network": NETWORK},
}

_DIMENSION_BY_TYPE: dict[ExternalIntelligenceAnalystType, ExternalIntelligenceDimension] = {
    ExternalIntelligenceAnalystType.MACRO_EVENT: ExternalIntelligenceDimension.SURPRISE,
    ExternalIntelligenceAnalystType.RATES_YIELD: ExternalIntelligenceDimension.POLICY_RATE_TREND,
    ExternalIntelligenceAnalystType.NEWS_SENTIMENT: ExternalIntelligenceDimension.RELEVANT_ITEM_PRESENCE,
    ExternalIntelligenceAnalystType.ON_CHAIN: ExternalIntelligenceDimension.ACTIVITY_TREND,
}


def make_evidence(
    *,
    analysis_time: Timestamp = NOW,
    quality: FeatureQuality = FeatureQuality.VALID,
    feature_name: str = "test.feature",
    source_record_id: str = "record-1",
) -> ExternalIntelligenceEvidence:
    return ExternalIntelligenceEvidence(
        feature_name=feature_name,
        observed_value="1",
        reference_value=None,
        quality=quality,
        source_timestamp=analysis_time,
        source_provider="test-provider",
        source_record_id=source_record_id,
        source_received_at=analysis_time,
        provenance="test:provider",
    )


def _scope_fields(analyst_type: ExternalIntelligenceAnalystType, overrides: dict[str, object]) -> dict[str, object]:
    scope = dict(_DEFAULT_SCOPE[analyst_type])
    scope.update(overrides)
    return {
        "currency": scope.get("currency"),
        "symbol": scope.get("symbol"),
        "asset": scope.get("asset"),
        "network": scope.get("network"),
    }


def analyzed_result(
    analyst_type: ExternalIntelligenceAnalystType,
    *,
    analysis_time: Timestamp = NOW,
    quality: FeatureQuality = FeatureQuality.VALID,
    value: str = "TEST_VALUE",
    **scope_overrides: object,
) -> ExternalIntelligenceAnalysisResult:
    """A generic ANALYZED result for any analyst type, one placeholder
    observation citing one evidence entry."""
    scope_fields = _scope_fields(analyst_type, scope_overrides)
    evidence = (make_evidence(analysis_time=analysis_time, quality=quality),)
    observation = ExternalIntelligenceAnalysisObservation(
        dimension=_DIMENSION_BY_TYPE[analyst_type],
        value=value,
        quality=quality,
        evidence_refs=(0,),
    )
    return ExternalIntelligenceAnalysisResult(
        analyst_type=analyst_type,
        analysis_time=analysis_time,
        status=ExternalIntelligenceOutcome.ANALYZED,
        observations=(observation,),
        evidence=evidence,
        quality=quality,
        **scope_fields,
    )


def abstained_result(
    analyst_type: ExternalIntelligenceAnalystType,
    *,
    analysis_time: Timestamp = NOW,
    reason: str = "no data supplied",
    **scope_overrides: object,
) -> ExternalIntelligenceAnalysisResult:
    scope_fields = _scope_fields(analyst_type, scope_overrides)
    return ExternalIntelligenceAnalysisResult(
        analyst_type=analyst_type,
        analysis_time=analysis_time,
        status=ExternalIntelligenceOutcome.ABSTAINED,
        observations=(),
        evidence=(),
        quality=FeatureQuality.UNAVAILABLE,
        abstention_reasons=(reason,),
        **scope_fields,
    )


def full_analyzed_set(*, analysis_time: Timestamp = NOW) -> tuple[ExternalIntelligenceAnalysisResult, ...]:
    """One ANALYZED result per Stage 4F analyst type, each in its own native scope."""
    return tuple(analyzed_result(t, analysis_time=analysis_time) for t in ExternalIntelligenceAnalystType)


__all__ = [
    "ASSET",
    "CURRENCY",
    "NETWORK",
    "NOW",
    "OTHER_ASSET",
    "OTHER_CURRENCY",
    "OTHER_NETWORK",
    "OTHER_SYMBOL",
    "SYMBOL",
    "abstained_result",
    "analyzed_result",
    "full_analyzed_set",
    "make_evidence",
]

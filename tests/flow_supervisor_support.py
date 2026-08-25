"""Shared builders for Stage 2C flow-supervisor tests.

Builds ``FlowAnalysisResult`` fixtures directly rather than via a real
``FlowFeatureSnapshot`` + Stage 2B engine: Stage 2C aggregates already-
produced Stage 2B contracts, independent of how those contracts were
produced - that path is already covered by Stage 2B's own test suite
(``tests/flow_analysts_support.py``). Not a test module itself (no
``test_`` prefix): pytest will not collect it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.enums.flow_analysis import (
    AnalysisDimension,
    AnalystOutcome,
    AnalystType,
    CorrelationRelationship,
    PriceFlowRelationship,
)
from app.core.enums.instrument import ContractType
from app.core.enums.quality import FeatureQuality
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.base import Timestamp
from app.core.models.flow_analysis_result import FlowAnalysisObservation, FlowAnalysisResult
from app.core.models.flow_evidence import FlowEvidence

NOW: Timestamp = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
SYMBOL = "BTCUSDT"
OTHER_SYMBOL = "ETHUSDT"
CONTRACT_TYPE = ContractType.PERPETUAL

WINDOW_10S = AnalyticsWindow(label="10s", duration=timedelta(seconds=10))
WINDOW_1M = AnalyticsWindow(label="1m", duration=timedelta(minutes=1))
WINDOWS = (WINDOW_10S, WINDOW_1M)


def make_evidence(
    *,
    feature_name: str = "test.feature",
    window: str | None = None,
    observed_value: str = "1",
    quality: FeatureQuality = FeatureQuality.VALID,
    source_timestamp: Timestamp = NOW,
    provenance: str = "test",
) -> FlowEvidence:
    return FlowEvidence(
        feature_name=feature_name,
        window=window,
        observed_value=observed_value,
        reference_value=None,
        quality=quality,
        source_timestamp=source_timestamp,
        provenance=provenance,
    )


def make_observation(
    *,
    dimension: AnalysisDimension,
    value: str,
    quality: FeatureQuality = FeatureQuality.VALID,
    window: str | None = None,
    subject: str | None = None,
    evidence_refs: tuple[int, ...] = (0,),
) -> FlowAnalysisObservation:
    return FlowAnalysisObservation(
        dimension=dimension,
        value=value,
        quality=quality,
        window=window,
        subject=subject,
        evidence_refs=evidence_refs,
    )


def analyzed_result(
    analyst_type: AnalystType,
    *,
    symbol: str = SYMBOL,
    contract_type: ContractType = CONTRACT_TYPE,
    observation_time: Timestamp = NOW,
    windows: tuple[AnalyticsWindow, ...] = WINDOWS,
    observations: tuple[FlowAnalysisObservation, ...] | None = None,
    evidence_entries: tuple[FlowEvidence, ...] | None = None,
    quality: FeatureQuality = FeatureQuality.VALID,
    provenance: dict[str, str] | None = None,
) -> FlowAnalysisResult:
    """A generic ANALYZED result for any analyst type, one placeholder observation by default."""
    if observations is None:
        observations = (make_observation(dimension=AnalysisDimension.DIRECTIONAL_PRESSURE, value="X"),)
    if evidence_entries is None:
        evidence_entries = (make_evidence(),)
    if provenance is None:
        provenance = {analyst_type.value.lower(): "test"}
    return FlowAnalysisResult(
        analyst_type=analyst_type,
        symbol=symbol,
        contract_type=contract_type,
        observation_time=observation_time,
        windows=windows,
        status=AnalystOutcome.ANALYZED,
        observations=observations,
        evidence=evidence_entries,
        quality=quality,
        provenance=provenance,
    )


def abstained_result(
    analyst_type: AnalystType,
    *,
    symbol: str = SYMBOL,
    contract_type: ContractType = CONTRACT_TYPE,
    observation_time: Timestamp = NOW,
    windows: tuple[AnalyticsWindow, ...] = WINDOWS,
    reason: str = "no usable data",
) -> FlowAnalysisResult:
    return FlowAnalysisResult(
        analyst_type=analyst_type,
        symbol=symbol,
        contract_type=contract_type,
        observation_time=observation_time,
        windows=windows,
        status=AnalystOutcome.ABSTAINED,
        quality=FeatureQuality.UNAVAILABLE,
        abstention_reasons=(reason,),
    )


def relationship_result(
    *,
    symbol: str = SYMBOL,
    contract_type: ContractType = CONTRACT_TYPE,
    observation_time: Timestamp = NOW,
    windows: tuple[AnalyticsWindow, ...] = WINDOWS,
    taker_values: tuple[PriceFlowRelationship, ...] = (),
    oi_values: tuple[PriceFlowRelationship, ...] = (),
    liquidation_values: tuple[PriceFlowRelationship, ...] = (),
    correlation_values: tuple[CorrelationRelationship, ...] = (),
    quality: FeatureQuality = FeatureQuality.VALID,
) -> FlowAnalysisResult:
    """Build a ``PRICE_FLOW_RELATIONSHIP`` result with one observation per
    supplied value per dimension (window labels assigned in order: 10s, 1m,
    then synthetic ``wN`` labels), each citing its own evidence entry -
    mirrors how the real ``PriceFlowRelationshipAnalyst`` pairs one evidence
    entry per window per relationship. ``correlation_values`` optionally adds
    ``CORRELATION_RELATIONSHIP`` observations (a distinct, non-participating
    vocabulary - see the approved Stage 2C design) to prove they never
    influence ``relationship_coherence``.

    Returns an ABSTAINED result when every value tuple is empty, matching
    the real analyst's own abstention behavior on zero observations.
    """
    evidence_entries: list[FlowEvidence] = []
    observations: list[FlowAnalysisObservation] = []

    def _window_label(i: int) -> str:
        return windows[i].label if i < len(windows) else f"w{i}"

    for dimension, values in (
        (AnalysisDimension.PRICE_TAKER_RELATIONSHIP, taker_values),
        (AnalysisDimension.PRICE_OPEN_INTEREST_RELATIONSHIP, oi_values),
        (AnalysisDimension.PRICE_LIQUIDATION_RELATIONSHIP, liquidation_values),
    ):
        for i, value in enumerate(values):
            window_label = _window_label(i)
            idx = len(evidence_entries)
            evidence_entries.append(make_evidence(window=window_label))
            observations.append(
                make_observation(dimension=dimension, value=value.value, window=window_label, evidence_refs=(idx,))
            )

    for i, corr_value in enumerate(correlation_values):
        window_label = _window_label(i)
        idx = len(evidence_entries)
        evidence_entries.append(make_evidence(window=window_label, feature_name="cross_features.pair.correlation"))
        observations.append(
            make_observation(
                dimension=AnalysisDimension.CORRELATION_RELATIONSHIP,
                value=corr_value.value,
                window=window_label,
                subject="pair",
                evidence_refs=(idx,),
            )
        )

    if not observations:
        return abstained_result(
            AnalystType.PRICE_FLOW_RELATIONSHIP,
            symbol=symbol,
            contract_type=contract_type,
            observation_time=observation_time,
            windows=windows,
            reason="no price/flow relationship evidence available",
        )

    return FlowAnalysisResult(
        analyst_type=AnalystType.PRICE_FLOW_RELATIONSHIP,
        symbol=symbol,
        contract_type=contract_type,
        observation_time=observation_time,
        windows=windows,
        status=AnalystOutcome.ANALYZED,
        observations=tuple(observations),
        evidence=tuple(evidence_entries),
        quality=quality,
        provenance={"price_context": "test"},
    )


def full_analyzed_set(
    *,
    symbol: str = SYMBOL,
    contract_type: ContractType = CONTRACT_TYPE,
    observation_time: Timestamp = NOW,
    windows: tuple[AnalyticsWindow, ...] = WINDOWS,
) -> tuple[FlowAnalysisResult, ...]:
    """One ANALYZED result per Stage 2B analyst type, all sharing one snapshot identity."""
    non_relationship = (
        AnalystType.TAKER_FLOW,
        AnalystType.LIQUIDATION,
        AnalystType.ORDER_BOOK_LIQUIDITY,
        AnalystType.OPEN_INTEREST,
        AnalystType.FUNDING,
    )
    results = [
        analyzed_result(
            analyst_type,
            symbol=symbol,
            contract_type=contract_type,
            observation_time=observation_time,
            windows=windows,
        )
        for analyst_type in non_relationship
    ]
    results.append(
        relationship_result(
            symbol=symbol,
            contract_type=contract_type,
            observation_time=observation_time,
            windows=windows,
            taker_values=(PriceFlowRelationship.AGREEMENT, PriceFlowRelationship.AGREEMENT),
            oi_values=(PriceFlowRelationship.AGREEMENT, PriceFlowRelationship.AGREEMENT),
            liquidation_values=(PriceFlowRelationship.AGREEMENT, PriceFlowRelationship.AGREEMENT),
        )
    )
    return tuple(results)

"""Shared builders for Stage 3C technical-supervisor tests.

Builds ``TechnicalAnalysisResult`` fixtures directly rather than via real
``TechnicalFeatureSnapshot`` + Stage 3B analysts: Stage 3C aggregates
already-produced Stage 3B contracts, independent of how those contracts were
produced - that path is already covered by Stage 3B's own test suite
(``tests/technical_analysts_support.py``). Not a test module itself (no
``test_`` prefix): pytest will not collect it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.enums.quality import FeatureQuality
from app.core.enums.technical_analysis import TechnicalAnalysisDimension, TechnicalAnalystOutcome, TechnicalAnalystType
from app.core.models.base import Timestamp
from app.core.models.technical_analysis_result import TechnicalAnalysisObservation, TechnicalAnalysisResult
from app.core.models.technical_evidence import TechnicalEvidence
from app.technical.timeframes import DEFAULT_TECHNICAL_TIMEFRAMES

NOW: Timestamp = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
SYMBOL = "BTCUSDT"
OTHER_SYMBOL = "ETHUSDT"
CONTRACT_TYPE = ContractType.PERPETUAL

DEFAULT_ANALYSTS: tuple[TechnicalAnalystType, ...] = tuple(TechnicalAnalystType)
DEFAULT_TIMEFRAMES: tuple[Timeframe, ...] = DEFAULT_TECHNICAL_TIMEFRAMES


def make_evidence(
    *,
    feature_name: str = "test.feature",
    observed_value: str = "1",
    reference_value: str | None = None,
    quality: FeatureQuality = FeatureQuality.VALID,
    source_timestamp: Timestamp = NOW,
    provenance: str = "test",
) -> TechnicalEvidence:
    return TechnicalEvidence(
        feature_name=feature_name,
        observed_value=observed_value,
        reference_value=reference_value,
        quality=quality,
        source_timestamp=source_timestamp,
        provenance=provenance,
    )


def make_observation(
    *,
    dimension: TechnicalAnalysisDimension,
    value: str,
    quality: FeatureQuality = FeatureQuality.VALID,
    subject: str | None = None,
    evidence_refs: tuple[int, ...] = (0,),
) -> TechnicalAnalysisObservation:
    return TechnicalAnalysisObservation(
        dimension=dimension, value=value, quality=quality, subject=subject, evidence_refs=evidence_refs
    )


_DEFAULT_OBSERVATION: dict[TechnicalAnalystType, TechnicalAnalysisObservation] = {
    TechnicalAnalystType.TREND: make_observation(dimension=TechnicalAnalysisDimension.RETURN_DIRECTION, value="UPWARD"),
    TechnicalAnalystType.MARKET_STRUCTURE: make_observation(
        dimension=TechnicalAnalysisDimension.STRUCTURAL_BREAK_PRESENCE, value="NO_BREAK_CONFIRMED"
    ),
    TechnicalAnalystType.VOLATILITY: make_observation(
        dimension=TechnicalAnalysisDimension.RANGE_EXPANSION_REFERENCE, value="AT_REFERENCE"
    ),
    TechnicalAnalystType.MOMENTUM: make_observation(dimension=TechnicalAnalysisDimension.ROC_SIGN, value="POSITIVE"),
    TechnicalAnalystType.MOVING_AVERAGE: make_observation(
        dimension=TechnicalAnalysisDimension.PRICE_VS_SMA_POSITION, value="ABOVE_SMA", subject="20"
    ),
    TechnicalAnalystType.CANDLE_STRUCTURE: make_observation(
        dimension=TechnicalAnalysisDimension.RANGE_SIZE_STATE, value="NON_ZERO_RANGE"
    ),
    TechnicalAnalystType.RANGE_STATE: make_observation(
        dimension=TechnicalAnalysisDimension.NORMALIZED_RANGE_REFERENCE, value="AT_REFERENCE"
    ),
}
"""One realistic-domain placeholder observation per analyst type, used as
``analyzed_result``'s default so generic (participation/quality/determinism)
fixtures never accidentally cross-contaminate an unrelated analyst's
coherence dimension."""


def analyzed_result(
    analyst_type: TechnicalAnalystType,
    timeframe: Timeframe,
    *,
    symbol: str = SYMBOL,
    contract_type: ContractType = CONTRACT_TYPE,
    observation_time: Timestamp = NOW,
    last_closed_candle_time: Timestamp | None = None,
    observations: tuple[TechnicalAnalysisObservation, ...] | None = None,
    evidence_entries: tuple[TechnicalEvidence, ...] | None = None,
    quality: FeatureQuality = FeatureQuality.VALID,
    provenance: dict[str, str] | None = None,
) -> TechnicalAnalysisResult:
    """A generic ANALYZED result for any (analyst_type, timeframe) cell, one
    domain-realistic placeholder observation by default."""
    if observations is None:
        observations = (_DEFAULT_OBSERVATION[analyst_type],)
    if evidence_entries is None:
        evidence_entries = (make_evidence(),)
    if provenance is None:
        provenance = {analyst_type.value.lower(): "test"}
    return TechnicalAnalysisResult(
        analyst_type=analyst_type,
        symbol=symbol,
        contract_type=contract_type,
        timeframe=timeframe,
        observation_time=observation_time,
        last_closed_candle_time=last_closed_candle_time,
        status=TechnicalAnalystOutcome.ANALYZED,
        observations=observations,
        evidence=evidence_entries,
        quality=quality,
        provenance=provenance,
    )


def abstained_result(
    analyst_type: TechnicalAnalystType,
    timeframe: Timeframe,
    *,
    symbol: str = SYMBOL,
    contract_type: ContractType = CONTRACT_TYPE,
    observation_time: Timestamp = NOW,
    last_closed_candle_time: Timestamp | None = None,
    reason: str = "no usable data",
) -> TechnicalAnalysisResult:
    return TechnicalAnalysisResult(
        analyst_type=analyst_type,
        symbol=symbol,
        contract_type=contract_type,
        timeframe=timeframe,
        observation_time=observation_time,
        last_closed_candle_time=last_closed_candle_time,
        status=TechnicalAnalystOutcome.ABSTAINED,
        quality=FeatureQuality.UNAVAILABLE,
        abstention_reasons=(reason,),
    )


def dimension_result(
    analyst_type: TechnicalAnalystType,
    timeframe: Timeframe,
    dimension: TechnicalAnalysisDimension,
    value: str,
    *,
    subject: str | None = None,
    quality: FeatureQuality = FeatureQuality.VALID,
    **kwargs: object,
) -> TechnicalAnalysisResult:
    """One ANALYZED result carrying exactly one observation of the given
    dimension/subject/value - used to build precise coherence scenarios."""
    return analyzed_result(
        analyst_type,
        timeframe,
        observations=(make_observation(dimension=dimension, value=value, subject=subject, quality=quality),),
        quality=quality,
        **kwargs,
    )


def moving_average_result(
    timeframe: Timeframe,
    *,
    price_vs_sma: dict[str, str] | None = None,
    ma_slope: dict[str, str] | None = None,
    ordering: tuple[str, str] | None = None,
    quality: FeatureQuality = FeatureQuality.VALID,
    **kwargs: object,
) -> TechnicalAnalysisResult:
    """One ANALYZED ``MOVING_AVERAGE`` result carrying an arbitrary
    combination of period-scoped observations - ``price_vs_sma``/``ma_slope``
    map a period string (e.g. ``"20"``) to its categorical value, and
    ``ordering`` is ``(period_pair_subject, value)`` e.g. ``("20_vs_50",
    "FASTER_ABOVE_SLOWER")``."""
    observations: list[TechnicalAnalysisObservation] = []
    for period, value in (price_vs_sma or {}).items():
        observations.append(
            make_observation(dimension=TechnicalAnalysisDimension.PRICE_VS_SMA_POSITION, value=value, subject=period)
        )
    for period, value in (ma_slope or {}).items():
        observations.append(
            make_observation(dimension=TechnicalAnalysisDimension.MA_SLOPE_DIRECTION, value=value, subject=period)
        )
    if ordering is not None:
        pair_subject, value = ordering
        observations.append(
            make_observation(dimension=TechnicalAnalysisDimension.MULTI_PERIOD_MA_ORDERING, value=value, subject=pair_subject)
        )
    return analyzed_result(
        TechnicalAnalystType.MOVING_AVERAGE, timeframe, observations=tuple(observations), quality=quality, **kwargs
    )


def full_matrix(
    *,
    symbol: str = SYMBOL,
    contract_type: ContractType = CONTRACT_TYPE,
    observation_time: Timestamp = NOW,
    analysts: tuple[TechnicalAnalystType, ...] = DEFAULT_ANALYSTS,
    timeframes: tuple[Timeframe, ...] = DEFAULT_TIMEFRAMES,
) -> tuple[TechnicalAnalysisResult, ...]:
    """One ANALYZED result per ``(analyst_type, timeframe)`` cell across the
    full given matrix (default: all 7 analysts x all 6 default timeframes)."""
    return tuple(
        analyzed_result(a, t, symbol=symbol, contract_type=contract_type, observation_time=observation_time)
        for t in timeframes
        for a in analysts
    )


__all__ = [
    "CONTRACT_TYPE",
    "DEFAULT_ANALYSTS",
    "DEFAULT_TIMEFRAMES",
    "NOW",
    "OTHER_SYMBOL",
    "SYMBOL",
    "abstained_result",
    "analyzed_result",
    "dimension_result",
    "full_matrix",
    "make_evidence",
    "make_observation",
    "moving_average_result",
]

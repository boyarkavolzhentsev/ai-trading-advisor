"""Deterministic Moving Average Analyst (Stage 3B).

Interprets Stage 3A ``MovingAverageFeatures`` only - never recomputes SMA,
EMA, distance-from-SMA, or MA slope (all remain Stage 3A arithmetic).
``distance_from_sma_pct``'s sign already encodes price-vs-SMA position, so
no raw close price is needed here. ``MULTI_PERIOD_MA_ORDERING`` reports only
the CURRENT instantaneous ordering of the fastest vs. slowest configured
period's SMA - never a crossover signal, since no comparison across time is
made.
"""

from __future__ import annotations

from app.core.enums.technical_analysis import (
    MovingAverageSlopeDirection,
    MultiPeriodMAOrdering,
    PricePositionRelativeToMA,
    TechnicalAnalysisDimension,
    TechnicalAnalystOutcome,
    TechnicalAnalystType,
)
from app.core.models.technical_analysis_result import TechnicalAnalysisObservation, TechnicalAnalysisResult
from app.core.models.technical_evidence import TechnicalEvidence
from app.core.models.technical_feature_snapshot import TechnicalFeatureSnapshot
from app.technical_analysts.base import abstain, make_evidence, qualifies, sign_category

ABSTENTION_REASON = "no usable moving average evidence available"


class MovingAverageAnalyst:
    """Deterministic interpretation of Stage 3A's per-period SMA/EMA facts."""

    analyst_type = TechnicalAnalystType.MOVING_AVERAGE

    def analyze(self, snapshot: TechnicalFeatureSnapshot) -> TechnicalAnalysisResult:
        moving_average = snapshot.moving_average
        if not qualifies(moving_average.status):
            return abstain(TechnicalAnalystType.MOVING_AVERAGE, snapshot, ABSTENTION_REASON)

        quality = moving_average.status.quality
        evidence: list[TechnicalEvidence] = []
        observations: list[TechnicalAnalysisObservation] = []

        for period in moving_average.periods:
            distance = moving_average.distance_from_sma_pct.get(period)
            position = sign_category(
                distance,
                positive=PricePositionRelativeToMA.ABOVE_SMA,
                negative=PricePositionRelativeToMA.BELOW_SMA,
                zero=PricePositionRelativeToMA.AT_SMA,
            )
            if position is not None:
                idx = len(evidence)
                evidence.append(
                    make_evidence(
                        feature_name="moving_average.distance_from_sma_pct",
                        observed_value=distance,
                        reference_value=0,
                        quality=quality,
                        source_timestamp=snapshot.observation_time,
                        provenance=moving_average.source,
                    )
                )
                observations.append(
                    TechnicalAnalysisObservation(
                        dimension=TechnicalAnalysisDimension.PRICE_VS_SMA_POSITION,
                        value=position.value,
                        quality=quality,
                        subject=str(period),
                        evidence_refs=(idx,),
                    )
                )

            slope = moving_average.ma_slope.get(period)
            slope_direction = sign_category(
                slope,
                positive=MovingAverageSlopeDirection.UPWARD,
                negative=MovingAverageSlopeDirection.DOWNWARD,
                zero=MovingAverageSlopeDirection.FLAT,
            )
            if slope_direction is not None:
                idx = len(evidence)
                evidence.append(
                    make_evidence(
                        feature_name="moving_average.ma_slope",
                        observed_value=slope,
                        reference_value=0,
                        quality=quality,
                        source_timestamp=snapshot.observation_time,
                        provenance=moving_average.source,
                    )
                )
                observations.append(
                    TechnicalAnalysisObservation(
                        dimension=TechnicalAnalysisDimension.MA_SLOPE_DIRECTION,
                        value=slope_direction.value,
                        quality=quality,
                        subject=str(period),
                        evidence_refs=(idx,),
                    )
                )

        if len(set(moving_average.periods)) >= 2:
            fastest = min(moving_average.periods)
            slowest = max(moving_average.periods)
            fast_sma = moving_average.sma.get(fastest)
            slow_sma = moving_average.sma.get(slowest)
            if fast_sma is not None and slow_sma is not None:
                fast_idx = len(evidence)
                evidence.append(
                    make_evidence(
                        feature_name="moving_average.sma",
                        observed_value=fast_sma,
                        reference_value=None,
                        quality=quality,
                        source_timestamp=snapshot.observation_time,
                        provenance=moving_average.source,
                    )
                )
                slow_idx = len(evidence)
                evidence.append(
                    make_evidence(
                        feature_name="moving_average.sma",
                        observed_value=slow_sma,
                        reference_value=None,
                        quality=quality,
                        source_timestamp=snapshot.observation_time,
                        provenance=moving_average.source,
                    )
                )
                if fast_sma > slow_sma:
                    ordering = MultiPeriodMAOrdering.FASTER_ABOVE_SLOWER
                elif fast_sma < slow_sma:
                    ordering = MultiPeriodMAOrdering.FASTER_BELOW_SLOWER
                else:
                    ordering = MultiPeriodMAOrdering.EQUAL
                observations.append(
                    TechnicalAnalysisObservation(
                        dimension=TechnicalAnalysisDimension.MULTI_PERIOD_MA_ORDERING,
                        value=ordering.value,
                        quality=quality,
                        subject=f"{fastest}_vs_{slowest}",
                        evidence_refs=(fast_idx, slow_idx),
                    )
                )

        if not observations:
            return abstain(TechnicalAnalystType.MOVING_AVERAGE, snapshot, ABSTENTION_REASON)

        return TechnicalAnalysisResult(
            analyst_type=TechnicalAnalystType.MOVING_AVERAGE,
            symbol=snapshot.symbol,
            contract_type=snapshot.contract_type,
            timeframe=snapshot.timeframe,
            observation_time=snapshot.observation_time,
            last_closed_candle_time=snapshot.last_closed_candle_time,
            status=TechnicalAnalystOutcome.ANALYZED,
            observations=tuple(observations),
            evidence=tuple(evidence),
            quality=quality,
            provenance={"moving_average": moving_average.source},
        )


__all__ = ["MovingAverageAnalyst"]

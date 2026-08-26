"""Deterministic Trend Analyst (Stage 3B).

Interprets Stage 3A ``TrendFeatures`` only - never recomputes return, slope,
HH/HL/LH/LL counts, or directional persistence (all remain Stage 3A
arithmetic). No magnitude thresholds: direction is sign-only, structural
sequence balance is an exact integer-count comparison, and
``directional_persistence`` is preserved as an evidence-backed numeric fact
(plus its own exact-boundary observation) rather than classified into a
strength label.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.technical_analysis import (
    StructuralSequenceBalance,
    TechnicalAgreementVerdict,
    TechnicalAnalysisDimension,
    TechnicalAnalystOutcome,
    TechnicalAnalystType,
    TrendDirection,
)
from app.core.models.technical_analysis_result import TechnicalAnalysisObservation, TechnicalAnalysisResult
from app.core.models.technical_evidence import TechnicalEvidence
from app.core.models.technical_feature_snapshot import TechnicalFeatureSnapshot
from app.technical_analysts.base import abstain, agreement_of, boundary_position, make_evidence, qualifies, sign_category

ABSTENTION_REASON = "no usable trend evidence available"

_DIRECTIONAL = (TrendDirection.UPWARD, TrendDirection.DOWNWARD)


class TrendAnalyst:
    """Deterministic interpretation of Stage 3A return/slope/structure-count facts."""

    analyst_type = TechnicalAnalystType.TREND

    def analyze(self, snapshot: TechnicalFeatureSnapshot) -> TechnicalAnalysisResult:
        trend = snapshot.trend
        if not qualifies(trend.status):
            return abstain(TechnicalAnalystType.TREND, snapshot, ABSTENTION_REASON)

        quality = trend.status.quality
        evidence: list[TechnicalEvidence] = []
        observations: list[TechnicalAnalysisObservation] = []

        return_direction = sign_category(
            trend.return_pct, positive=TrendDirection.UPWARD, negative=TrendDirection.DOWNWARD, zero=TrendDirection.FLAT
        )
        return_idx = None
        if return_direction is not None:
            return_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="trend.return_pct",
                    observed_value=trend.return_pct,
                    reference_value=Decimal(0),
                    quality=quality,
                    source_timestamp=snapshot.observation_time,
                    provenance=trend.source,
                )
            )
            observations.append(
                TechnicalAnalysisObservation(
                    dimension=TechnicalAnalysisDimension.RETURN_DIRECTION,
                    value=return_direction.value,
                    quality=quality,
                    evidence_refs=(return_idx,),
                )
            )

        slope_direction = sign_category(
            trend.slope, positive=TrendDirection.UPWARD, negative=TrendDirection.DOWNWARD, zero=TrendDirection.FLAT
        )
        slope_idx = None
        if slope_direction is not None:
            slope_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="trend.slope",
                    observed_value=trend.slope,
                    reference_value=Decimal(0),
                    quality=quality,
                    source_timestamp=snapshot.observation_time,
                    provenance=trend.source,
                )
            )
            observations.append(
                TechnicalAnalysisObservation(
                    dimension=TechnicalAnalysisDimension.SLOPE_DIRECTION,
                    value=slope_direction.value,
                    quality=quality,
                    evidence_refs=(slope_idx,),
                )
            )

        up_count = trend.higher_high_count + trend.higher_low_count
        down_count = trend.lower_high_count + trend.lower_low_count
        hh_idx = len(evidence)
        evidence.append(
            make_evidence(
                feature_name="trend.higher_high_count",
                observed_value=trend.higher_high_count,
                reference_value=None,
                quality=quality,
                source_timestamp=snapshot.observation_time,
                provenance=trend.source,
            )
        )
        hl_idx = len(evidence)
        evidence.append(
            make_evidence(
                feature_name="trend.higher_low_count",
                observed_value=trend.higher_low_count,
                reference_value=None,
                quality=quality,
                source_timestamp=snapshot.observation_time,
                provenance=trend.source,
            )
        )
        lh_idx = len(evidence)
        evidence.append(
            make_evidence(
                feature_name="trend.lower_high_count",
                observed_value=trend.lower_high_count,
                reference_value=None,
                quality=quality,
                source_timestamp=snapshot.observation_time,
                provenance=trend.source,
            )
        )
        ll_idx = len(evidence)
        evidence.append(
            make_evidence(
                feature_name="trend.lower_low_count",
                observed_value=trend.lower_low_count,
                reference_value=None,
                quality=quality,
                source_timestamp=snapshot.observation_time,
                provenance=trend.source,
            )
        )
        if up_count > down_count:
            balance = StructuralSequenceBalance.UPWARD_STRUCTURE
        elif down_count > up_count:
            balance = StructuralSequenceBalance.DOWNWARD_STRUCTURE
        else:
            balance = StructuralSequenceBalance.MIXED_STRUCTURE
        observations.append(
            TechnicalAnalysisObservation(
                dimension=TechnicalAnalysisDimension.STRUCTURAL_SEQUENCE_BALANCE,
                value=balance.value,
                quality=quality,
                evidence_refs=(hh_idx, hl_idx, lh_idx, ll_idx),
            )
        )

        agreement_refs = tuple(i for i in (return_idx, slope_idx) if i is not None)
        if agreement_refs:
            if return_direction in _DIRECTIONAL and slope_direction in _DIRECTIONAL:
                verdict = agreement_of([return_direction, slope_direction])
            else:
                verdict = TechnicalAgreementVerdict.INSUFFICIENT_DATA
            observations.append(
                TechnicalAnalysisObservation(
                    dimension=TechnicalAnalysisDimension.TREND_PRIMITIVE_AGREEMENT,
                    value=verdict.value,
                    quality=quality,
                    evidence_refs=agreement_refs,
                )
            )

        if trend.directional_persistence is not None:
            persistence_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="trend.directional_persistence",
                    observed_value=trend.directional_persistence,
                    reference_value=None,
                    quality=quality,
                    source_timestamp=snapshot.observation_time,
                    provenance=trend.source,
                )
            )
            boundary = boundary_position(trend.directional_persistence, minimum=Decimal(0), maximum=Decimal(1))
            observations.append(
                TechnicalAnalysisObservation(
                    dimension=TechnicalAnalysisDimension.DIRECTIONAL_PERSISTENCE,
                    value=boundary.value,
                    quality=quality,
                    evidence_refs=(persistence_idx,),
                )
            )

        if not observations:
            return abstain(TechnicalAnalystType.TREND, snapshot, ABSTENTION_REASON)

        return TechnicalAnalysisResult(
            analyst_type=TechnicalAnalystType.TREND,
            symbol=snapshot.symbol,
            contract_type=snapshot.contract_type,
            timeframe=snapshot.timeframe,
            observation_time=snapshot.observation_time,
            last_closed_candle_time=snapshot.last_closed_candle_time,
            status=TechnicalAnalystOutcome.ANALYZED,
            observations=tuple(observations),
            evidence=tuple(evidence),
            quality=quality,
            provenance={"trend": trend.source},
        )


__all__ = ["TrendAnalyst"]

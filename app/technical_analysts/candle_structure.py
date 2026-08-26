"""Deterministic Candle Structure Analyst (Stage 3B).

Interprets Stage 3A ``CandleStructureFeatures`` only - never recomputes
body/wick/range geometry (all remain Stage 3A arithmetic). Pure ordinal
geometry only - no named candlestick patterns (no "hammer", no
"engulfing"), no reversal/continuation interpretation. ``0.5`` is used as
the exact geometric midpoint of the close-location-value's natural
``[0, 1]`` bound, never an arbitrary third/quarter.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.technical_analysis import (
    BodyWickDominance,
    RangeSizeState,
    TechnicalAnalysisDimension,
    TechnicalAnalystOutcome,
    TechnicalAnalystType,
    WickSideComparison,
)
from app.core.models.technical_analysis_result import TechnicalAnalysisObservation, TechnicalAnalysisResult
from app.core.models.technical_evidence import TechnicalEvidence
from app.core.models.technical_feature_snapshot import TechnicalFeatureSnapshot
from app.technical_analysts.base import abstain, make_evidence, midpoint_relation, qualifies

ABSTENTION_REASON = "no usable candle structure evidence available"

CLOSE_LOCATION_MIDPOINT = Decimal("0.5")


class CandleStructureAnalyst:
    """Deterministic interpretation of the most recent closed candle's geometry."""

    analyst_type = TechnicalAnalystType.CANDLE_STRUCTURE

    def analyze(self, snapshot: TechnicalFeatureSnapshot) -> TechnicalAnalysisResult:
        candle_structure = snapshot.candle_structure
        if not qualifies(candle_structure.status):
            return abstain(TechnicalAnalystType.CANDLE_STRUCTURE, snapshot, ABSTENTION_REASON)

        quality = candle_structure.status.quality
        evidence: list[TechnicalEvidence] = []
        observations: list[TechnicalAnalysisObservation] = []

        range_size = candle_structure.range_size
        if range_size is not None:
            idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="candle_structure.range_size",
                    observed_value=range_size,
                    reference_value=0,
                    quality=quality,
                    source_timestamp=snapshot.observation_time,
                    provenance=candle_structure.source,
                )
            )
            state = RangeSizeState.ZERO_RANGE if range_size == 0 else RangeSizeState.NON_ZERO_RANGE
            observations.append(
                TechnicalAnalysisObservation(
                    dimension=TechnicalAnalysisDimension.RANGE_SIZE_STATE,
                    value=state.value,
                    quality=quality,
                    evidence_refs=(idx,),
                )
            )

        body_size = candle_structure.body_size
        upper_wick = candle_structure.upper_wick
        lower_wick = candle_structure.lower_wick
        if body_size is not None and upper_wick is not None and lower_wick is not None:
            body_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="candle_structure.body_size",
                    observed_value=body_size,
                    reference_value=None,
                    quality=quality,
                    source_timestamp=snapshot.observation_time,
                    provenance=candle_structure.source,
                )
            )
            wick_sum = upper_wick + lower_wick
            wick_sum_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="candle_structure.upper_wick_plus_lower_wick",
                    observed_value=wick_sum,
                    reference_value=None,
                    quality=quality,
                    source_timestamp=snapshot.observation_time,
                    provenance=candle_structure.source,
                )
            )
            if body_size > wick_sum:
                dominance = BodyWickDominance.BODY_DOMINANT
            elif wick_sum > body_size:
                dominance = BodyWickDominance.WICK_DOMINANT
            else:
                dominance = BodyWickDominance.EQUAL
            observations.append(
                TechnicalAnalysisObservation(
                    dimension=TechnicalAnalysisDimension.BODY_WICK_DOMINANCE,
                    value=dominance.value,
                    quality=quality,
                    evidence_refs=(body_idx, wick_sum_idx),
                )
            )

            upper_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="candle_structure.upper_wick",
                    observed_value=upper_wick,
                    reference_value=None,
                    quality=quality,
                    source_timestamp=snapshot.observation_time,
                    provenance=candle_structure.source,
                )
            )
            lower_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="candle_structure.lower_wick",
                    observed_value=lower_wick,
                    reference_value=None,
                    quality=quality,
                    source_timestamp=snapshot.observation_time,
                    provenance=candle_structure.source,
                )
            )
            if upper_wick > lower_wick:
                wick_comparison = WickSideComparison.UPPER_WICK_LARGER
            elif lower_wick > upper_wick:
                wick_comparison = WickSideComparison.LOWER_WICK_LARGER
            else:
                wick_comparison = WickSideComparison.EQUAL
            observations.append(
                TechnicalAnalysisObservation(
                    dimension=TechnicalAnalysisDimension.WICK_SIDE_COMPARISON,
                    value=wick_comparison.value,
                    quality=quality,
                    evidence_refs=(upper_idx, lower_idx),
                )
            )

        clv_relation = midpoint_relation(candle_structure.close_location_value, midpoint=CLOSE_LOCATION_MIDPOINT)
        if clv_relation is not None:
            idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="candle_structure.close_location_value",
                    observed_value=candle_structure.close_location_value,
                    reference_value=CLOSE_LOCATION_MIDPOINT,
                    quality=quality,
                    source_timestamp=snapshot.observation_time,
                    provenance=candle_structure.source,
                )
            )
            observations.append(
                TechnicalAnalysisObservation(
                    dimension=TechnicalAnalysisDimension.CLOSE_LOCATION_RELATION,
                    value=clv_relation.value,
                    quality=quality,
                    evidence_refs=(idx,),
                )
            )

        if not observations:
            return abstain(TechnicalAnalystType.CANDLE_STRUCTURE, snapshot, ABSTENTION_REASON)

        return TechnicalAnalysisResult(
            analyst_type=TechnicalAnalystType.CANDLE_STRUCTURE,
            symbol=snapshot.symbol,
            contract_type=snapshot.contract_type,
            timeframe=snapshot.timeframe,
            observation_time=snapshot.observation_time,
            last_closed_candle_time=snapshot.last_closed_candle_time,
            status=TechnicalAnalystOutcome.ANALYZED,
            observations=tuple(observations),
            evidence=tuple(evidence),
            quality=quality,
            provenance={"candle_structure": candle_structure.source},
        )


__all__ = ["CandleStructureAnalyst"]

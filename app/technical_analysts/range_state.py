"""Deterministic Range State Analyst (Stage 3B).

Interprets Stage 3A ``RangeStateFeatures`` only - never recomputes
normalized range or directional efficiency (both remain Stage 3A
arithmetic). ``normalized_range`` is compared only to the mathematically
neutral reference ``1.0``; ``directional_efficiency`` is compared only to
its own exact natural bounds ``0``/``1``. No CONSOLIDATING/RANGING/TRENDING
classification and no arbitrary threshold.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.technical_analysis import TechnicalAnalysisDimension, TechnicalAnalystOutcome, TechnicalAnalystType
from app.core.models.technical_analysis_result import TechnicalAnalysisObservation, TechnicalAnalysisResult
from app.core.models.technical_evidence import TechnicalEvidence
from app.core.models.technical_feature_snapshot import TechnicalFeatureSnapshot
from app.technical_analysts.base import abstain, boundary_position, make_evidence, qualifies, reference_comparison

ABSTENTION_REASON = "no usable range state evidence available"


class RangeStateAnalyst:
    """Deterministic interpretation of Stage 3A's calibration-free range facts."""

    analyst_type = TechnicalAnalystType.RANGE_STATE

    def analyze(self, snapshot: TechnicalFeatureSnapshot) -> TechnicalAnalysisResult:
        range_state = snapshot.range_state
        if not qualifies(range_state.status):
            return abstain(TechnicalAnalystType.RANGE_STATE, snapshot, ABSTENTION_REASON)

        quality = range_state.status.quality
        evidence: list[TechnicalEvidence] = []
        observations: list[TechnicalAnalysisObservation] = []

        comparison = reference_comparison(range_state.normalized_range)
        if comparison is not None:
            idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="range_state.normalized_range",
                    observed_value=range_state.normalized_range,
                    reference_value=1,
                    quality=quality,
                    source_timestamp=snapshot.observation_time,
                    provenance=range_state.source,
                )
            )
            observations.append(
                TechnicalAnalysisObservation(
                    dimension=TechnicalAnalysisDimension.NORMALIZED_RANGE_REFERENCE,
                    value=comparison.value,
                    quality=quality,
                    evidence_refs=(idx,),
                )
            )

        boundary = boundary_position(range_state.directional_efficiency, minimum=Decimal(0), maximum=Decimal(1))
        if boundary is not None:
            idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="range_state.directional_efficiency",
                    observed_value=range_state.directional_efficiency,
                    reference_value=None,
                    quality=quality,
                    source_timestamp=snapshot.observation_time,
                    provenance=range_state.source,
                )
            )
            observations.append(
                TechnicalAnalysisObservation(
                    dimension=TechnicalAnalysisDimension.DIRECTIONAL_EFFICIENCY_BOUNDARY,
                    value=boundary.value,
                    quality=quality,
                    evidence_refs=(idx,),
                )
            )

        if not observations:
            return abstain(TechnicalAnalystType.RANGE_STATE, snapshot, ABSTENTION_REASON)

        return TechnicalAnalysisResult(
            analyst_type=TechnicalAnalystType.RANGE_STATE,
            symbol=snapshot.symbol,
            contract_type=snapshot.contract_type,
            timeframe=snapshot.timeframe,
            observation_time=snapshot.observation_time,
            last_closed_candle_time=snapshot.last_closed_candle_time,
            status=TechnicalAnalystOutcome.ANALYZED,
            observations=tuple(observations),
            evidence=tuple(evidence),
            quality=quality,
            provenance={"range_state": range_state.source},
        )


__all__ = ["RangeStateAnalyst"]

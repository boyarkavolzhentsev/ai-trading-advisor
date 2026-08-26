"""Deterministic Volatility Analyst (Stage 3B).

Interprets Stage 3A ``VolatilityFeatures`` only - never recomputes true
range, ATR, or realized volatility (all remain Stage 3A arithmetic).
Intentionally thin in v1: the only calibration-free comparison Stage 3A's
single-lookback contract supports is ``range_expansion_ratio`` against the
mathematically neutral reference ``1.0`` (current true range vs. its own
ATR). Multi-window realized-volatility comparison is deferred until Stage 3A
exposes more than one ``volatility_lookback`` per snapshot - see the
approved Stage 3B design report, section 16/36.
"""

from __future__ import annotations

from app.core.enums.technical_analysis import TechnicalAnalysisDimension, TechnicalAnalystOutcome, TechnicalAnalystType
from app.core.models.technical_analysis_result import TechnicalAnalysisObservation, TechnicalAnalysisResult
from app.core.models.technical_evidence import TechnicalEvidence
from app.core.models.technical_feature_snapshot import TechnicalFeatureSnapshot
from app.technical_analysts.base import abstain, make_evidence, qualifies, reference_comparison

ABSTENTION_REASON = "no usable volatility evidence available"


class VolatilityAnalyst:
    """Deterministic interpretation of Stage 3A's ATR-relative range-expansion ratio."""

    analyst_type = TechnicalAnalystType.VOLATILITY

    def analyze(self, snapshot: TechnicalFeatureSnapshot) -> TechnicalAnalysisResult:
        volatility = snapshot.volatility
        if not qualifies(volatility.status):
            return abstain(TechnicalAnalystType.VOLATILITY, snapshot, ABSTENTION_REASON)

        quality = volatility.status.quality
        evidence: list[TechnicalEvidence] = []
        observations: list[TechnicalAnalysisObservation] = []

        comparison = reference_comparison(volatility.range_expansion_ratio)
        if comparison is not None:
            idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="volatility.range_expansion_ratio",
                    observed_value=volatility.range_expansion_ratio,
                    reference_value=1,
                    quality=quality,
                    source_timestamp=snapshot.observation_time,
                    provenance=volatility.source,
                )
            )
            observations.append(
                TechnicalAnalysisObservation(
                    dimension=TechnicalAnalysisDimension.RANGE_EXPANSION_REFERENCE,
                    value=comparison.value,
                    quality=quality,
                    evidence_refs=(idx,),
                )
            )

        if not observations:
            return abstain(TechnicalAnalystType.VOLATILITY, snapshot, ABSTENTION_REASON)

        return TechnicalAnalysisResult(
            analyst_type=TechnicalAnalystType.VOLATILITY,
            symbol=snapshot.symbol,
            contract_type=snapshot.contract_type,
            timeframe=snapshot.timeframe,
            observation_time=snapshot.observation_time,
            last_closed_candle_time=snapshot.last_closed_candle_time,
            status=TechnicalAnalystOutcome.ANALYZED,
            observations=tuple(observations),
            evidence=tuple(evidence),
            quality=quality,
            provenance={"volatility": volatility.source},
        )


__all__ = ["VolatilityAnalyst"]

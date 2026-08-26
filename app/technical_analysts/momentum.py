"""Deterministic Momentum Analyst (Stage 3B).

Interprets Stage 3A ``MomentumFeatures`` only - never recomputes ROC or RSI
(both remain Stage 3A arithmetic). ROC is sign-only; RSI is compared only to
its own mathematically neutral midpoint (50 on ``[0, 100]``) - never to a
calibrated 70/30 overbought/oversold cutoff.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.technical_analysis import (
    MidpointRelation,
    ROCSign,
    TechnicalAgreementVerdict,
    TechnicalAnalysisDimension,
    TechnicalAnalystOutcome,
    TechnicalAnalystType,
)
from app.core.models.technical_analysis_result import TechnicalAnalysisObservation, TechnicalAnalysisResult
from app.core.models.technical_evidence import TechnicalEvidence
from app.core.models.technical_feature_snapshot import TechnicalFeatureSnapshot
from app.technical_analysts.base import abstain, make_evidence, midpoint_relation, qualifies, sign_category

ABSTENTION_REASON = "no usable momentum evidence available"

RSI_MIDPOINT = Decimal(50)


class MomentumAnalyst:
    """Deterministic interpretation of Stage 3A's ROC sign and RSI-midpoint relation."""

    analyst_type = TechnicalAnalystType.MOMENTUM

    def analyze(self, snapshot: TechnicalFeatureSnapshot) -> TechnicalAnalysisResult:
        momentum = snapshot.momentum
        if not qualifies(momentum.status):
            return abstain(TechnicalAnalystType.MOMENTUM, snapshot, ABSTENTION_REASON)

        quality = momentum.status.quality
        evidence: list[TechnicalEvidence] = []
        observations: list[TechnicalAnalysisObservation] = []

        roc_sign = sign_category(momentum.roc, positive=ROCSign.POSITIVE, negative=ROCSign.NEGATIVE, zero=ROCSign.ZERO)
        roc_idx = None
        if roc_sign is not None:
            roc_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="momentum.roc",
                    observed_value=momentum.roc,
                    reference_value=Decimal(0),
                    quality=quality,
                    source_timestamp=snapshot.observation_time,
                    provenance=momentum.source,
                )
            )
            observations.append(
                TechnicalAnalysisObservation(
                    dimension=TechnicalAnalysisDimension.ROC_SIGN,
                    value=roc_sign.value,
                    quality=quality,
                    evidence_refs=(roc_idx,),
                )
            )

        rsi_relation = midpoint_relation(momentum.rsi, midpoint=RSI_MIDPOINT)
        rsi_idx = None
        if rsi_relation is not None:
            rsi_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="momentum.rsi",
                    observed_value=momentum.rsi,
                    reference_value=RSI_MIDPOINT,
                    quality=quality,
                    source_timestamp=snapshot.observation_time,
                    provenance=momentum.source,
                )
            )
            observations.append(
                TechnicalAnalysisObservation(
                    dimension=TechnicalAnalysisDimension.RSI_MIDPOINT_RELATION,
                    value=rsi_relation.value,
                    quality=quality,
                    evidence_refs=(rsi_idx,),
                )
            )

        agreement_refs = tuple(i for i in (roc_idx, rsi_idx) if i is not None)
        if agreement_refs:
            roc_directional = roc_sign in (ROCSign.POSITIVE, ROCSign.NEGATIVE)
            rsi_directional = rsi_relation in (MidpointRelation.ABOVE_MIDPOINT, MidpointRelation.BELOW_MIDPOINT)
            if roc_directional and rsi_directional:
                roc_up = roc_sign is ROCSign.POSITIVE
                rsi_up = rsi_relation is MidpointRelation.ABOVE_MIDPOINT
                verdict = TechnicalAgreementVerdict.ALL_AGREE if roc_up == rsi_up else TechnicalAgreementVerdict.MIXED
            else:
                verdict = TechnicalAgreementVerdict.INSUFFICIENT_DATA
            observations.append(
                TechnicalAnalysisObservation(
                    dimension=TechnicalAnalysisDimension.MOMENTUM_PRIMITIVE_AGREEMENT,
                    value=verdict.value,
                    quality=quality,
                    evidence_refs=agreement_refs,
                )
            )

        if not observations:
            return abstain(TechnicalAnalystType.MOMENTUM, snapshot, ABSTENTION_REASON)

        return TechnicalAnalysisResult(
            analyst_type=TechnicalAnalystType.MOMENTUM,
            symbol=snapshot.symbol,
            contract_type=snapshot.contract_type,
            timeframe=snapshot.timeframe,
            observation_time=snapshot.observation_time,
            last_closed_candle_time=snapshot.last_closed_candle_time,
            status=TechnicalAnalystOutcome.ANALYZED,
            observations=tuple(observations),
            evidence=tuple(evidence),
            quality=quality,
            provenance={"momentum": momentum.source},
        )


__all__ = ["MomentumAnalyst"]

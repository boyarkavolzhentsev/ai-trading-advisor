"""Deterministic Liquidation Analyst (Stage 2B).

Interprets Stage 2A ``LiquidationWindowFeatures`` only. Preserves the
normalized semantics already established below this layer: forced ``SELL``
closes a long (counted as long-liquidation volume), forced ``BUY`` closes a
short (counted as short-liquidation volume) - see ``app.flow.liquidation``.

A window with zero liquidation events on a healthy stream is a legitimate
``VALID`` zero, never ``UNAVAILABLE`` - ``ACTIVITY_PRESENCE`` is reported as
a dimension separate from ``DIRECTIONAL_PRESSURE`` precisely so "no events"
(``NO_ACTIVITY``) is never conflated with "events balanced on both sides"
(``BALANCED``). No burst/cluster/unusual-liquidation labeling - abnormality
detection is deferred.
"""

from __future__ import annotations

from app.core.enums.flow_analysis import AnalysisDimension, AnalystOutcome, AnalystType, LiquidationActivity, LiquidationPressure
from app.core.enums.quality import FeatureQuality
from app.core.models.flow_analysis_result import FlowAnalysisObservation, FlowAnalysisResult
from app.core.models.flow_evidence import FlowEvidence
from app.core.models.flow_feature_snapshot import FlowFeatureSnapshot
from app.flow_analysts.base import make_evidence, qualifies, sign_category, worse_of_many

ABSTENTION_REASON = "no liquidation window has usable (non-UNAVAILABLE) data"


class LiquidationAnalyst:
    """Deterministic interpretation of forced-liquidation flow."""

    analyst_type = AnalystType.LIQUIDATION

    def analyze(self, snapshot: FlowFeatureSnapshot) -> FlowAnalysisResult:
        provenance_label = snapshot.provenance.get("liquidation", "unknown")
        evidence: list[FlowEvidence] = []
        observations: list[FlowAnalysisObservation] = []

        for label, features in snapshot.liquidation.items():
            if not qualifies(features.status):
                continue

            imbalance_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="liquidation.liquidation_imbalance",
                    window=label,
                    observed_value=features.liquidation_imbalance,
                    reference_value=None,
                    quality=features.status.quality,
                    source_timestamp=snapshot.observation_time,
                    provenance=provenance_label,
                )
            )
            pressure = sign_category(
                features.liquidation_imbalance,
                positive=LiquidationPressure.LONG_LIQUIDATIONS_DOMINANT,
                negative=LiquidationPressure.SHORT_LIQUIDATIONS_DOMINANT,
                zero=LiquidationPressure.BALANCED,
            )
            assert pressure is not None  # liquidation_imbalance is never None on a qualifying window
            observations.append(
                FlowAnalysisObservation(
                    dimension=AnalysisDimension.DIRECTIONAL_PRESSURE,
                    window=label,
                    value=pressure.value,
                    quality=features.status.quality,
                    evidence_refs=(imbalance_idx,),
                )
            )

            count_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="liquidation.liquidation_count",
                    window=label,
                    observed_value=features.liquidation_count,
                    reference_value=None,
                    quality=features.status.quality,
                    source_timestamp=snapshot.observation_time,
                    provenance=provenance_label,
                )
            )
            activity = (
                LiquidationActivity.ACTIVITY_PRESENT
                if features.liquidation_count > 0
                else LiquidationActivity.NO_ACTIVITY
            )
            observations.append(
                FlowAnalysisObservation(
                    dimension=AnalysisDimension.ACTIVITY_PRESENCE,
                    window=label,
                    value=activity.value,
                    quality=features.status.quality,
                    evidence_refs=(count_idx,),
                )
            )

        if not observations:
            return FlowAnalysisResult(
                analyst_type=AnalystType.LIQUIDATION,
                symbol=snapshot.symbol,
                contract_type=snapshot.contract_type,
                observation_time=snapshot.observation_time,
                windows=snapshot.windows,
                status=AnalystOutcome.ABSTAINED,
                quality=FeatureQuality.UNAVAILABLE,
                abstention_reasons=(ABSTENTION_REASON,),
            )

        return FlowAnalysisResult(
            analyst_type=AnalystType.LIQUIDATION,
            symbol=snapshot.symbol,
            contract_type=snapshot.contract_type,
            observation_time=snapshot.observation_time,
            windows=snapshot.windows,
            status=AnalystOutcome.ANALYZED,
            observations=tuple(observations),
            evidence=tuple(evidence),
            quality=worse_of_many(observation.quality for observation in observations),
            provenance={"liquidation": provenance_label},
        )


__all__ = ["LiquidationAnalyst"]

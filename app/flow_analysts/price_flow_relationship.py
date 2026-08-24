"""Deterministic Price/Flow Relationship Analyst (Stage 2B).

The single deliberate exception to the otherwise narrow domain-specialist
boundary: reads price context together with taker flow, open interest and
liquidation - solely to describe deterministic categorical relationships
between price movement and each flow metric. It never recomputes a new
correlation (that stays in ``app.flow.cross_features``); it only
categorizes signs of already-computed Stage 2A numbers and the sign of the
one correlation Stage 2A already provides.

Zero semantics are explicit and conservative: whenever either side of a
price/flow comparison is exactly zero, the relationship is reported as
``NO_DIRECTION`` rather than guessed as agreement or divergence. It must
never interpret divergence as reversal or agreement as trade confirmation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.core.enums.flow_analysis import AnalysisDimension, AnalystOutcome, AnalystType, CorrelationRelationship, PriceFlowRelationship
from app.core.enums.quality import FeatureQuality
from app.core.models.flow_analysis_result import FlowAnalysisObservation, FlowAnalysisResult
from app.core.models.flow_evidence import FlowEvidence
from app.core.models.base import Timestamp
from app.core.models.flow_feature_snapshot import FlowFeatureSnapshot
from app.core.models.price_context_features import PriceContextWindowFeatures
from app.flow_analysts.base import make_evidence, qualifies, sign_category, worse_of_many

ABSTENTION_REASON = "no price/flow relationship evidence available"

_RELATED_DOMAINS: tuple[str, ...] = ("price_context", "taker_flow", "open_interest", "liquidation")


@dataclass(frozen=True, slots=True)
class _Leg:
    """The non-price side of one instantaneous sign-relationship comparison."""

    value: Decimal
    feature_name: str
    quality: FeatureQuality
    provenance: str


def _relationship(price_value: Decimal, other_value: Decimal) -> PriceFlowRelationship:
    """Categorize the instantaneous sign relationship of two Decimal values.

    Either side being exactly zero (no directional signal on that side) is
    reported as ``NO_DIRECTION`` - never silently treated as agreement.
    """
    if price_value == 0 or other_value == 0:
        return PriceFlowRelationship.NO_DIRECTION
    return PriceFlowRelationship.AGREEMENT if (price_value > 0) == (other_value > 0) else PriceFlowRelationship.DIVERGENCE


class PriceFlowRelationshipAnalyst:
    """Deterministic interpretation of price-vs-flow relationships."""

    analyst_type = AnalystType.PRICE_FLOW_RELATIONSHIP

    def analyze(self, snapshot: FlowFeatureSnapshot) -> FlowAnalysisResult:
        evidence: list[FlowEvidence] = []
        observations: list[FlowAnalysisObservation] = []
        provenance = {
            domain: snapshot.provenance[domain] for domain in _RELATED_DOMAINS if domain in snapshot.provenance
        }
        price_provenance = snapshot.provenance.get("price_context", "unknown")

        for label, cross in snapshot.cross_features.items():
            if not qualifies(cross.status) or cross.correlation is None:
                continue
            idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name=f"cross_features.{cross.pair_label}.correlation",
                    window=label,
                    observed_value=cross.correlation,
                    reference_value=None,
                    quality=cross.status.quality,
                    source_timestamp=snapshot.observation_time,
                    provenance=price_provenance,
                )
            )
            category = sign_category(
                cross.correlation,
                positive=CorrelationRelationship.POSITIVE_RELATIONSHIP,
                negative=CorrelationRelationship.NEGATIVE_RELATIONSHIP,
                zero=CorrelationRelationship.NO_RELATIONSHIP,
            )
            assert category is not None
            observations.append(
                FlowAnalysisObservation(
                    dimension=AnalysisDimension.CORRELATION_RELATIONSHIP,
                    window=label,
                    subject=cross.pair_label,
                    value=category.value,
                    quality=cross.status.quality,
                    evidence_refs=(idx,),
                )
            )

        for label, price in snapshot.price_context.items():
            if not qualifies(price.status) or price.return_pct is None:
                continue

            taker = snapshot.taker_flow.get(label)
            if taker is not None and qualifies(taker.status):
                self._append_relationship(
                    evidence,
                    observations,
                    dimension=AnalysisDimension.PRICE_TAKER_RELATIONSHIP,
                    window=label,
                    price=price,
                    price_provenance=price_provenance,
                    other=_Leg(
                        value=taker.delta,
                        feature_name="taker_flow.delta",
                        quality=taker.status.quality,
                        provenance=snapshot.provenance.get("taker_flow", "unknown"),
                    ),
                    snapshot_time=snapshot.observation_time,
                )

            oi = snapshot.open_interest
            oi_window = oi.windows.get(label) if oi is not None else None
            if oi_window is not None and qualifies(oi_window.status) and oi_window.percent_change is not None:
                self._append_relationship(
                    evidence,
                    observations,
                    dimension=AnalysisDimension.PRICE_OPEN_INTEREST_RELATIONSHIP,
                    window=label,
                    price=price,
                    price_provenance=price_provenance,
                    other=_Leg(
                        value=oi_window.percent_change,
                        feature_name="open_interest.percent_change",
                        quality=oi_window.status.quality,
                        provenance=snapshot.provenance.get("open_interest", "unknown"),
                    ),
                    snapshot_time=snapshot.observation_time,
                )

            liquidation = snapshot.liquidation.get(label)
            if liquidation is not None and qualifies(liquidation.status):
                self._append_relationship(
                    evidence,
                    observations,
                    dimension=AnalysisDimension.PRICE_LIQUIDATION_RELATIONSHIP,
                    window=label,
                    price=price,
                    price_provenance=price_provenance,
                    other=_Leg(
                        value=liquidation.liquidation_imbalance,
                        feature_name="liquidation.liquidation_imbalance",
                        quality=liquidation.status.quality,
                        provenance=snapshot.provenance.get("liquidation", "unknown"),
                    ),
                    snapshot_time=snapshot.observation_time,
                )

        if not observations:
            return FlowAnalysisResult(
                analyst_type=AnalystType.PRICE_FLOW_RELATIONSHIP,
                symbol=snapshot.symbol,
                contract_type=snapshot.contract_type,
                observation_time=snapshot.observation_time,
                windows=snapshot.windows,
                status=AnalystOutcome.ABSTAINED,
                quality=FeatureQuality.UNAVAILABLE,
                abstention_reasons=(ABSTENTION_REASON,),
            )

        return FlowAnalysisResult(
            analyst_type=AnalystType.PRICE_FLOW_RELATIONSHIP,
            symbol=snapshot.symbol,
            contract_type=snapshot.contract_type,
            observation_time=snapshot.observation_time,
            windows=snapshot.windows,
            status=AnalystOutcome.ANALYZED,
            observations=tuple(observations),
            evidence=tuple(evidence),
            quality=worse_of_many(observation.quality for observation in observations),
            provenance=provenance,
        )

    @staticmethod
    def _append_relationship(
        evidence: list[FlowEvidence],
        observations: list[FlowAnalysisObservation],
        *,
        dimension: AnalysisDimension,
        window: str,
        price: PriceContextWindowFeatures,
        price_provenance: str,
        other: _Leg,
        snapshot_time: Timestamp,
    ) -> None:
        assert price.return_pct is not None
        price_idx = len(evidence)
        evidence.append(
            make_evidence(
                feature_name="price_context.return_pct",
                window=window,
                observed_value=price.return_pct,
                reference_value=None,
                quality=price.status.quality,
                source_timestamp=snapshot_time,
                provenance=price_provenance,
            )
        )
        other_idx = len(evidence)
        evidence.append(
            make_evidence(
                feature_name=other.feature_name,
                window=window,
                observed_value=other.value,
                reference_value=None,
                quality=other.quality,
                source_timestamp=snapshot_time,
                provenance=other.provenance,
            )
        )
        relationship = _relationship(price.return_pct, other.value)
        observations.append(
            FlowAnalysisObservation(
                dimension=dimension,
                window=window,
                value=relationship.value,
                quality=worse_of_many([price.status.quality, other.quality]),
                evidence_refs=(price_idx, other_idx),
            )
        )


__all__ = ["PriceFlowRelationshipAnalyst"]

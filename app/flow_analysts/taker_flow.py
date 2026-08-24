"""Deterministic Taker Flow Analyst (Stage 2B).

Interprets Stage 2A ``TakerFlowWindowFeatures`` only - never raw
``TradeEvent`` history, never liquidation/order-book/open-interest/
funding/price data. No magnitude thresholds: pressure is sign-only, and
window-magnitude trend is a shortest-vs-longest ordinal comparison, never a
calibrated cutoff.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.flow_analysis import (
    AnalysisDimension,
    AnalystOutcome,
    AnalystType,
    OrdinalTrend,
    TakerFlowPressure,
)
from app.core.enums.quality import FeatureQuality
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.flow_analysis_result import FlowAnalysisObservation, FlowAnalysisResult
from app.core.models.flow_evidence import FlowEvidence
from app.core.models.flow_feature_snapshot import FlowFeatureSnapshot
from app.flow_analysts.base import agreement_of, make_evidence, ordinal_trend, qualifies, shortest_and_longest, sign_category, worse_of_many

ABSTENTION_REASON = "no taker-flow window has usable (non-UNAVAILABLE) data"


class TakerFlowAnalyst:
    """Deterministic interpretation of executed taker buy/sell flow pressure."""

    analyst_type = AnalystType.TAKER_FLOW

    def analyze(self, snapshot: FlowFeatureSnapshot) -> FlowAnalysisResult:
        provenance_label = snapshot.provenance.get("taker_flow", "unknown")
        evidence: list[FlowEvidence] = []
        observations: list[FlowAnalysisObservation] = []

        pressures: dict[str, TakerFlowPressure] = {}
        pressure_evidence: dict[str, int] = {}
        rates: dict[str, Decimal] = {}
        rate_evidence: dict[str, int] = {}
        rate_windows: dict[str, AnalyticsWindow] = {}
        qualities: dict[str, FeatureQuality] = {}

        for label, features in snapshot.taker_flow.items():
            if not qualifies(features.status):
                continue
            qualities[label] = features.status.quality

            category = sign_category(
                features.delta,
                positive=TakerFlowPressure.BUY_DOMINANT,
                negative=TakerFlowPressure.SELL_DOMINANT,
                zero=TakerFlowPressure.BALANCED,
            )
            if category is not None:
                idx = len(evidence)
                evidence.append(
                    make_evidence(
                        feature_name="taker_flow.delta",
                        window=label,
                        observed_value=features.delta,
                        reference_value=None,
                        quality=features.status.quality,
                        source_timestamp=snapshot.observation_time,
                        provenance=provenance_label,
                    )
                )
                pressures[label] = category
                pressure_evidence[label] = idx
                observations.append(
                    FlowAnalysisObservation(
                        dimension=AnalysisDimension.DIRECTIONAL_PRESSURE,
                        window=label,
                        value=category.value,
                        quality=features.status.quality,
                        evidence_refs=(idx,),
                    )
                )

            rate_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="taker_flow.delta_rate",
                    window=label,
                    observed_value=features.delta_rate,
                    reference_value=None,
                    quality=features.status.quality,
                    source_timestamp=snapshot.observation_time,
                    provenance=provenance_label,
                )
            )
            rates[label] = features.delta_rate
            rate_evidence[label] = rate_idx
            rate_windows[label] = features.window

        if pressures:
            observations.append(
                FlowAnalysisObservation(
                    dimension=AnalysisDimension.PERSISTENCE,
                    value=agreement_of(list(pressures.values())).value,
                    quality=worse_of_many(qualities[label] for label in pressures),
                    evidence_refs=tuple(pressure_evidence.values()),
                )
            )

        if rate_windows:
            pair = shortest_and_longest(rate_windows)
            if pair is None:
                (only_label,) = rate_windows
                observations.append(
                    FlowAnalysisObservation(
                        dimension=AnalysisDimension.MAGNITUDE_TREND,
                        value=OrdinalTrend.INSUFFICIENT_DATA.value,
                        quality=qualities[only_label],
                        evidence_refs=(rate_evidence[only_label],),
                    )
                )
            else:
                short_label, long_label = pair
                trend = ordinal_trend(rates[short_label], rates[long_label])
                observations.append(
                    FlowAnalysisObservation(
                        dimension=AnalysisDimension.MAGNITUDE_TREND,
                        value=trend.value,
                        quality=worse_of_many([qualities[short_label], qualities[long_label]]),
                        evidence_refs=(rate_evidence[short_label], rate_evidence[long_label]),
                    )
                )

        if not observations:
            return FlowAnalysisResult(
                analyst_type=AnalystType.TAKER_FLOW,
                symbol=snapshot.symbol,
                contract_type=snapshot.contract_type,
                observation_time=snapshot.observation_time,
                windows=snapshot.windows,
                status=AnalystOutcome.ABSTAINED,
                quality=FeatureQuality.UNAVAILABLE,
                abstention_reasons=(ABSTENTION_REASON,),
            )

        return FlowAnalysisResult(
            analyst_type=AnalystType.TAKER_FLOW,
            symbol=snapshot.symbol,
            contract_type=snapshot.contract_type,
            observation_time=snapshot.observation_time,
            windows=snapshot.windows,
            status=AnalystOutcome.ANALYZED,
            observations=tuple(observations),
            evidence=tuple(evidence),
            quality=worse_of_many(observation.quality for observation in observations),
            provenance={"taker_flow": provenance_label},
        )


__all__ = ["TakerFlowAnalyst"]

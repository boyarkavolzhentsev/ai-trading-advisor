"""Deterministic Open Interest Analyst (Stage 2B).

Interprets Stage 2A ``OpenInterestFeatures`` only. ``percent_change`` and
``oi_velocity`` are treated as two separate evidence-backed dimensions
(they can disagree in edge cases since they use different reference
points) rather than being collapsed into one. No "unusual OI expansion"
labeling - abnormality detection is deferred.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.flow_analysis import AnalysisDimension, AnalystOutcome, AnalystType, OpenInterestTrend, OrdinalTrend
from app.core.enums.quality import FeatureQuality
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.flow_analysis_result import FlowAnalysisObservation, FlowAnalysisResult
from app.core.models.flow_evidence import FlowEvidence
from app.core.models.flow_feature_snapshot import FlowFeatureSnapshot
from app.flow_analysts.base import agreement_of, make_evidence, ordinal_trend, qualifies, shortest_and_longest, sign_category, worse_of_many

ABSTENTION_REASON = "no open-interest observation available"


class OpenInterestAnalyst:
    """Deterministic interpretation of open-interest change."""

    analyst_type = AnalystType.OPEN_INTEREST

    def analyze(self, snapshot: FlowFeatureSnapshot) -> FlowAnalysisResult:
        oi = snapshot.open_interest
        provenance_label = snapshot.provenance.get("open_interest", "unknown")

        if oi is None or not qualifies(oi.status):
            return self._abstain(snapshot)

        evidence: list[FlowEvidence] = []
        observations: list[FlowAnalysisObservation] = []

        trends: dict[str, OpenInterestTrend] = {}
        trend_evidence: dict[str, int] = {}
        trend_windows: dict[str, AnalyticsWindow] = {}
        trend_values: dict[str, Decimal] = {}
        qualities: dict[str, FeatureQuality] = {}

        for label, window_features in oi.windows.items():
            if not qualifies(window_features.status):
                continue
            qualities[label] = window_features.status.quality

            if window_features.percent_change is not None:
                idx = len(evidence)
                evidence.append(
                    make_evidence(
                        feature_name="open_interest.percent_change",
                        window=label,
                        observed_value=window_features.percent_change,
                        reference_value=None,
                        quality=window_features.status.quality,
                        source_timestamp=snapshot.observation_time,
                        provenance=provenance_label,
                    )
                )
                trend = sign_category(
                    window_features.percent_change,
                    positive=OpenInterestTrend.EXPANDING,
                    negative=OpenInterestTrend.CONTRACTING,
                    zero=OpenInterestTrend.FLAT,
                )
                assert trend is not None
                trends[label] = trend
                trend_evidence[label] = idx
                trend_windows[label] = window_features.window
                trend_values[label] = window_features.percent_change
                observations.append(
                    FlowAnalysisObservation(
                        dimension=AnalysisDimension.OPEN_INTEREST_TREND,
                        window=label,
                        value=trend.value,
                        quality=window_features.status.quality,
                        evidence_refs=(idx,),
                    )
                )

            if window_features.oi_velocity is not None:
                idx = len(evidence)
                evidence.append(
                    make_evidence(
                        feature_name="open_interest.oi_velocity",
                        window=label,
                        observed_value=window_features.oi_velocity,
                        reference_value=None,
                        quality=window_features.status.quality,
                        source_timestamp=snapshot.observation_time,
                        provenance=provenance_label,
                    )
                )
                velocity_trend = sign_category(
                    window_features.oi_velocity,
                    positive=OpenInterestTrend.EXPANDING,
                    negative=OpenInterestTrend.CONTRACTING,
                    zero=OpenInterestTrend.FLAT,
                )
                assert velocity_trend is not None
                observations.append(
                    FlowAnalysisObservation(
                        dimension=AnalysisDimension.OPEN_INTEREST_VELOCITY_TREND,
                        window=label,
                        value=velocity_trend.value,
                        quality=window_features.status.quality,
                        evidence_refs=(idx,),
                    )
                )

        if trends:
            observations.append(
                FlowAnalysisObservation(
                    dimension=AnalysisDimension.PERSISTENCE,
                    value=agreement_of(list(trends.values())).value,
                    quality=worse_of_many(qualities[label] for label in trends),
                    evidence_refs=tuple(trend_evidence.values()),
                )
            )

            pair = shortest_and_longest(trend_windows)
            if pair is None:
                (only_label,) = trend_windows
                observations.append(
                    FlowAnalysisObservation(
                        dimension=AnalysisDimension.MAGNITUDE_TREND,
                        value=OrdinalTrend.INSUFFICIENT_DATA.value,
                        quality=qualities[only_label],
                        evidence_refs=(trend_evidence[only_label],),
                    )
                )
            else:
                short_label, long_label = pair
                trend = ordinal_trend(trend_values[short_label], trend_values[long_label])
                observations.append(
                    FlowAnalysisObservation(
                        dimension=AnalysisDimension.MAGNITUDE_TREND,
                        value=trend.value,
                        quality=worse_of_many([qualities[short_label], qualities[long_label]]),
                        evidence_refs=(trend_evidence[short_label], trend_evidence[long_label]),
                    )
                )

        if not observations:
            return self._abstain(snapshot)

        return FlowAnalysisResult(
            analyst_type=AnalystType.OPEN_INTEREST,
            symbol=snapshot.symbol,
            contract_type=snapshot.contract_type,
            observation_time=snapshot.observation_time,
            windows=snapshot.windows,
            status=AnalystOutcome.ANALYZED,
            observations=tuple(observations),
            evidence=tuple(evidence),
            quality=worse_of_many(observation.quality for observation in observations),
            provenance={"open_interest": provenance_label},
        )

    @staticmethod
    def _abstain(snapshot: FlowFeatureSnapshot) -> FlowAnalysisResult:
        return FlowAnalysisResult(
            analyst_type=AnalystType.OPEN_INTEREST,
            symbol=snapshot.symbol,
            contract_type=snapshot.contract_type,
            observation_time=snapshot.observation_time,
            windows=snapshot.windows,
            status=AnalystOutcome.ABSTAINED,
            quality=FeatureQuality.UNAVAILABLE,
            abstention_reasons=(ABSTENTION_REASON,),
        )


__all__ = ["OpenInterestAnalyst"]

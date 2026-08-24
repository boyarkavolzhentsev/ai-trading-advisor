"""Deterministic Funding Analyst (Stage 2B).

Interprets Stage 2A ``FundingFeatures`` only. ``rolling_stddev`` is carried
as evidence only - no "high/low volatility" label is derived from it since
that would need a reference distribution (abnormality, deferred). No
funding interval is assumed or hardcoded (``time_to_next_funding`` is never
read here); ``FundingFeatures`` itself already never assumes one.
"""

from __future__ import annotations

from app.core.enums.flow_analysis import AnalysisDimension, AnalystOutcome, AnalystType, BasisSign, FundingSign, FundingTrend
from app.core.enums.quality import FeatureQuality
from app.core.models.flow_analysis_result import FlowAnalysisObservation, FlowAnalysisResult
from app.core.models.flow_evidence import FlowEvidence
from app.core.models.flow_feature_snapshot import FlowFeatureSnapshot
from app.flow_analysts.base import make_evidence, qualifies, sign_category, worse_of_many

ABSTENTION_REASON = "no funding observation available"


class FundingAnalyst:
    """Deterministic interpretation of funding-rate and mark/index basis."""

    analyst_type = AnalystType.FUNDING

    def analyze(self, snapshot: FlowFeatureSnapshot) -> FlowAnalysisResult:
        funding = snapshot.funding
        provenance_label = snapshot.provenance.get("funding", "unknown")

        if funding is None or not qualifies(funding.status):
            return self._abstain(snapshot)

        evidence: list[FlowEvidence] = []
        observations: list[FlowAnalysisObservation] = []

        if funding.latest_funding_rate is not None:
            idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="funding.latest_funding_rate",
                    window=None,
                    observed_value=funding.latest_funding_rate,
                    reference_value=None,
                    quality=funding.status.quality,
                    source_timestamp=snapshot.observation_time,
                    provenance=provenance_label,
                )
            )
            sign = sign_category(
                funding.latest_funding_rate,
                positive=FundingSign.POSITIVE,
                negative=FundingSign.NEGATIVE,
                zero=FundingSign.ZERO,
            )
            assert sign is not None
            observations.append(
                FlowAnalysisObservation(
                    dimension=AnalysisDimension.FUNDING_SIGN,
                    value=sign.value,
                    quality=funding.status.quality,
                    evidence_refs=(idx,),
                )
            )

        if funding.mark_index_basis_bps is not None:
            idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="funding.mark_index_basis_bps",
                    window=None,
                    observed_value=funding.mark_index_basis_bps,
                    reference_value=None,
                    quality=funding.status.quality,
                    source_timestamp=snapshot.observation_time,
                    provenance=provenance_label,
                )
            )
            basis = sign_category(
                funding.mark_index_basis_bps,
                positive=BasisSign.MARK_ABOVE_INDEX,
                negative=BasisSign.MARK_BELOW_INDEX,
                zero=BasisSign.AT_PARITY,
            )
            assert basis is not None
            observations.append(
                FlowAnalysisObservation(
                    dimension=AnalysisDimension.BASIS_SIGN,
                    value=basis.value,
                    quality=funding.status.quality,
                    evidence_refs=(idx,),
                )
            )

        for label, window_features in funding.windows.items():
            if not qualifies(window_features.status):
                continue

            if window_features.funding_trend is not None:
                idx = len(evidence)
                evidence.append(
                    make_evidence(
                        feature_name="funding.funding_trend",
                        window=label,
                        observed_value=window_features.funding_trend,
                        reference_value=None,
                        quality=window_features.status.quality,
                        source_timestamp=snapshot.observation_time,
                        provenance=provenance_label,
                    )
                )
                trend = sign_category(
                    window_features.funding_trend,
                    positive=FundingTrend.RISING,
                    negative=FundingTrend.FALLING,
                    zero=FundingTrend.FLAT,
                )
                assert trend is not None
                observations.append(
                    FlowAnalysisObservation(
                        dimension=AnalysisDimension.FUNDING_TREND,
                        window=label,
                        value=trend.value,
                        quality=window_features.status.quality,
                        evidence_refs=(idx,),
                    )
                )

            if window_features.rolling_stddev is not None:
                # evidence only, per approved design - no observation cites it
                evidence.append(
                    make_evidence(
                        feature_name="funding.rolling_stddev",
                        window=label,
                        observed_value=window_features.rolling_stddev,
                        reference_value=None,
                        quality=window_features.status.quality,
                        source_timestamp=snapshot.observation_time,
                        provenance=provenance_label,
                    )
                )

        if not observations:
            return self._abstain(snapshot)

        return FlowAnalysisResult(
            analyst_type=AnalystType.FUNDING,
            symbol=snapshot.symbol,
            contract_type=snapshot.contract_type,
            observation_time=snapshot.observation_time,
            windows=snapshot.windows,
            status=AnalystOutcome.ANALYZED,
            observations=tuple(observations),
            evidence=tuple(evidence),
            quality=worse_of_many(observation.quality for observation in observations),
            provenance={"funding": provenance_label},
        )

    @staticmethod
    def _abstain(snapshot: FlowFeatureSnapshot) -> FlowAnalysisResult:
        return FlowAnalysisResult(
            analyst_type=AnalystType.FUNDING,
            symbol=snapshot.symbol,
            contract_type=snapshot.contract_type,
            observation_time=snapshot.observation_time,
            windows=snapshot.windows,
            status=AnalystOutcome.ABSTAINED,
            quality=FeatureQuality.UNAVAILABLE,
            abstention_reasons=(ABSTENTION_REASON,),
        )


__all__ = ["FundingAnalyst"]

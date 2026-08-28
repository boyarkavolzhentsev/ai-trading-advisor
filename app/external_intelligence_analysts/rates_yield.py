"""Deterministic Rates/Yield Analyst (Stage 4F).

Interprets caller-supplied ``PolicyRateObservation``/``GovernmentYieldObservation``
records only. Every dimension is an exact-zero-boundary sign comparison
between two *compatible* observations - never across providers (a curve
built by mixing two providers' own methodologies for the same tenor would
not be one coherent term structure) and never across currencies/countries.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.core.enums.external_intelligence_analysis import (
    CurveSlopeState,
    CurveSlopeTrend,
    ExternalIntelligenceAnalystType,
    ExternalIntelligenceDimension,
    ExternalIntelligenceOutcome,
    RateTrend,
    RealNominalRelationship,
)
from app.core.enums.rates import GovernmentYieldType
from app.core.models.base import Timestamp
from app.core.models.economic_event import CurrencyCode
from app.core.models.external_intelligence_analysis_result import (
    ExternalIntelligenceAnalysisObservation,
    ExternalIntelligenceAnalysisResult,
)
from app.core.models.external_intelligence_evidence import ExternalIntelligenceEvidence
from app.core.models.government_yield_observation import GovernmentYieldObservation
from app.core.models.policy_rate_observation import PolicyRateObservation
from app.external_intelligence_analysts.base import abstain, classify_quality, make_evidence, sign_category, worse_of_many
from app.external_intelligence_analysts.config import RatesYieldAnalystConfig

ABSTENTION_REASON = "no policy-rate or government-yield observations supplied for this currency"


def _series_trend_observations(
    observations: Sequence[PolicyRateObservation | GovernmentYieldObservation],
    *,
    dimension: ExternalIntelligenceDimension,
    feature_name: str,
    package_label: str,
    analysis_time: Timestamp,
    staleness_threshold,
    evidence: list[ExternalIntelligenceEvidence],
) -> list[ExternalIntelligenceAnalysisObservation]:
    groups: dict[tuple[str, str], list[PolicyRateObservation | GovernmentYieldObservation]] = {}
    for obs in observations:
        if obs.value is None:
            continue
        groups.setdefault((obs.provider, obs.provider_series_id), []).append(obs)

    results: list[ExternalIntelligenceAnalysisObservation] = []
    for (provider, series_id) in sorted(groups):
        members = groups[(provider, series_id)]
        if len(members) < 2:
            continue
        ranked = sorted(members, key=lambda o: o.observation_time)
        previous, current = ranked[-2], ranked[-1]
        previous_quality = classify_quality(previous.observation_time, analysis_time, staleness_threshold)
        current_quality = classify_quality(current.observation_time, analysis_time, staleness_threshold)
        provenance = f"{package_label}:{provider}"

        previous_idx = len(evidence)
        evidence.append(
            make_evidence(
                feature_name=feature_name,
                observed_value=previous.value,
                reference_value=None,
                quality=previous_quality,
                source_timestamp=previous.observation_time,
                source_provider=previous.provider,
                source_record_id=previous.provider_series_id,
                source_received_at=previous.received_at,
                provenance=provenance,
            )
        )
        current_idx = len(evidence)
        evidence.append(
            make_evidence(
                feature_name=feature_name,
                observed_value=current.value,
                reference_value=previous.value,
                quality=current_quality,
                source_timestamp=current.observation_time,
                source_provider=current.provider,
                source_record_id=current.provider_series_id,
                source_received_at=current.received_at,
                provenance=provenance,
            )
        )
        trend = sign_category(
            current.value - previous.value, positive=RateTrend.RISING, negative=RateTrend.FALLING, zero=RateTrend.UNCHANGED
        )
        assert trend is not None
        results.append(
            ExternalIntelligenceAnalysisObservation(
                dimension=dimension,
                value=trend.value,
                quality=worse_of_many([previous_quality, current_quality]),
                subject=f"{provider}:{series_id}",
                evidence_refs=(previous_idx, current_idx),
            )
        )
    return results


class RatesYieldAnalyst:
    """Deterministic interpretation of policy-rate/government-yield level, trend and curve facts."""

    analyst_type = ExternalIntelligenceAnalystType.RATES_YIELD

    def analyze(
        self,
        policy_rates: Sequence[PolicyRateObservation],
        yields: Sequence[GovernmentYieldObservation],
        *,
        currency: CurrencyCode,
        analysis_time: Timestamp,
        config: RatesYieldAnalystConfig,
    ) -> ExternalIntelligenceAnalysisResult:
        if not policy_rates and not yields:
            return abstain(
                ExternalIntelligenceAnalystType.RATES_YIELD,
                analysis_time=analysis_time,
                reason=ABSTENTION_REASON,
                currency=currency,
            )

        evidence: list[ExternalIntelligenceEvidence] = []
        observations: list[ExternalIntelligenceAnalysisObservation] = []

        observations.extend(
            _series_trend_observations(
                policy_rates,
                dimension=ExternalIntelligenceDimension.POLICY_RATE_TREND,
                feature_name="policy_rate_observation.value",
                package_label="app.rates",
                analysis_time=analysis_time,
                staleness_threshold=config.staleness_threshold,
                evidence=evidence,
            )
        )
        observations.extend(
            _series_trend_observations(
                yields,
                dimension=ExternalIntelligenceDimension.YIELD_TREND,
                feature_name="government_yield_observation.value",
                package_label="app.rates",
                analysis_time=analysis_time,
                staleness_threshold=config.staleness_threshold,
                evidence=evidence,
            )
        )

        # CURVE_SLOPE - compatible = same provider, country, currency, yield_type, observation_time.
        slope_groups: dict[tuple[str, str, str, GovernmentYieldType, Timestamp], dict[int, list[GovernmentYieldObservation]]] = {}
        for obs in yields:
            if obs.value is None:
                continue
            key = (obs.provider, obs.country, obs.currency, obs.yield_type, obs.observation_time)
            slope_groups.setdefault(key, {}).setdefault(obs.tenor.total_months, []).append(obs)

        slope_values: dict[tuple, list[tuple[Timestamp, Decimal, int, int]]] = {}
        for key in sorted(slope_groups, key=lambda k: (k[0], k[1], k[2], k[3].value, k[4])):
            provider, country, curr, yield_type, obs_time = key
            by_tenor = slope_groups[key]
            months_sorted = sorted(by_tenor)
            for i in range(len(months_sorted)):
                for j in range(i + 1, len(months_sorted)):
                    short_months, long_months = months_sorted[i], months_sorted[j]
                    for short_obs in by_tenor[short_months]:
                        for long_obs in by_tenor[long_months]:
                            provenance = f"app.rates:{provider}"
                            short_quality = classify_quality(short_obs.observation_time, analysis_time, config.staleness_threshold)
                            long_quality = classify_quality(long_obs.observation_time, analysis_time, config.staleness_threshold)
                            short_idx = len(evidence)
                            evidence.append(
                                make_evidence(
                                    feature_name="government_yield_observation.value",
                                    observed_value=short_obs.value,
                                    reference_value=None,
                                    quality=short_quality,
                                    source_timestamp=short_obs.observation_time,
                                    source_provider=short_obs.provider,
                                    source_record_id=short_obs.provider_series_id,
                                    source_received_at=short_obs.received_at,
                                    provenance=provenance,
                                )
                            )
                            long_idx = len(evidence)
                            evidence.append(
                                make_evidence(
                                    feature_name="government_yield_observation.value",
                                    observed_value=long_obs.value,
                                    reference_value=short_obs.value,
                                    quality=long_quality,
                                    source_timestamp=long_obs.observation_time,
                                    source_provider=long_obs.provider,
                                    source_record_id=long_obs.provider_series_id,
                                    source_received_at=long_obs.received_at,
                                    provenance=provenance,
                                )
                            )
                            slope_value = long_obs.value - short_obs.value
                            slope_state = sign_category(
                                slope_value,
                                positive=CurveSlopeState.NORMAL,
                                negative=CurveSlopeState.INVERTED,
                                zero=CurveSlopeState.FLAT,
                            )
                            assert slope_state is not None
                            subject = f"{provider}:{short_obs.tenor.label}-{long_obs.tenor.label}"
                            observation = ExternalIntelligenceAnalysisObservation(
                                dimension=ExternalIntelligenceDimension.CURVE_SLOPE,
                                value=slope_state.value,
                                quality=worse_of_many([short_quality, long_quality]),
                                subject=subject,
                                evidence_refs=(short_idx, long_idx),
                            )
                            observations.append(observation)
                            trend_key = (provider, country, curr, yield_type, short_months, long_months)
                            slope_values.setdefault(trend_key, []).append((obs_time, slope_value, short_idx, long_idx))  # type: ignore[arg-type]

        # CURVE_SLOPE_TREND - same compatible tenor pair, two different observation times.
        for trend_key in sorted(slope_values, key=lambda k: (k[0], k[1], k[2], k[3].value, k[4], k[5])):
            entries = sorted(slope_values[trend_key], key=lambda e: e[0])
            if len(entries) < 2:
                continue
            (time_prev, slope_prev, prev_short_idx, prev_long_idx), (time_curr, slope_curr, curr_short_idx, curr_long_idx) = (
                entries[-2],
                entries[-1],
            )
            provider, country, curr_code, yield_type, short_months, long_months = trend_key
            delta = slope_curr - slope_prev
            trend = sign_category(
                delta, positive=CurveSlopeTrend.STEEPENING, negative=CurveSlopeTrend.FLATTENING, zero=CurveSlopeTrend.UNCHANGED
            )
            assert trend is not None
            quality = worse_of_many(
                [evidence[prev_short_idx].quality, evidence[prev_long_idx].quality, evidence[curr_short_idx].quality, evidence[curr_long_idx].quality]
            )
            observations.append(
                ExternalIntelligenceAnalysisObservation(
                    dimension=ExternalIntelligenceDimension.CURVE_SLOPE_TREND,
                    value=trend.value,
                    quality=quality,
                    subject=f"{provider}:{yield_type.value}:tenor{short_months}-{long_months}",
                    evidence_refs=(prev_short_idx, prev_long_idx, curr_short_idx, curr_long_idx),
                )
            )

        # REAL_NOMINAL_RELATIONSHIP - same provider, country, currency, tenor, observation_time, different yield_type.
        real_nominal_groups: dict[tuple, dict[GovernmentYieldType, GovernmentYieldObservation]] = {}
        for obs in yields:
            if obs.value is None:
                continue
            key = (obs.provider, obs.country, obs.currency, obs.tenor.total_months, obs.observation_time)
            real_nominal_groups.setdefault(key, {})[obs.yield_type] = obs

        for key in sorted(real_nominal_groups, key=lambda k: (k[0], k[1], k[2], k[3], k[4])):
            by_type = real_nominal_groups[key]
            if GovernmentYieldType.NOMINAL not in by_type or GovernmentYieldType.REAL not in by_type:
                continue
            nominal_obs = by_type[GovernmentYieldType.NOMINAL]
            real_obs = by_type[GovernmentYieldType.REAL]
            provenance = f"app.rates:{nominal_obs.provider}"
            nominal_quality = classify_quality(nominal_obs.observation_time, analysis_time, config.staleness_threshold)
            real_quality = classify_quality(real_obs.observation_time, analysis_time, config.staleness_threshold)
            nominal_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="government_yield_observation.value",
                    observed_value=nominal_obs.value,
                    reference_value=real_obs.value,
                    quality=nominal_quality,
                    source_timestamp=nominal_obs.observation_time,
                    source_provider=nominal_obs.provider,
                    source_record_id=nominal_obs.provider_series_id,
                    source_received_at=nominal_obs.received_at,
                    provenance=provenance,
                )
            )
            real_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="government_yield_observation.value",
                    observed_value=real_obs.value,
                    reference_value=nominal_obs.value,
                    quality=real_quality,
                    source_timestamp=real_obs.observation_time,
                    source_provider=real_obs.provider,
                    source_record_id=real_obs.provider_series_id,
                    source_received_at=real_obs.received_at,
                    provenance=provenance,
                )
            )
            relationship = sign_category(
                nominal_obs.value - real_obs.value,
                positive=RealNominalRelationship.NOMINAL_ABOVE_REAL,
                negative=RealNominalRelationship.NOMINAL_BELOW_REAL,
                zero=RealNominalRelationship.AT_PARITY,
            )
            assert relationship is not None
            observations.append(
                ExternalIntelligenceAnalysisObservation(
                    dimension=ExternalIntelligenceDimension.REAL_NOMINAL_RELATIONSHIP,
                    value=relationship.value,
                    quality=worse_of_many([nominal_quality, real_quality]),
                    subject=f"{nominal_obs.provider}:{nominal_obs.tenor.label}",
                    evidence_refs=(nominal_idx, real_idx),
                )
            )

        if not observations:
            return abstain(
                ExternalIntelligenceAnalystType.RATES_YIELD,
                analysis_time=analysis_time,
                reason=ABSTENTION_REASON,
                currency=currency,
            )

        return ExternalIntelligenceAnalysisResult(
            analyst_type=ExternalIntelligenceAnalystType.RATES_YIELD,
            currency=currency,
            analysis_time=analysis_time,
            status=ExternalIntelligenceOutcome.ANALYZED,
            observations=tuple(observations),
            evidence=tuple(evidence),
            quality=worse_of_many([observation.quality for observation in observations]),
        )


__all__ = ["RatesYieldAnalyst"]

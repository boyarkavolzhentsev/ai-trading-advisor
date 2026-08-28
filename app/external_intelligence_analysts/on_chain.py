"""Deterministic On-Chain Analyst (Stage 4F).

Interprets caller-supplied ``NetworkActivityObservation``/``SupplyObservation``/
``ExchangeFlowObservation``/``StablecoinSupplyObservation`` records for one
``(asset, network)`` scope only - no cross-asset, cross-network or
cross-exchange aggregation of any kind, and no global liquidity conclusion.
Stablecoin facts are analyzed here, not by a separate analyst, since they
already share this exact scope shape - see the Stage 4F design report.

When both ``active_addresses`` and ``transaction_count`` trends are
independently computable and disagree, both are retained as separate
``ACTIVITY_TREND`` observations (subject-tagged by metric) rather than one
metric being arbitrarily preferred.

``ACTIVITY_TREND`` and ``EXCHANGE_NET_FLOW`` are deliberately never combined
into a relationship/agreement dimension: no factually-grounded deterministic
relationship between network-activity direction and exchange-flow direction
exists in the Stage 4A-4E foundations - either combination (e.g. increasing
activity with net inflow, or increasing activity with net outflow) can occur
for many unrelated reasons, so mapping them onto AGREEMENT/DIVERGENCE would
be a market-semantic assumption, not a deterministic transformation of
facts. The two dimensions are reported independently; any relationship
between them is left to a future, separately reviewed analytical model.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import timedelta

from app.core.enums.external_intelligence_analysis import (
    ExchangeNetFlowState,
    ExternalIntelligenceAnalystType,
    ExternalIntelligenceDimension,
    ExternalIntelligenceOutcome,
    StablecoinNetIssuanceState,
    TrendDirection,
)
from app.core.models.base import Timestamp
from app.core.models.exchange_flow_observation import ExchangeFlowObservation
from app.core.models.external_intelligence_analysis_result import (
    ExternalIntelligenceAnalysisObservation,
    ExternalIntelligenceAnalysisResult,
)
from app.core.models.external_intelligence_evidence import ExternalIntelligenceEvidence
from app.core.models.instrument import Asset
from app.core.models.network_activity_observation import NetworkActivityObservation
from app.core.models.stablecoin_supply_observation import StablecoinSupplyObservation
from app.core.models.supply_observation import SupplyObservation
from app.external_intelligence_analysts.base import abstain, classify_quality, make_evidence, sign_category, worse_of_many
from app.external_intelligence_analysts.config import OnChainAnalystConfig

ABSTENTION_REASON = "no on-chain observations supplied for this asset/network"
NO_ANALYZABLE_DIMENSION_REASON = "no compatible pair of observations for any on-chain dimension"


def _trend_entries(
    items: Sequence[object],
    *,
    group_key_fn: Callable[[object], tuple[str | None, ...]],
    metric_getter: Callable[[object], object],
    metric_name: str,
    dimension: ExternalIntelligenceDimension,
    package_label: str,
    analysis_time: Timestamp,
    staleness_threshold: timedelta,
    evidence: list[ExternalIntelligenceEvidence],
) -> list[tuple[ExternalIntelligenceAnalysisObservation, Timestamp]]:
    groups: dict[tuple[str | None, ...], list[object]] = {}
    for item in items:
        value = metric_getter(item)
        if value is None:
            continue
        groups.setdefault(group_key_fn(item), []).append(item)

    results: list[tuple[ExternalIntelligenceAnalysisObservation, Timestamp]] = []
    for key in sorted(groups, key=lambda k: tuple(part or "" for part in k)):
        members = groups[key]
        if len(members) < 2:
            continue
        ranked = sorted(members, key=lambda o: o.observation_time)
        previous, current = ranked[-2], ranked[-1]
        previous_value, current_value = metric_getter(previous), metric_getter(current)
        previous_quality = classify_quality(previous.observation_time, analysis_time, staleness_threshold)
        current_quality = classify_quality(current.observation_time, analysis_time, staleness_threshold)
        provenance = f"{package_label}:{previous.provider}"

        previous_idx = len(evidence)
        evidence.append(
            make_evidence(
                feature_name=f"{metric_name}",
                observed_value=previous_value,
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
                feature_name=f"{metric_name}",
                observed_value=current_value,
                reference_value=previous_value,
                quality=current_quality,
                source_timestamp=current.observation_time,
                source_provider=current.provider,
                source_record_id=current.provider_series_id,
                source_received_at=current.received_at,
                provenance=provenance,
            )
        )
        trend = sign_category(
            current_value - previous_value,
            positive=TrendDirection.INCREASING,
            negative=TrendDirection.DECREASING,
            zero=TrendDirection.UNCHANGED,
        )
        assert trend is not None
        subject = ":".join(part for part in key if part) + f":{metric_name}"
        observation = ExternalIntelligenceAnalysisObservation(
            dimension=dimension,
            value=trend.value,
            quality=worse_of_many([previous_quality, current_quality]),
            subject=subject,
            evidence_refs=(previous_idx, current_idx),
        )
        results.append((observation, current.observation_time))
    return results


class OnChainAnalyst:
    """Deterministic interpretation of network-activity/supply/exchange-flow/stablecoin facts."""

    analyst_type = ExternalIntelligenceAnalystType.ON_CHAIN

    def analyze(
        self,
        network_activity: Sequence[NetworkActivityObservation],
        supply: Sequence[SupplyObservation],
        exchange_flows: Sequence[ExchangeFlowObservation],
        stablecoin_supply: Sequence[StablecoinSupplyObservation],
        *,
        asset: Asset,
        network: str,
        analysis_time: Timestamp,
        config: OnChainAnalystConfig,
    ) -> ExternalIntelligenceAnalysisResult:
        if not network_activity and not supply and not exchange_flows and not stablecoin_supply:
            return abstain(
                ExternalIntelligenceAnalystType.ON_CHAIN,
                analysis_time=analysis_time,
                reason=ABSTENTION_REASON,
                asset=asset,
                network=network,
            )

        evidence: list[ExternalIntelligenceEvidence] = []
        observations: list[ExternalIntelligenceAnalysisObservation] = []

        activity_key = lambda o: (o.provider, o.provider_series_id)  # noqa: E731

        active_addr_entries = _trend_entries(
            network_activity,
            group_key_fn=activity_key,
            metric_getter=lambda o: o.active_addresses,
            metric_name="network_activity_observation.active_addresses",
            dimension=ExternalIntelligenceDimension.ACTIVITY_TREND,
            package_label="app.onchain",
            analysis_time=analysis_time,
            staleness_threshold=config.staleness_threshold,
            evidence=evidence,
        )
        tx_count_entries = _trend_entries(
            network_activity,
            group_key_fn=activity_key,
            metric_getter=lambda o: o.transaction_count,
            metric_name="network_activity_observation.transaction_count",
            dimension=ExternalIntelligenceDimension.ACTIVITY_TREND,
            package_label="app.onchain",
            analysis_time=analysis_time,
            staleness_threshold=config.staleness_threshold,
            evidence=evidence,
        )
        observations.extend(obs for obs, _ in active_addr_entries)
        observations.extend(obs for obs, _ in tx_count_entries)

        supply_key = lambda o: (o.provider, o.provider_series_id)  # noqa: E731
        for metric_name, metric_getter in (
            ("supply_observation.total_supply", lambda o: o.total_supply),
            ("supply_observation.circulating_supply", lambda o: o.circulating_supply),
        ):
            observations.extend(
                obs
                for obs, _ in _trend_entries(
                    supply,
                    group_key_fn=supply_key,
                    metric_getter=metric_getter,
                    metric_name=metric_name,
                    dimension=ExternalIntelligenceDimension.SUPPLY_TREND,
                    package_label="app.onchain",
                    analysis_time=analysis_time,
                    staleness_threshold=config.staleness_threshold,
                    evidence=evidence,
                )
            )

        for metric_name, metric_getter in (
            ("stablecoin_supply_observation.total_supply", lambda o: o.total_supply),
            ("stablecoin_supply_observation.circulating_supply", lambda o: o.circulating_supply),
        ):
            observations.extend(
                obs
                for obs, _ in _trend_entries(
                    stablecoin_supply,
                    group_key_fn=supply_key,
                    metric_getter=metric_getter,
                    metric_name=metric_name,
                    dimension=ExternalIntelligenceDimension.STABLECOIN_SUPPLY_TREND,
                    package_label="app.onchain",
                    analysis_time=analysis_time,
                    staleness_threshold=config.staleness_threshold,
                    evidence=evidence,
                )
            )

        exchange_balance_key = lambda o: (o.provider, o.provider_series_id, o.exchange)  # noqa: E731
        observations.extend(
            obs
            for obs, _ in _trend_entries(
                exchange_flows,
                group_key_fn=exchange_balance_key,
                metric_getter=lambda o: o.balance,
                metric_name="exchange_flow_observation.balance",
                dimension=ExternalIntelligenceDimension.EXCHANGE_BALANCE_TREND,
                package_label="app.onchain",
                analysis_time=analysis_time,
                staleness_threshold=config.staleness_threshold,
                evidence=evidence,
            )
        )

        for flow in sorted(
            exchange_flows, key=lambda o: (o.provider, o.provider_series_id, o.exchange or "", o.observation_time)
        ):
            if flow.inflow is None or flow.outflow is None:
                continue
            quality = classify_quality(flow.observation_time, analysis_time, config.staleness_threshold)
            provenance = f"app.onchain:{flow.provider}"
            inflow_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="exchange_flow_observation.inflow",
                    observed_value=flow.inflow,
                    reference_value=flow.outflow,
                    quality=quality,
                    source_timestamp=flow.observation_time,
                    source_provider=flow.provider,
                    source_record_id=flow.provider_series_id,
                    source_received_at=flow.received_at,
                    provenance=provenance,
                )
            )
            outflow_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="exchange_flow_observation.outflow",
                    observed_value=flow.outflow,
                    reference_value=flow.inflow,
                    quality=quality,
                    source_timestamp=flow.observation_time,
                    source_provider=flow.provider,
                    source_record_id=flow.provider_series_id,
                    source_received_at=flow.received_at,
                    provenance=provenance,
                )
            )
            net_flow = sign_category(
                flow.inflow - flow.outflow,
                positive=ExchangeNetFlowState.NET_INFLOW,
                negative=ExchangeNetFlowState.NET_OUTFLOW,
                zero=ExchangeNetFlowState.BALANCED,
            )
            assert net_flow is not None
            subject = f"{flow.provider}:{flow.provider_series_id}:{flow.exchange or 'aggregate'}"
            observation = ExternalIntelligenceAnalysisObservation(
                dimension=ExternalIntelligenceDimension.EXCHANGE_NET_FLOW,
                value=net_flow.value,
                quality=quality,
                subject=subject,
                evidence_refs=(inflow_idx, outflow_idx),
            )
            observations.append(observation)

        for stablecoin in sorted(stablecoin_supply, key=lambda o: (o.provider, o.provider_series_id, o.observation_time)):
            if stablecoin.mint_amount is None or stablecoin.burn_amount is None:
                continue
            quality = classify_quality(stablecoin.observation_time, analysis_time, config.staleness_threshold)
            provenance = f"app.onchain:{stablecoin.provider}"
            mint_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="stablecoin_supply_observation.mint_amount",
                    observed_value=stablecoin.mint_amount,
                    reference_value=stablecoin.burn_amount,
                    quality=quality,
                    source_timestamp=stablecoin.observation_time,
                    source_provider=stablecoin.provider,
                    source_record_id=stablecoin.provider_series_id,
                    source_received_at=stablecoin.received_at,
                    provenance=provenance,
                )
            )
            burn_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="stablecoin_supply_observation.burn_amount",
                    observed_value=stablecoin.burn_amount,
                    reference_value=stablecoin.mint_amount,
                    quality=quality,
                    source_timestamp=stablecoin.observation_time,
                    source_provider=stablecoin.provider,
                    source_record_id=stablecoin.provider_series_id,
                    source_received_at=stablecoin.received_at,
                    provenance=provenance,
                )
            )
            issuance = sign_category(
                stablecoin.mint_amount - stablecoin.burn_amount,
                positive=StablecoinNetIssuanceState.NET_MINT,
                negative=StablecoinNetIssuanceState.NET_BURN,
                zero=StablecoinNetIssuanceState.BALANCED,
            )
            assert issuance is not None
            observations.append(
                ExternalIntelligenceAnalysisObservation(
                    dimension=ExternalIntelligenceDimension.STABLECOIN_NET_ISSUANCE,
                    value=issuance.value,
                    quality=quality,
                    subject=f"{stablecoin.provider}:{stablecoin.provider_series_id}",
                    evidence_refs=(mint_idx, burn_idx),
                )
            )

        if not observations:
            return abstain(
                ExternalIntelligenceAnalystType.ON_CHAIN,
                analysis_time=analysis_time,
                reason=NO_ANALYZABLE_DIMENSION_REASON,
                asset=asset,
                network=network,
            )

        return ExternalIntelligenceAnalysisResult(
            analyst_type=ExternalIntelligenceAnalystType.ON_CHAIN,
            asset=asset,
            network=network,
            analysis_time=analysis_time,
            status=ExternalIntelligenceOutcome.ANALYZED,
            observations=tuple(observations),
            evidence=tuple(evidence),
            quality=worse_of_many([observation.quality for observation in observations]),
        )


__all__ = ["OnChainAnalyst"]

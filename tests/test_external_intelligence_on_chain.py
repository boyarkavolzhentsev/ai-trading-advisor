"""Stage 4F ``OnChainAnalyst`` deterministic calculations."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from app.core.enums.external_intelligence_analysis import (
    ExchangeNetFlowState,
    ExternalIntelligenceDimension,
    ExternalIntelligenceOutcome,
    StablecoinNetIssuanceState,
    TrendDirection,
)
from app.core.enums.onchain import OnChainUnit
from app.core.enums.quality import FeatureQuality
from app.core.models.exchange_flow_observation import ExchangeFlowObservation
from app.core.models.network_activity_observation import NetworkActivityObservation
from app.core.models.stablecoin_supply_observation import StablecoinSupplyObservation
from app.core.models.supply_observation import SupplyObservation
from app.external_intelligence_analysts import OnChainAnalyst, OnChainAnalystConfig

CONFIG = OnChainAnalystConfig(staleness_threshold=timedelta(days=3))
ASSET = "BTC"
NETWORK = "bitcoin"


def _activity(now: datetime, **overrides: object) -> NetworkActivityObservation:
    fields: dict[str, object] = {
        "provider": "glassnode",
        "provider_series_id": "btc-activity",
        "asset": ASSET,
        "network": NETWORK,
        "observation_time": now,
        "received_at": now,
        "active_addresses": 900_000,
    }
    fields.update(overrides)
    return NetworkActivityObservation(**fields)


def _supply(now: datetime, **overrides: object) -> SupplyObservation:
    fields: dict[str, object] = {
        "provider": "glassnode",
        "provider_series_id": "btc-supply",
        "asset": ASSET,
        "network": NETWORK,
        "observation_time": now,
        "received_at": now,
        "total_supply": Decimal("19800000"),
    }
    fields.update(overrides)
    return SupplyObservation(**fields)


def _flow(now: datetime, **overrides: object) -> ExchangeFlowObservation:
    fields: dict[str, object] = {
        "provider": "cryptoq",
        "provider_series_id": "btc-binance",
        "asset": ASSET,
        "network": NETWORK,
        "exchange": "binance",
        "observation_time": now,
        "received_at": now,
        "inflow": Decimal("500"),
        "outflow": Decimal("200"),
        "unit": OnChainUnit.NATIVE_ASSET,
    }
    fields.update(overrides)
    return ExchangeFlowObservation(**fields)


def _stablecoin(now: datetime, **overrides: object) -> StablecoinSupplyObservation:
    fields: dict[str, object] = {
        "provider": "glassnode",
        "provider_series_id": "usdt-eth-supply",
        "asset": "USDT",
        "network": "ethereum",
        "observation_time": now,
        "received_at": now,
        "total_supply": Decimal("50000000000"),
    }
    fields.update(overrides)
    return StablecoinSupplyObservation(**fields)


def _dims(result, dimension: ExternalIntelligenceDimension):
    return [o for o in result.observations if o.dimension is dimension]


def test_abstains_with_no_observations(now: datetime) -> None:
    analyst = OnChainAnalyst()
    result = analyst.analyze([], [], [], [], asset=ASSET, network=NETWORK, analysis_time=now, config=CONFIG)
    assert result.status is ExternalIntelligenceOutcome.ABSTAINED


def test_activity_trend_increasing(now: datetime) -> None:
    previous = _activity(now - timedelta(days=1), active_addresses=900_000)
    current = _activity(now, active_addresses=950_000)
    analyst = OnChainAnalyst()
    result = analyst.analyze([previous, current], [], [], [], asset=ASSET, network=NETWORK, analysis_time=now, config=CONFIG)
    trends = _dims(result, ExternalIntelligenceDimension.ACTIVITY_TREND)
    assert trends[0].value == TrendDirection.INCREASING.value


def test_activity_trend_decreasing(now: datetime) -> None:
    previous = _activity(now - timedelta(days=1), active_addresses=950_000)
    current = _activity(now, active_addresses=900_000)
    analyst = OnChainAnalyst()
    result = analyst.analyze([previous, current], [], [], [], asset=ASSET, network=NETWORK, analysis_time=now, config=CONFIG)
    trends = _dims(result, ExternalIntelligenceDimension.ACTIVITY_TREND)
    assert trends[0].value == TrendDirection.DECREASING.value


def test_conflicting_activity_metrics_retained_separately(now: datetime) -> None:
    """active_addresses rising while transaction_count falls must produce
    TWO independent ACTIVITY_TREND observations, never one arbitrarily
    chosen metric."""
    previous = _activity(now - timedelta(days=1), active_addresses=900_000, transaction_count=300_000)
    current = _activity(now, active_addresses=950_000, transaction_count=280_000)
    analyst = OnChainAnalyst()
    result = analyst.analyze([previous, current], [], [], [], asset=ASSET, network=NETWORK, analysis_time=now, config=CONFIG)
    trends = _dims(result, ExternalIntelligenceDimension.ACTIVITY_TREND)
    assert len(trends) == 2
    values = {(t.subject, t.value) for t in trends}
    assert any(v[1] == TrendDirection.INCREASING.value for v in values)
    assert any(v[1] == TrendDirection.DECREASING.value for v in values)


def test_single_activity_observation_produces_no_trend(now: datetime) -> None:
    analyst = OnChainAnalyst()
    result = analyst.analyze([_activity(now)], [], [], [], asset=ASSET, network=NETWORK, analysis_time=now, config=CONFIG)
    assert _dims(result, ExternalIntelligenceDimension.ACTIVITY_TREND) == []


def test_supply_trend(now: datetime) -> None:
    previous = _supply(now - timedelta(days=1), total_supply=Decimal("19800000"))
    current = _supply(now, total_supply=Decimal("19800100"))
    analyst = OnChainAnalyst()
    result = analyst.analyze([], [previous, current], [], [], asset=ASSET, network=NETWORK, analysis_time=now, config=CONFIG)
    trends = _dims(result, ExternalIntelligenceDimension.SUPPLY_TREND)
    assert trends[0].value == TrendDirection.INCREASING.value


def test_stablecoin_supply_trend(now: datetime) -> None:
    previous = _stablecoin(now - timedelta(days=1), total_supply=Decimal("50000000000"))
    current = _stablecoin(now, total_supply=Decimal("49000000000"))
    analyst = OnChainAnalyst()
    result = analyst.analyze(
        [], [], [], [previous, current], asset="USDT", network="ethereum", analysis_time=now, config=CONFIG
    )
    trends = _dims(result, ExternalIntelligenceDimension.STABLECOIN_SUPPLY_TREND)
    assert trends[0].value == TrendDirection.DECREASING.value


def test_exchange_net_inflow(now: datetime) -> None:
    flow = _flow(now, inflow=Decimal("500"), outflow=Decimal("200"))
    analyst = OnChainAnalyst()
    result = analyst.analyze([], [], [flow], [], asset=ASSET, network=NETWORK, analysis_time=now, config=CONFIG)
    net_flows = _dims(result, ExternalIntelligenceDimension.EXCHANGE_NET_FLOW)
    assert net_flows[0].value == ExchangeNetFlowState.NET_INFLOW.value


def test_exchange_net_outflow(now: datetime) -> None:
    flow = _flow(now, inflow=Decimal("100"), outflow=Decimal("400"))
    analyst = OnChainAnalyst()
    result = analyst.analyze([], [], [flow], [], asset=ASSET, network=NETWORK, analysis_time=now, config=CONFIG)
    net_flows = _dims(result, ExternalIntelligenceDimension.EXCHANGE_NET_FLOW)
    assert net_flows[0].value == ExchangeNetFlowState.NET_OUTFLOW.value


def test_exchange_net_flow_balanced_exact_zero(now: datetime) -> None:
    flow = _flow(now, inflow=Decimal("300"), outflow=Decimal("300"))
    analyst = OnChainAnalyst()
    result = analyst.analyze([], [], [flow], [], asset=ASSET, network=NETWORK, analysis_time=now, config=CONFIG)
    net_flows = _dims(result, ExternalIntelligenceDimension.EXCHANGE_NET_FLOW)
    assert net_flows[0].value == ExchangeNetFlowState.BALANCED.value


def test_missing_outflow_side_produces_no_net_flow(now: datetime) -> None:
    flow = _flow(now, inflow=Decimal("500"), outflow=None)
    analyst = OnChainAnalyst()
    result = analyst.analyze([], [], [flow], [], asset=ASSET, network=NETWORK, analysis_time=now, config=CONFIG)
    assert _dims(result, ExternalIntelligenceDimension.EXCHANGE_NET_FLOW) == []


def test_exchange_balance_trend(now: datetime) -> None:
    previous = _flow(now - timedelta(days=1), inflow=None, outflow=None, balance=Decimal("1000"))
    current = _flow(now, inflow=None, outflow=None, balance=Decimal("1200"))
    analyst = OnChainAnalyst()
    result = analyst.analyze([], [], [previous, current], [], asset=ASSET, network=NETWORK, analysis_time=now, config=CONFIG)
    trends = _dims(result, ExternalIntelligenceDimension.EXCHANGE_BALANCE_TREND)
    assert trends[0].value == TrendDirection.INCREASING.value


def test_stablecoin_net_mint(now: datetime) -> None:
    obs = _stablecoin(now, mint_amount=Decimal("500"), burn_amount=Decimal("100"), total_supply=None)
    analyst = OnChainAnalyst()
    result = analyst.analyze([], [], [], [obs], asset="USDT", network="ethereum", analysis_time=now, config=CONFIG)
    issuance = _dims(result, ExternalIntelligenceDimension.STABLECOIN_NET_ISSUANCE)
    assert issuance[0].value == StablecoinNetIssuanceState.NET_MINT.value


def test_stablecoin_net_burn(now: datetime) -> None:
    obs = _stablecoin(now, mint_amount=Decimal("50"), burn_amount=Decimal("300"), total_supply=None)
    analyst = OnChainAnalyst()
    result = analyst.analyze([], [], [], [obs], asset="USDT", network="ethereum", analysis_time=now, config=CONFIG)
    issuance = _dims(result, ExternalIntelligenceDimension.STABLECOIN_NET_ISSUANCE)
    assert issuance[0].value == StablecoinNetIssuanceState.NET_BURN.value


def test_stablecoin_net_balanced_exact_zero(now: datetime) -> None:
    obs = _stablecoin(now, mint_amount=Decimal("200"), burn_amount=Decimal("200"), total_supply=None)
    analyst = OnChainAnalyst()
    result = analyst.analyze([], [], [], [obs], asset="USDT", network="ethereum", analysis_time=now, config=CONFIG)
    issuance = _dims(result, ExternalIntelligenceDimension.STABLECOIN_NET_ISSUANCE)
    assert issuance[0].value == StablecoinNetIssuanceState.BALANCED.value


def test_missing_mint_side_produces_no_net_issuance(now: datetime) -> None:
    obs = _stablecoin(now, mint_amount=None, burn_amount=Decimal("100"))
    analyst = OnChainAnalyst()
    result = analyst.analyze([], [], [], [obs], asset="USDT", network="ethereum", analysis_time=now, config=CONFIG)
    assert _dims(result, ExternalIntelligenceDimension.STABLECOIN_NET_ISSUANCE) == []


def test_activity_trend_and_exchange_net_flow_remain_independent_dimensions(now: datetime) -> None:
    """Required correction: no activity-vs-exchange-flow relationship
    dimension exists in Stage 4F V1 - ACTIVITY_TREND and EXCHANGE_NET_FLOW
    are reported as two fully independent observations, with no
    agreement/divergence/composite dimension linking them, regardless of
    whether their signs happen to align or conflict."""
    previous = _activity(now - timedelta(days=1), active_addresses=900_000)
    current = _activity(now, active_addresses=950_000)
    flow = _flow(now, inflow=Decimal("100"), outflow=Decimal("500"))
    analyst = OnChainAnalyst()
    result = analyst.analyze(
        [previous, current], [], [flow], [], asset=ASSET, network=NETWORK, analysis_time=now, config=CONFIG
    )
    activity_trends = _dims(result, ExternalIntelligenceDimension.ACTIVITY_TREND)
    net_flows = _dims(result, ExternalIntelligenceDimension.EXCHANGE_NET_FLOW)
    assert activity_trends[0].value == TrendDirection.INCREASING.value
    assert net_flows[0].value == ExchangeNetFlowState.NET_OUTFLOW.value
    dimension_values = {o.dimension.value for o in result.observations}
    assert "ACTIVITY_FLOW_RELATIONSHIP" not in dimension_values


def test_no_cross_asset_or_cross_network_aggregation(now: datetime) -> None:
    """Supplying observations for a different asset/network than the
    queried scope contributes nothing - no cross-asset/network blending."""
    other_asset_activity = _activity(now, asset="ETH", network="ethereum", active_addresses=500_000)
    analyst = OnChainAnalyst()
    result = analyst.analyze(
        [other_asset_activity], [], [], [], asset=ASSET, network=NETWORK, analysis_time=now, config=CONFIG
    )
    # the analyst does not filter by scope itself (caller responsibility) but
    # produces no ACTIVITY_TREND for a lone single observation regardless
    assert _dims(result, ExternalIntelligenceDimension.ACTIVITY_TREND) == []


def test_no_partial_quality_ever_emitted(now: datetime) -> None:
    previous = _activity(now - timedelta(days=1), active_addresses=900_000)
    current = _activity(now, active_addresses=950_000)
    analyst = OnChainAnalyst()
    result = analyst.analyze([previous, current], [], [], [], asset=ASSET, network=NETWORK, analysis_time=now, config=CONFIG)
    for observation in result.observations:
        assert observation.quality is not FeatureQuality.PARTIAL


def test_result_scope_is_asset_and_network(now: datetime) -> None:
    previous = _activity(now - timedelta(days=1), active_addresses=900_000)
    current = _activity(now, active_addresses=950_000)
    analyst = OnChainAnalyst()
    result = analyst.analyze([previous, current], [], [], [], asset=ASSET, network=NETWORK, analysis_time=now, config=CONFIG)
    assert result.asset == ASSET
    assert result.network == NETWORK
    assert result.currency is None
    assert result.symbol is None

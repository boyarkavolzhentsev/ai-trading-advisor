"""Determinism: identical inputs produce identical, order-independent results."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.core.models.exchange_flow_observation import ExchangeFlowObservation
from app.core.models.network_activity_observation import NetworkActivityObservation
from app.core.models.stablecoin_supply_observation import StablecoinSupplyObservation
from app.core.models.supply_observation import SupplyObservation
from app.core.enums.onchain import OnChainUnit


def test_network_activity_construction_is_deterministic(now: datetime) -> None:
    fields = dict(
        provider="glassnode",
        provider_series_id="btc-active-addresses",
        asset="BTC",
        network="bitcoin",
        observation_time=now,
        received_at=now,
        active_addresses=950_000,
    )
    first = NetworkActivityObservation(**fields)
    second = NetworkActivityObservation(**fields)
    assert first == second
    assert first.model_dump() == second.model_dump()


def test_supply_construction_is_deterministic(now: datetime) -> None:
    fields = dict(
        provider="glassnode",
        provider_series_id="btc-supply",
        asset="BTC",
        network="bitcoin",
        observation_time=now,
        received_at=now,
        total_supply=Decimal("19800000"),
    )
    first = SupplyObservation(**fields)
    second = SupplyObservation(**fields)
    assert first == second
    assert first.model_dump() == second.model_dump()


def test_exchange_flow_construction_is_deterministic(now: datetime) -> None:
    fields = dict(
        provider="cryptoq",
        provider_series_id="btc-binance-inflow",
        asset="BTC",
        network="bitcoin",
        exchange="binance",
        observation_time=now,
        received_at=now,
        inflow=Decimal("120.5"),
        unit=OnChainUnit.NATIVE_ASSET,
    )
    first = ExchangeFlowObservation(**fields)
    second = ExchangeFlowObservation(**fields)
    assert first == second
    assert first.model_dump() == second.model_dump()


def test_stablecoin_supply_construction_is_deterministic(now: datetime) -> None:
    fields = dict(
        provider="glassnode",
        provider_series_id="usdt-eth-supply",
        asset="USDT",
        network="ethereum",
        observation_time=now,
        received_at=now,
        total_supply=Decimal("50000000000"),
    )
    first = StablecoinSupplyObservation(**fields)
    second = StablecoinSupplyObservation(**fields)
    assert first == second
    assert first.model_dump() == second.model_dump()

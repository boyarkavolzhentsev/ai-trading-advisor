"""Stage 4E ``OnChainProvider`` structural protocol conformance."""

from __future__ import annotations

from datetime import datetime

from app.core.models.exchange_flow_observation import ExchangeFlowObservation
from app.core.models.network_activity_observation import NetworkActivityObservation
from app.core.models.stablecoin_supply_observation import StablecoinSupplyObservation
from app.core.models.supply_observation import SupplyObservation
from app.onchain.protocols import DEFAULT_ONCHAIN_LIMIT, OnChainProvider


class _ConformingProvider:
    def get_network_activity(
        self, asset: str, network: str, start: datetime, end: datetime, *, limit: int = DEFAULT_ONCHAIN_LIMIT
    ) -> list[NetworkActivityObservation]:
        return []

    def get_supply(
        self, asset: str, network: str, start: datetime, end: datetime, *, limit: int = DEFAULT_ONCHAIN_LIMIT
    ) -> list[SupplyObservation]:
        return []

    def get_exchange_flows(
        self,
        asset: str,
        network: str,
        start: datetime,
        end: datetime,
        *,
        exchange: str | None = None,
        limit: int = DEFAULT_ONCHAIN_LIMIT,
    ) -> list[ExchangeFlowObservation]:
        return []

    def get_stablecoin_supply(
        self, asset: str, network: str, start: datetime, end: datetime, *, limit: int = DEFAULT_ONCHAIN_LIMIT
    ) -> list[StablecoinSupplyObservation]:
        return []


class _PartialProvider:
    def get_network_activity(
        self, asset: str, network: str, start: datetime, end: datetime, *, limit: int = DEFAULT_ONCHAIN_LIMIT
    ) -> list[NetworkActivityObservation]:
        return []


class _NonConformingProvider:
    def some_other_method(self) -> None:
        pass


def test_conforming_provider_satisfies_protocol() -> None:
    assert isinstance(_ConformingProvider(), OnChainProvider)


def test_partial_provider_does_not_satisfy_protocol() -> None:
    assert not isinstance(_PartialProvider(), OnChainProvider)


def test_non_conforming_provider_does_not_satisfy_protocol() -> None:
    assert not isinstance(_NonConformingProvider(), OnChainProvider)


def test_default_onchain_limit_is_positive() -> None:
    assert DEFAULT_ONCHAIN_LIMIT > 0


def test_protocol_has_exactly_four_typed_methods_no_generic_get_metric() -> None:
    method_names = [
        name for name, value in vars(OnChainProvider).items() if not name.startswith("_") and callable(value)
    ]
    assert set(method_names) == {
        "get_network_activity",
        "get_supply",
        "get_exchange_flows",
        "get_stablecoin_supply",
    }
    assert "get_metric" not in method_names

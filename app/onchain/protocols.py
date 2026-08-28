"""Provider-agnostic on-chain contract (Stage 4E).

One narrow, synchronous, ``runtime_checkable`` ``Protocol`` with four
explicitly typed methods - one per approved v1 metric family - each
returning its own strongly typed observation list, raising
``OnChainDataError`` subclasses on failure. Deliberately not a generic
``get_metric(name, ...)`` method: a generic accessor would defeat the
strongly-typed-per-family model design this stage is built around. On-chain
polling at this foundation layer is a discrete, low-frequency fetch over a
time range - there is no continuous-stream requirement analogous to the
Stage 1C real-time layer, so this Protocol stays synchronous by design,
mirroring every prior Foundation stage.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.models.base import Timestamp
from app.core.models.exchange_flow_observation import ExchangeFlowObservation
from app.core.models.instrument import Asset
from app.core.models.network_activity_observation import NetworkActivityObservation
from app.core.models.stablecoin_supply_observation import StablecoinSupplyObservation
from app.core.models.supply_observation import SupplyObservation

DEFAULT_ONCHAIN_LIMIT = 100
"""Number of observations requested when the caller does not specify a limit."""


@runtime_checkable
class OnChainProvider(Protocol):
    """Read-only source of on-chain observations across the four v1 metric families."""

    def get_network_activity(
        self,
        asset: Asset,
        network: str,
        start: Timestamp,
        end: Timestamp,
        *,
        limit: int = DEFAULT_ONCHAIN_LIMIT,
    ) -> list[NetworkActivityObservation]:
        """Return up to ``limit`` observations with ``observation_time`` in ``[start, end]``."""
        ...

    def get_supply(
        self,
        asset: Asset,
        network: str,
        start: Timestamp,
        end: Timestamp,
        *,
        limit: int = DEFAULT_ONCHAIN_LIMIT,
    ) -> list[SupplyObservation]:
        """Return up to ``limit`` observations with ``observation_time`` in ``[start, end]``."""
        ...

    def get_exchange_flows(
        self,
        asset: Asset,
        network: str,
        start: Timestamp,
        end: Timestamp,
        *,
        exchange: str | None = None,
        limit: int = DEFAULT_ONCHAIN_LIMIT,
    ) -> list[ExchangeFlowObservation]:
        """Return up to ``limit`` observations with ``observation_time`` in ``[start, end]``."""
        ...

    def get_stablecoin_supply(
        self,
        asset: Asset,
        network: str,
        start: Timestamp,
        end: Timestamp,
        *,
        limit: int = DEFAULT_ONCHAIN_LIMIT,
    ) -> list[StablecoinSupplyObservation]:
        """Return up to ``limit`` observations with ``observation_time`` in ``[start, end]``."""
        ...


__all__ = ["DEFAULT_ONCHAIN_LIMIT", "OnChainProvider"]

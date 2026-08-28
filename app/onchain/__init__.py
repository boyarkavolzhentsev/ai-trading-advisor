"""Stage 4E: provider-agnostic on-chain facts.

Normalized facts only - no interpretation, no analyst, no supervisor, no
real HTTP provider integration. Layering mirrors ``app.news``:

1. one provider Protocol (``OnChainProvider``) with four explicitly typed
   methods future concrete adapters satisfy;
2. four domain contracts
   (``app.core.models.network_activity_observation.NetworkActivityObservation``,
   ``app.core.models.supply_observation.SupplyObservation``,
   ``app.core.models.exchange_flow_observation.ExchangeFlowObservation``,
   ``app.core.models.stablecoin_supply_observation.StablecoinSupplyObservation``);
3. ``app.onchain.history`` - four bounded, append-only, version-preserving
   observation logs.

Deliberately narrow v1 scope: no provider-native derived-metric model
(MVRV/SOPR/NVT/realized-cap/...) and no generic metric-name/value bag exist
anywhere in this package - see the Stage 4E design report and its approved
scope correction. A future increment may add provider-native derived
metrics as a separately reviewed extension; it is not stubbed here.

No ``revision_number`` and no revision-conflict rule on any of the four
models, mirroring ``app.news``: on-chain observations carry no
provider-native revision counter, and a changed observation at the same
identity (e.g. a reorg-driven recount) is a normal correction, not a
conflict.

Independent from ``app.flow*`` and ``app.technical*`` - see
``tests/test_onchain_no_flow_coupling.py`` and
``tests/test_onchain_no_technical_coupling.py``.
"""

from __future__ import annotations

from app.onchain.exceptions import (
    DuplicateOnChainObservationError,
    InvalidProviderResponseError,
    OnChainDataError,
    ProviderUnavailableError,
    UnknownOnChainObservationError,
)
from app.onchain.history import (
    DEFAULT_CAPACITY,
    ExchangeFlowObservationHistory,
    NetworkActivityObservationHistory,
    StablecoinSupplyObservationHistory,
    SupplyObservationHistory,
)
from app.onchain.protocols import DEFAULT_ONCHAIN_LIMIT, OnChainProvider
from app.onchain.provenance import OnChainDataSource, OnChainProvenance

__all__ = [
    "DEFAULT_CAPACITY",
    "DEFAULT_ONCHAIN_LIMIT",
    "DuplicateOnChainObservationError",
    "ExchangeFlowObservationHistory",
    "InvalidProviderResponseError",
    "NetworkActivityObservationHistory",
    "OnChainDataError",
    "OnChainDataSource",
    "OnChainProvenance",
    "OnChainProvider",
    "ProviderUnavailableError",
    "StablecoinSupplyObservationHistory",
    "SupplyObservationHistory",
    "UnknownOnChainObservationError",
]

"""Bounded, append-only on-chain observation history (Stage 4E).

Four concrete classes below, one per approved v1 metric family, each
wrapping ``app.market_data.realtime.buffers.BoundedBuffer`` directly and
unmodified as its sole backing store - the same "don't reimplement bounded
storage" stance as ``app.news.history.NewsItemHistory``. There is
deliberately no secondary index kept alongside any of them: ``BoundedBuffer``
does not expose which item a drop-oldest eviction removed, so a parallel
index could silently retain a key the buffer itself has already evicted.
Every query below is instead a pure, read-time scan over the bounded
buffer's current contents.

Only the reviewed minimal query surface exists on every class: ``append``,
``all_observations``, ``by_provider``, ``versions_for``, ``latest_version``.
No ``by_asset``/``by_network``/``by_exchange``, date-range, or aggregation
query exists - deliberately, per the approved Stage 4E scope correction, not
merely by omission.

Identity: ON-CHAIN FACT vs. INGESTION OBSERVATION
------------------------------------------------------
For ``NetworkActivityObservation``/``SupplyObservation``/
``StablecoinSupplyObservation``, identity is ``(provider,
provider_series_id, asset, network, observation_time)``. For
``ExchangeFlowObservation`` it additionally includes ``exchange`` (including
when ``None``, meaning the provider's all-exchange aggregate - a genuinely
different, independently retained fact from any one named exchange, not a
version of one another). None of the four is a unique row identity: the
same identity is legitimately *observed* more than once as a provider
revises a historical value (e.g. a reorg-driven recount) - these are
multiple retained versions of one fact, not conflicting records.

Unlike ``app.macro.history.EconomicEventHistory``/``app.rates.history``'s
observation histories, and mirroring ``app.news.history.NewsItemHistory``,
there is **no revision-conflict rule** here: on-chain observations carry no
provider-native revision counter and no settled state that a later
observation could illegitimately contradict. Every retained version at one
identity is preserved.

Semantic duplicate detection
-----------------------------
Because ``received_at`` records when *our* ingestion fetched a record - not
a provider/on-chain fact - it must never by itself make an otherwise
identical observation look new. ``_fingerprint`` compares every field
*except* ``received_at``; two observations at the same key with an
identical fingerprint are the same fact re-polled, and are rejected as a
``DuplicateOnChainObservationError`` without changing history state
(including ``dropped_count``, since nothing is appended).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.models.exchange_flow_observation import ExchangeFlowObservation
from app.core.models.network_activity_observation import NetworkActivityObservation
from app.core.models.stablecoin_supply_observation import StablecoinSupplyObservation
from app.core.models.supply_observation import SupplyObservation
from app.market_data.realtime.buffers import BoundedBuffer
from app.onchain.exceptions import DuplicateOnChainObservationError

DEFAULT_CAPACITY = 512

NetworkActivityKey = tuple[str, str, str, str, datetime]
"""``(provider, provider_series_id, asset, network, observation_time)``."""

SupplyKey = tuple[str, str, str, str, datetime]
"""``(provider, provider_series_id, asset, network, observation_time)``."""

ExchangeFlowKey = tuple[str, str, str, str, str | None, datetime]
"""``(provider, provider_series_id, asset, network, exchange, observation_time)``."""

StablecoinSupplyKey = tuple[str, str, str, str, datetime]
"""``(provider, provider_series_id, asset, network, observation_time)``."""

_INGESTION_ONLY_FIELDS = frozenset({"received_at"})
"""The only field excluded from semantic duplicate comparison on any of the
four models - it records when *we* fetched the record, never a provider
fact. A field added to any observation model in the future participates
automatically unless explicitly added here."""


def _fingerprint(observation: Any) -> dict[str, Any]:
    """All provider/domain facts on ``observation``, excluding ingestion-only metadata."""
    return observation.model_dump(exclude=_INGESTION_ONLY_FIELDS)


def _network_activity_key(observation: NetworkActivityObservation) -> NetworkActivityKey:
    return (observation.provider, observation.provider_series_id, observation.asset, observation.network, observation.observation_time)


def _supply_key(observation: SupplyObservation) -> SupplyKey:
    return (observation.provider, observation.provider_series_id, observation.asset, observation.network, observation.observation_time)


def _exchange_flow_key(observation: ExchangeFlowObservation) -> ExchangeFlowKey:
    return (
        observation.provider,
        observation.provider_series_id,
        observation.asset,
        observation.network,
        observation.exchange,
        observation.observation_time,
    )


def _stablecoin_supply_key(observation: StablecoinSupplyObservation) -> StablecoinSupplyKey:
    return (observation.provider, observation.provider_series_id, observation.asset, observation.network, observation.observation_time)


def _sort_key(observation: Any) -> tuple[object, ...]:
    return (observation.observation_time, observation.provider, observation.provider_series_id)


@dataclass(slots=True)
class NetworkActivityObservationHistory:
    """Bounded, version-preserving, provider-isolated network-activity log."""

    capacity: int = DEFAULT_CAPACITY
    _buffer: BoundedBuffer[NetworkActivityObservation] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._buffer = BoundedBuffer(maxlen=self.capacity)

    @property
    def dropped_count(self) -> int:
        """Number of records evicted so far because the buffer was full."""
        return self._buffer.dropped_count

    def __len__(self) -> int:
        return len(self._buffer)

    def append(self, observation: NetworkActivityObservation) -> None:
        """Append one new ingestion observation.

        A re-poll whose fingerprint (every field except ``received_at``)
        exactly matches an already-recorded observation at the same
        identity raises ``DuplicateOnChainObservationError`` without
        changing history state. Any other observation at the same identity
        - a corrected count, a newly-populated field, and so on - is a
        legitimate new version and is always appended; there is no
        conflict rule.
        """
        key = _network_activity_key(observation)
        fingerprint = _fingerprint(observation)
        for existing in self._buffer:
            if _network_activity_key(existing) == key and _fingerprint(existing) == fingerprint:
                raise DuplicateOnChainObservationError(
                    f"observation already recorded for key {key} (differs only by received_at, if at all)"
                )
        self._buffer.append(observation)

    def all_observations(self) -> list[NetworkActivityObservation]:
        """All retained observations, ordered by ``(observation_time, provider, provider_series_id)``.

        Ties are broken by insertion order (the buffer already iterates
        oldest-inserted-first and ``sorted`` is stable), never by
        ``received_at``.
        """
        return sorted(self._buffer.latest(), key=_sort_key)

    def by_provider(self, provider: str) -> list[NetworkActivityObservation]:
        """All retained observations for one provider, deterministically ordered."""
        return sorted((o for o in self._buffer if o.provider == provider), key=_sort_key)

    def versions_for(
        self, provider: str, provider_series_id: str, asset: str, network: str, observation_time: datetime
    ) -> list[NetworkActivityObservation]:
        """All retained observations of one identity, in append order.

        Preserves append/insertion order exactly - **not** re-sorted by any
        timestamp: there is no provider-guaranteed monotonic counter, so
        insertion order is the one ordering this history can honestly claim
        is deterministic without fabricating a ranking key.
        """
        target_key = (provider, provider_series_id, asset, network, observation_time)
        return [o for o in self._buffer if _network_activity_key(o) == target_key]

    def latest_version(
        self, provider: str, provider_series_id: str, asset: str, network: str, observation_time: datetime
    ) -> NetworkActivityObservation | None:
        """Most recently appended observation of this identity, or ``None`` if never retained."""
        versions = self.versions_for(provider, provider_series_id, asset, network, observation_time)
        return versions[-1] if versions else None


@dataclass(slots=True)
class SupplyObservationHistory:
    """Bounded, version-preserving, provider-isolated supply log."""

    capacity: int = DEFAULT_CAPACITY
    _buffer: BoundedBuffer[SupplyObservation] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._buffer = BoundedBuffer(maxlen=self.capacity)

    @property
    def dropped_count(self) -> int:
        """Number of records evicted so far because the buffer was full."""
        return self._buffer.dropped_count

    def __len__(self) -> int:
        return len(self._buffer)

    def append(self, observation: SupplyObservation) -> None:
        """Append one new ingestion observation. See ``NetworkActivityObservationHistory.append``."""
        key = _supply_key(observation)
        fingerprint = _fingerprint(observation)
        for existing in self._buffer:
            if _supply_key(existing) == key and _fingerprint(existing) == fingerprint:
                raise DuplicateOnChainObservationError(
                    f"observation already recorded for key {key} (differs only by received_at, if at all)"
                )
        self._buffer.append(observation)

    def all_observations(self) -> list[SupplyObservation]:
        """All retained observations, deterministically ordered. See ``NetworkActivityObservationHistory.all_observations``."""
        return sorted(self._buffer.latest(), key=_sort_key)

    def by_provider(self, provider: str) -> list[SupplyObservation]:
        """All retained observations for one provider, deterministically ordered."""
        return sorted((o for o in self._buffer if o.provider == provider), key=_sort_key)

    def versions_for(
        self, provider: str, provider_series_id: str, asset: str, network: str, observation_time: datetime
    ) -> list[SupplyObservation]:
        """All retained observations of one identity, in append order."""
        target_key = (provider, provider_series_id, asset, network, observation_time)
        return [o for o in self._buffer if _supply_key(o) == target_key]

    def latest_version(
        self, provider: str, provider_series_id: str, asset: str, network: str, observation_time: datetime
    ) -> SupplyObservation | None:
        """Most recently appended observation of this identity, or ``None`` if never retained."""
        versions = self.versions_for(provider, provider_series_id, asset, network, observation_time)
        return versions[-1] if versions else None


@dataclass(slots=True)
class ExchangeFlowObservationHistory:
    """Bounded, version-preserving, provider-isolated exchange-flow log."""

    capacity: int = DEFAULT_CAPACITY
    _buffer: BoundedBuffer[ExchangeFlowObservation] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._buffer = BoundedBuffer(maxlen=self.capacity)

    @property
    def dropped_count(self) -> int:
        """Number of records evicted so far because the buffer was full."""
        return self._buffer.dropped_count

    def __len__(self) -> int:
        return len(self._buffer)

    def append(self, observation: ExchangeFlowObservation) -> None:
        """Append one new ingestion observation. See ``NetworkActivityObservationHistory.append``."""
        key = _exchange_flow_key(observation)
        fingerprint = _fingerprint(observation)
        for existing in self._buffer:
            if _exchange_flow_key(existing) == key and _fingerprint(existing) == fingerprint:
                raise DuplicateOnChainObservationError(
                    f"observation already recorded for key {key} (differs only by received_at, if at all)"
                )
        self._buffer.append(observation)

    def all_observations(self) -> list[ExchangeFlowObservation]:
        """All retained observations, deterministically ordered. See ``NetworkActivityObservationHistory.all_observations``."""
        return sorted(self._buffer.latest(), key=_sort_key)

    def by_provider(self, provider: str) -> list[ExchangeFlowObservation]:
        """All retained observations for one provider, deterministically ordered."""
        return sorted((o for o in self._buffer if o.provider == provider), key=_sort_key)

    def versions_for(
        self,
        provider: str,
        provider_series_id: str,
        asset: str,
        network: str,
        exchange: str | None,
        observation_time: datetime,
    ) -> list[ExchangeFlowObservation]:
        """All retained observations of one identity, in append order."""
        target_key = (provider, provider_series_id, asset, network, exchange, observation_time)
        return [o for o in self._buffer if _exchange_flow_key(o) == target_key]

    def latest_version(
        self,
        provider: str,
        provider_series_id: str,
        asset: str,
        network: str,
        exchange: str | None,
        observation_time: datetime,
    ) -> ExchangeFlowObservation | None:
        """Most recently appended observation of this identity, or ``None`` if never retained."""
        versions = self.versions_for(provider, provider_series_id, asset, network, exchange, observation_time)
        return versions[-1] if versions else None


@dataclass(slots=True)
class StablecoinSupplyObservationHistory:
    """Bounded, version-preserving, provider-isolated stablecoin-supply log."""

    capacity: int = DEFAULT_CAPACITY
    _buffer: BoundedBuffer[StablecoinSupplyObservation] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._buffer = BoundedBuffer(maxlen=self.capacity)

    @property
    def dropped_count(self) -> int:
        """Number of records evicted so far because the buffer was full."""
        return self._buffer.dropped_count

    def __len__(self) -> int:
        return len(self._buffer)

    def append(self, observation: StablecoinSupplyObservation) -> None:
        """Append one new ingestion observation. See ``NetworkActivityObservationHistory.append``."""
        key = _stablecoin_supply_key(observation)
        fingerprint = _fingerprint(observation)
        for existing in self._buffer:
            if _stablecoin_supply_key(existing) == key and _fingerprint(existing) == fingerprint:
                raise DuplicateOnChainObservationError(
                    f"observation already recorded for key {key} (differs only by received_at, if at all)"
                )
        self._buffer.append(observation)

    def all_observations(self) -> list[StablecoinSupplyObservation]:
        """All retained observations, deterministically ordered. See ``NetworkActivityObservationHistory.all_observations``."""
        return sorted(self._buffer.latest(), key=_sort_key)

    def by_provider(self, provider: str) -> list[StablecoinSupplyObservation]:
        """All retained observations for one provider, deterministically ordered."""
        return sorted((o for o in self._buffer if o.provider == provider), key=_sort_key)

    def versions_for(
        self, provider: str, provider_series_id: str, asset: str, network: str, observation_time: datetime
    ) -> list[StablecoinSupplyObservation]:
        """All retained observations of one identity, in append order."""
        target_key = (provider, provider_series_id, asset, network, observation_time)
        return [o for o in self._buffer if _stablecoin_supply_key(o) == target_key]

    def latest_version(
        self, provider: str, provider_series_id: str, asset: str, network: str, observation_time: datetime
    ) -> StablecoinSupplyObservation | None:
        """Most recently appended observation of this identity, or ``None`` if never retained."""
        versions = self.versions_for(provider, provider_series_id, asset, network, observation_time)
        return versions[-1] if versions else None


__all__ = [
    "DEFAULT_CAPACITY",
    "ExchangeFlowKey",
    "ExchangeFlowObservationHistory",
    "NetworkActivityKey",
    "NetworkActivityObservationHistory",
    "StablecoinSupplyKey",
    "StablecoinSupplyObservationHistory",
    "SupplyKey",
    "SupplyObservationHistory",
]

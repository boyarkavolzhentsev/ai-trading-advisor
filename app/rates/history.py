"""Bounded, append-only rates/yields observation history (Stage 4B).

Two concrete classes below, each wrapping
``app.market_data.realtime.buffers.BoundedBuffer`` directly and unmodified
as its sole backing store - the same "don't reimplement bounded storage"
stance as ``app.macro.history.EconomicEventHistory``. There is deliberately
no secondary ``(provider, provider_series_id, observation_time,
revision_number)`` index kept alongside either buffer: ``BoundedBuffer``
does not expose which item a drop-oldest eviction removed, so a parallel
index could silently retain a key the buffer itself has already evicted.
Every query below is instead a pure, read-time scan over the bounded
buffer's current contents.

Two concrete classes, not one generic time-series-history abstraction: a
third near-identical history is the trigger point to extract a shared
abstraction, not before.

Identity: OBSERVATION REVISION vs. INGESTION OBSERVATION
----------------------------------------------------------
``(provider, provider_series_id, observation_time, revision_number)``
identifies one *observation revision* - the provider's revision of the
reported value at one point in time. It is **not** a unique row identity:
the same observation revision may legitimately be *observed* more than once
as it moves from an initially valueless provider row to its own first
reported value (generalizing Stage 4A's SCHEDULED -> RELEASED progression to
unvalued -> valued) - these are multiple ingestion observations of one
observation revision, not new revisions. A genuine new observation revision
always arrives under a strictly higher ``revision_number``.

Semantic duplicate detection
-----------------------------
Because ``received_at`` records when *our* ingestion fetched a record - not
a provider/market fact - it must never by itself make an otherwise
identical observation look new. ``_fingerprint`` compares every field
*except* ``received_at``; two observations at the same key with an
identical fingerprint are the same fact re-polled, and are rejected as a
``DuplicateObservationError`` without changing history state (including
``dropped_count``, since nothing is appended).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.models.government_yield_observation import GovernmentYieldObservation
from app.core.models.policy_rate_observation import PolicyRateObservation
from app.market_data.realtime.buffers import BoundedBuffer
from app.rates.exceptions import DuplicateObservationError, RevisionConflictError

DEFAULT_CAPACITY = 512

PolicyRateKey = tuple[str, str, datetime, int]
"""``(provider, provider_series_id, observation_time, revision_number)``."""

GovernmentYieldKey = tuple[str, str, datetime, int]
"""``(provider, provider_series_id, observation_time, revision_number)``."""

_INGESTION_ONLY_FIELDS = frozenset({"received_at"})
"""The only field excluded from semantic duplicate comparison - it records
when *we* fetched the record, never a provider fact. Any field added to
either observation model in the future participates automatically unless
explicitly added here."""


def _fingerprint(observation: PolicyRateObservation | GovernmentYieldObservation) -> dict[str, Any]:
    """All provider/domain facts on ``observation``, excluding ingestion-only metadata."""
    return observation.model_dump(exclude=_INGESTION_ONLY_FIELDS)


def _policy_rate_key(observation: PolicyRateObservation) -> PolicyRateKey:
    return (
        observation.provider,
        observation.provider_series_id,
        observation.observation_time,
        observation.revision_number,
    )


def _yield_key(observation: GovernmentYieldObservation) -> GovernmentYieldKey:
    return (
        observation.provider,
        observation.provider_series_id,
        observation.observation_time,
        observation.revision_number,
    )


def _sort_key(observation: PolicyRateObservation | GovernmentYieldObservation) -> tuple[datetime, int]:
    return (observation.observation_time, observation.revision_number)


@dataclass(slots=True)
class PolicyRateObservationHistory:
    """Bounded, revision-preserving, provider-isolated policy-rate log."""

    capacity: int = DEFAULT_CAPACITY
    _buffer: BoundedBuffer[PolicyRateObservation] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._buffer = BoundedBuffer(maxlen=self.capacity)

    @property
    def dropped_count(self) -> int:
        """Number of observations evicted so far because the buffer was full."""
        return self._buffer.dropped_count

    def __len__(self) -> int:
        return len(self._buffer)

    def append(self, observation: PolicyRateObservation) -> None:
        """Append one new ingestion observation.

        For a given observation-revision key
        (``provider``, ``provider_series_id``, ``observation_time``,
        ``revision_number``):

        - an unvalued observation (``value is None``) may be followed by
          another unvalued observation with genuinely different provider
          facts, or by its own first valued observation - both are
          legitimate append-only progression, never a conflict;
        - a valued observation may never be followed by an unvalued one for
          the same key (data cannot regress from known back to unknown) -
          raises ``RevisionConflictError``, checked against *every*
          already-recorded observation of the key, not just the first one
          encountered;
        - a valued observation may never be followed by a *different*
          valued observation for the same key (a changed reported value
          must arrive under a higher ``revision_number``, i.e. a new key,
          not a mutated old one) - raises ``RevisionConflictError``;
        - an observation whose fingerprint (every field except
          ``received_at``) exactly matches an already-recorded observation
          at the same key is a re-poll of the same fact, regardless of
          ``received_at`` - raises ``DuplicateObservationError`` without
          changing history state.

        Neither error appends anything or otherwise mutates the history.
        """
        key = _policy_rate_key(observation)
        valued = observation.value is not None
        existing_for_key = [o for o in self._buffer if _policy_rate_key(o) == key]

        if not valued and any(o.value is not None for o in existing_for_key):
            raise RevisionConflictError(
                f"key {key} already has a reported value; cannot revert to unreported"
            )

        fingerprint = _fingerprint(observation)
        for existing in existing_for_key:
            if _fingerprint(existing) == fingerprint:
                raise DuplicateObservationError(
                    f"observation already recorded for key {key} (differs only by received_at, if at all)"
                )
            if valued and existing.value is not None:
                raise RevisionConflictError(f"key {key} already recorded with conflicting content")
            # else: one or both unvalued and provider facts genuinely
            # differ - a legitimate pre-report update, or the first valued
            # observation of a prior unvalued placeholder - allow it.
        self._buffer.append(observation)

    def all_observations(self) -> list[PolicyRateObservation]:
        """All retained observations (any provider/series/revision), deterministically ordered.

        Ordered by ``(observation_time, revision_number)``; ties are broken
        by insertion order (the buffer already iterates oldest-inserted-
        first and ``sorted`` is stable), never by ``received_at``.
        """
        return sorted(self._buffer.latest(), key=_sort_key)

    def by_provider(self, provider: str) -> list[PolicyRateObservation]:
        """All retained observations for one provider, deterministically ordered."""
        return sorted((o for o in self._buffer if o.provider == provider), key=_sort_key)

    def observations_for(self, provider: str, provider_series_id: str) -> list[PolicyRateObservation]:
        """All retained observations of one ``(provider, provider_series_id)``.

        Ordered by ``(observation_time, revision_number)``; within one exact
        revision identity, observations keep their original append order.
        """
        matches = [
            o for o in self._buffer if o.provider == provider and o.provider_series_id == provider_series_id
        ]
        return sorted(matches, key=_sort_key)

    def latest(self, provider: str, provider_series_id: str) -> PolicyRateObservation | None:
        """Most current retained observation of this series.

        Ordering: (1) highest ``observation_time``; (2) highest
        ``revision_number`` at that time; (3) most recently appended
        observation within that exact revision identity - never based on
        ``received_at``. ``None`` when no observation of this series is
        currently retained (never seen, or evicted) - never fabricated.
        """
        observations = self.observations_for(provider, provider_series_id)
        return observations[-1] if observations else None


@dataclass(slots=True)
class GovernmentYieldObservationHistory:
    """Bounded, revision-preserving, provider-isolated government-yield log."""

    capacity: int = DEFAULT_CAPACITY
    _buffer: BoundedBuffer[GovernmentYieldObservation] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._buffer = BoundedBuffer(maxlen=self.capacity)

    @property
    def dropped_count(self) -> int:
        """Number of observations evicted so far because the buffer was full."""
        return self._buffer.dropped_count

    def __len__(self) -> int:
        return len(self._buffer)

    def append(self, observation: GovernmentYieldObservation) -> None:
        """Append one new ingestion observation.

        See ``PolicyRateObservationHistory.append`` for the exact
        unvalued/valued progression and conflict rules - identical here,
        keyed the same way.
        """
        key = _yield_key(observation)
        valued = observation.value is not None
        existing_for_key = [o for o in self._buffer if _yield_key(o) == key]

        if not valued and any(o.value is not None for o in existing_for_key):
            raise RevisionConflictError(
                f"key {key} already has a reported value; cannot revert to unreported"
            )

        fingerprint = _fingerprint(observation)
        for existing in existing_for_key:
            if _fingerprint(existing) == fingerprint:
                raise DuplicateObservationError(
                    f"observation already recorded for key {key} (differs only by received_at, if at all)"
                )
            if valued and existing.value is not None:
                raise RevisionConflictError(f"key {key} already recorded with conflicting content")
        self._buffer.append(observation)

    def all_observations(self) -> list[GovernmentYieldObservation]:
        """All retained observations, deterministically ordered.

        See ``PolicyRateObservationHistory.all_observations``.
        """
        return sorted(self._buffer.latest(), key=_sort_key)

    def by_provider(self, provider: str) -> list[GovernmentYieldObservation]:
        """All retained observations for one provider, deterministically ordered."""
        return sorted((o for o in self._buffer if o.provider == provider), key=_sort_key)

    def observations_for(self, provider: str, provider_series_id: str) -> list[GovernmentYieldObservation]:
        """All retained observations of one ``(provider, provider_series_id)``."""
        matches = [
            o for o in self._buffer if o.provider == provider and o.provider_series_id == provider_series_id
        ]
        return sorted(matches, key=_sort_key)

    def latest(self, provider: str, provider_series_id: str) -> GovernmentYieldObservation | None:
        """Most current retained observation of this series.

        See ``PolicyRateObservationHistory.latest``.
        """
        observations = self.observations_for(provider, provider_series_id)
        return observations[-1] if observations else None


__all__ = [
    "DEFAULT_CAPACITY",
    "GovernmentYieldKey",
    "GovernmentYieldObservationHistory",
    "PolicyRateKey",
    "PolicyRateObservationHistory",
]

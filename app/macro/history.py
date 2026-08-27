"""Bounded, append-only economic-calendar event history (Stage 4A).

Wraps ``app.market_data.realtime.buffers.BoundedBuffer`` directly, unmodified,
as the sole backing store - the same "don't reimplement bounded storage"
stance as ``app.flow.history``. There is deliberately no secondary
``(provider, provider_event_id)`` index kept alongside it: ``BoundedBuffer``
does not expose which item a drop-oldest eviction removed, so a parallel
index could silently retain a key the buffer itself has already evicted.
Every query below is instead a pure, read-time scan over the bounded buffer's
current contents - with a capacity in the low hundreds this is trivially
cheap, and it keeps the buffer the single source of truth (see the Stage 4A
design report, "History/storage architecture").

Eviction is oldest-*inserted*-first (``BoundedBuffer``'s drop-oldest policy),
not oldest-``event_time``-first - callers should insert roughly in
``event_time`` order for eviction to also approximate recency, but every
retrieval method below sorts explicitly, so read-order determinism never
depends on insertion order.

Identity: ECONOMIC REVISION vs. INGESTION OBSERVATION
------------------------------------------------------
``(provider, provider_event_id, revision_number)`` (``EventKey``) identifies
one *economic revision* - the provider's revision of the released value. It
is **not** a unique row identity: the same economic revision is legitimately
*observed* more than once as it moves through its lifecycle (e.g. a
``SCHEDULED`` placeholder, possibly re-polled with an updated forecast, then
its own ``RELEASED`` realization) - these are multiple ingestion
observations of one economic revision, not new revisions. A genuine new
economic revision always arrives under a strictly higher ``revision_number``.

Semantic duplicate detection
-----------------------------
Because ``received_at`` records when *our* ingestion fetched a record - not
a provider/economic fact - it must never by itself make an otherwise
identical observation look new. ``_semantic_fingerprint`` compares every
``EconomicEvent`` field *except* ``received_at``; two observations at the
same key with an identical fingerprint are the same fact re-polled, and are
rejected as a ``DuplicateEventError`` without changing history state
(including ``dropped_count``, since nothing is appended).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.models.economic_event import EconomicEvent
from app.macro.exceptions import DuplicateEventError, RevisionConflictError
from app.market_data.realtime.buffers import BoundedBuffer

DEFAULT_CAPACITY = 512

EventKey = tuple[str, str, int]
"""``(provider, provider_event_id, revision_number)`` - the economic-revision
identity (see module docstring), not a unique ingestion-record identity."""

_INGESTION_ONLY_FIELDS = frozenset({"received_at"})
"""The only ``EconomicEvent`` field excluded from semantic duplicate
comparison - it records when *we* fetched the record, never a provider fact.
Every other field, including nested ``rate_decision_detail``, participates;
a field added to ``EconomicEvent`` in the future participates automatically
unless explicitly added here."""


def _key(event: EconomicEvent) -> EventKey:
    return (event.provider, event.provider_event_id, event.revision_number)


def _semantic_fingerprint(event: EconomicEvent) -> dict[str, Any]:
    """All provider/domain facts on ``event``, excluding ingestion-only metadata.

    Used only for duplicate comparison - never for the identity key itself,
    which stays ``(provider, provider_event_id, revision_number)``.
    """
    return event.model_dump(exclude=_INGESTION_ONLY_FIELDS)


@dataclass(slots=True)
class EconomicEventHistory:
    """Bounded, revision-preserving, provider-isolated event log."""

    capacity: int = DEFAULT_CAPACITY
    _buffer: BoundedBuffer[EconomicEvent] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._buffer = BoundedBuffer(maxlen=self.capacity)

    @property
    def dropped_count(self) -> int:
        """Number of records evicted so far because the buffer was full."""
        return self._buffer.dropped_count

    def __len__(self) -> int:
        return len(self._buffer)

    def append(self, event: EconomicEvent) -> None:
        """Append one new ingestion observation.

        A record is *settled* once it carries an ``actual`` value
        (``RELEASED``/``REVISED``); a ``SCHEDULED``/``POSTPONED``/
        ``CANCELLED`` record is not. For a given economic-revision key
        (``provider``, ``provider_event_id``, ``revision_number``):

        - an unsettled observation may be followed by another unsettled
          observation with genuinely different provider facts (e.g. a
          pre-release forecast refinement), or by its own first settled
          observation (``SCHEDULED`` -> ``RELEASED``) - both are legitimate
          append-only lifecycle progression, never a conflict;
        - a settled observation may never be followed by an unsettled one
          for the same key (data cannot regress from known back to
          unknown) - raises ``RevisionConflictError``. This is checked
          against *every* already-recorded observation of the key, not just
          the first one encountered - regression is forbidden even if the
          incoming (reverted) content happens to be byte-identical to an
          earlier, still-unsettled observation of the same key;
        - a settled observation may never be followed by a *different*
          settled observation for the same key (a changed released value
          must arrive under a higher ``revision_number``, i.e. a new key,
          not a mutated old one) - raises ``RevisionConflictError``;
        - an observation whose fingerprint (every field except
          ``received_at``, see ``_semantic_fingerprint``) exactly matches an
          already-recorded observation at the same key is a re-poll of the
          same fact, regardless of ``received_at`` - raises
          ``DuplicateEventError`` without changing history state.

        Neither error appends anything or otherwise mutates the history.
        """
        key = _key(event)
        settled = event.actual is not None
        existing_for_key = [e for e in self._buffer if _key(e) == key]

        if not settled and any(e.actual is not None for e in existing_for_key):
            raise RevisionConflictError(
                f"key {key} already has a reported value; cannot revert to unreported"
            )

        fingerprint = _semantic_fingerprint(event)
        for existing in existing_for_key:
            if _semantic_fingerprint(existing) == fingerprint:
                raise DuplicateEventError(
                    f"event already recorded for key {key} (differs only by received_at, if at all)"
                )
            if settled and existing.actual is not None:
                raise RevisionConflictError(f"key {key} already recorded with conflicting content")
            # else: one or both unsettled and provider facts genuinely
            # differ - a legitimate pre-release update, or the settled
            # first-release of a prior SCHEDULED placeholder - allow it.
        self._buffer.append(event)

    def all_events(self) -> list[EconomicEvent]:
        """All retained observations (any provider/revision), event-time ordered.

        Ties are broken by ``(provider, provider_event_id, revision_number)``
        so the ordering is fully deterministic regardless of insertion order.
        """
        return sorted(self._buffer.latest(), key=_sort_key)

    def by_provider(self, provider: str) -> list[EconomicEvent]:
        """All retained observations for one provider, deterministically ordered."""
        return sorted((e for e in self._buffer if e.provider == provider), key=_sort_key)

    def revisions_for(self, provider: str, provider_event_id: str) -> list[EconomicEvent]:
        """All retained observations of one ``(provider, provider_event_id)``.

        Ordered by ascending ``revision_number``; within one
        ``revision_number``, observations keep their original insertion
        (append) order - Python's ``sorted`` is stable, and ``self._buffer``
        already iterates oldest-inserted-first, so sorting on
        ``revision_number`` alone is enough to get both properties without a
        second explicit sort key.

        Insertion order, not ``received_at``, is used as the within-revision
        tie-breaker: ``received_at`` is caller-supplied data that two
        observations could legitimately share (e.g. a batch fetch) or even
        report out of order (a backfill), whereas append order is always a
        strict total order over what this history actually holds and needs
        no assumption about the caller's clock.
        """
        matches = [
            e for e in self._buffer if e.provider == provider and e.provider_event_id == provider_event_id
        ]
        return sorted(matches, key=lambda e: e.revision_number)

    def latest_revision(self, provider: str, provider_event_id: str) -> EconomicEvent | None:
        """Most recent observation of the highest retained economic revision.

        Ordering: (1) highest ``revision_number``; (2) most recently
        appended observation within that revision number (see
        ``revisions_for``) - so ``SCHEDULED`` -> ``RELEASED`` at the same
        ``revision_number`` returns the ``RELEASED`` observation once it has
        been appended. ``None`` when no observation of this key is currently
        retained (never seen, or evicted) - never fabricated.
        """
        revisions = self.revisions_for(provider, provider_event_id)
        return revisions[-1] if revisions else None


def _sort_key(event: EconomicEvent) -> tuple[object, ...]:
    return (event.event_time, event.provider, event.provider_event_id, event.revision_number)


__all__ = ["DEFAULT_CAPACITY", "EconomicEventHistory", "EventKey"]

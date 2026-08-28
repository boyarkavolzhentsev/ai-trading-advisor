"""Bounded, append-only sentiment history (Stage 4D).

Wraps ``app.market_data.realtime.buffers.BoundedBuffer`` directly,
unmodified, as the sole backing store - the same "don't reimplement bounded
storage" stance as ``app.news.history.NewsItemHistory``. There is
deliberately no secondary index kept alongside it: ``BoundedBuffer`` does
not expose which item a drop-oldest eviction removed, so a parallel index
could silently retain a key the buffer itself has already evicted. Every
query below is instead a pure, read-time scan over the bounded buffer's
current contents.

Identity: SENTIMENT FACT vs. INGESTION OBSERVATION
------------------------------------------------------
``(provider, source_provider, source_provider_item_id, target_symbol)``
(``NewsSentimentKey``) identifies one *sentiment fact* - one sentiment
feed's reported sentiment about one entity grain (whole-item when
``target_symbol`` is ``None``, one provider-tagged entity otherwise) of one
news-item identity. It is a larger identity than
``app.news.history.NewsItemKey`` because two independent provider
dimensions are in play: ``provider`` (who reports *this sentiment*) is not
assumed to be the same as ``source_provider`` (which news feed the scored
article came from) - a dedicated sentiment vendor scoring a wire-service
article is the ordinary case, not an edge case.

Unlike ``app.macro.history.EconomicEventHistory``/``app.rates.history``'s
observation histories, and mirroring ``app.news.history.NewsItemHistory``,
there is **no revision-conflict rule** here: a sentiment feed revising its
own reported score as more signal becomes available is a normal, expected
update - not a conflict to reject. Every retained version at one identity
is preserved.

Semantic duplicate detection
-----------------------------
Because the Stage 4D ``received_at`` records when *our* ingestion fetched
this sentiment record - not a provider/sentiment-feed fact - it must never
by itself make an otherwise identical observation look new. ``_fingerprint``
compares every ``NewsSentimentObservation`` field *except* ``received_at``;
two observations at the same key with an identical fingerprint are the same
fact re-polled, and are rejected as a ``DuplicateNewsSentimentError``
without changing history state (including ``dropped_count``, since nothing
is appended).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.models.news_sentiment_observation import NewsSentimentObservation
from app.market_data.realtime.buffers import BoundedBuffer
from app.news_intel.exceptions import DuplicateNewsSentimentError

DEFAULT_CAPACITY = 512

NewsSentimentKey = tuple[str, str, str, str | None]
"""``(provider, source_provider, source_provider_item_id, target_symbol)`` -
the sentiment-fact identity (see module docstring), not a unique
ingestion-record identity."""

_INGESTION_ONLY_FIELDS = frozenset({"received_at"})
"""The only ``NewsSentimentObservation`` field excluded from semantic
duplicate comparison - it records when *we* fetched the record, never a
provider fact. A field added to ``NewsSentimentObservation`` in the future
participates automatically unless explicitly added here."""


def _key(observation: NewsSentimentObservation) -> NewsSentimentKey:
    return (
        observation.provider,
        observation.source_provider,
        observation.source_provider_item_id,
        observation.target_symbol,
    )


def _fingerprint(observation: NewsSentimentObservation) -> dict[str, Any]:
    """All provider/domain facts on ``observation``, excluding ingestion-only metadata.

    Used only for duplicate comparison - never for the identity key itself,
    which stays the 4-tuple in ``_key``.
    """
    return observation.model_dump(exclude=_INGESTION_ONLY_FIELDS)


def _sort_key(observation: NewsSentimentObservation) -> tuple[object, ...]:
    return (
        observation.published_at,
        observation.provider,
        observation.source_provider,
        observation.source_provider_item_id,
    )


@dataclass(slots=True)
class NewsSentimentObservationHistory:
    """Bounded, version-preserving, provider-isolated sentiment log."""

    capacity: int = DEFAULT_CAPACITY
    _buffer: BoundedBuffer[NewsSentimentObservation] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._buffer = BoundedBuffer(maxlen=self.capacity)

    @property
    def dropped_count(self) -> int:
        """Number of records evicted so far because the buffer was full."""
        return self._buffer.dropped_count

    def __len__(self) -> int:
        return len(self._buffer)

    def append(self, observation: NewsSentimentObservation) -> None:
        """Append one new ingestion observation.

        For a given identity (``provider``, ``source_provider``,
        ``source_provider_item_id``, ``target_symbol``):

        - an observation whose fingerprint (every field except
          ``received_at``, see ``_fingerprint``) exactly matches an
          already-recorded observation at the same identity is a re-poll of
          the same fact, regardless of ``received_at`` - raises
          ``DuplicateNewsSentimentError`` without changing history state;
        - any other observation at the same identity - an updated
          ``sentiment_score``/``sentiment_label``, and so on - is a
          legitimate new version and is always appended. There is no
          conflict rule: sentiment carries no settled state that a later
          observation could illegitimately contradict.

        Neither the duplicate case appends anything nor otherwise mutates
        the history.
        """
        key = _key(observation)
        fingerprint = _fingerprint(observation)
        for existing in self._buffer:
            if _key(existing) == key and _fingerprint(existing) == fingerprint:
                raise DuplicateNewsSentimentError(
                    f"observation already recorded for key {key} (differs only by received_at, if at all)"
                )
        self._buffer.append(observation)

    def all_observations(self) -> list[NewsSentimentObservation]:
        """All retained observations (any identity), deterministically ordered.

        Ordered by ``(published_at, provider, source_provider,
        source_provider_item_id)``; ties are broken by insertion order (the
        buffer already iterates oldest-inserted-first and ``sorted`` is
        stable), never by ``received_at``.
        """
        return sorted(self._buffer.latest(), key=_sort_key)

    def by_provider(self, provider: str) -> list[NewsSentimentObservation]:
        """All retained observations for one sentiment provider, deterministically ordered."""
        return sorted((o for o in self._buffer if o.provider == provider), key=_sort_key)

    def versions_for(
        self,
        provider: str,
        source_provider: str,
        source_provider_item_id: str,
        target_symbol: str | None,
    ) -> list[NewsSentimentObservation]:
        """All retained observations of one identity.

        Preserves append/insertion order exactly - **not** re-sorted by any
        timestamp, mirroring ``app.news.history.NewsItemHistory.versions_for``:
        sentiment carries no provider-guaranteed monotonic counter, so
        insertion order is the one ordering this history can honestly claim
        is deterministic without fabricating a ranking key.
        """
        target_key = (provider, source_provider, source_provider_item_id, target_symbol)
        return [o for o in self._buffer if _key(o) == target_key]

    def latest_version(
        self,
        provider: str,
        source_provider: str,
        source_provider_item_id: str,
        target_symbol: str | None,
    ) -> NewsSentimentObservation | None:
        """Most recently appended observation of this identity.

        ``None`` when no observation of this identity is currently retained
        (never seen, or evicted) - never fabricated.
        """
        versions = self.versions_for(provider, source_provider, source_provider_item_id, target_symbol)
        return versions[-1] if versions else None


__all__ = ["DEFAULT_CAPACITY", "NewsSentimentKey", "NewsSentimentObservationHistory"]

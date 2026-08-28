"""Bounded, append-only news-item history (Stage 4C).

Wraps ``app.market_data.realtime.buffers.BoundedBuffer`` directly,
unmodified, as the sole backing store - the same "don't reimplement bounded
storage" stance as ``app.macro.history``/``app.rates.history``. There is
deliberately no secondary ``(provider, provider_item_id)`` index kept
alongside it: ``BoundedBuffer`` does not expose which item a drop-oldest
eviction removed, so a parallel index could silently retain a key the
buffer itself has already evicted. Every query below is instead a pure,
read-time scan over the bounded buffer's current contents.

Identity: NEWS ITEM vs. INGESTION OBSERVATION
------------------------------------------------
``(provider, provider_item_id)`` (``NewsItemKey``) identifies one *news
item* - one real provider article/story. It is **not** a unique row
identity: the same item is legitimately *observed* more than once as it is
corrected or updated by its publisher (a headline edit, a body correction,
a breaking story filled in with more detail) - these are multiple retained
versions of one news item, not conflicting records.

Unlike ``app.macro.history.EconomicEventHistory``/``app.rates.history``'s
observation histories, there is **no revision-conflict rule** here: those
domains have a genuine provider-native concept of a settled value that
cannot legitimately regress or be silently contradicted. News has no
settled state - a changed headline/body at the same identity is a normal,
expected correction, and every retained version is preserved, never
rejected as conflicting.

Semantic duplicate detection
-----------------------------
Because ``received_at`` records when *our* ingestion fetched a record - not
a provider/story fact - it must never by itself make an otherwise identical
observation look new. ``_fingerprint`` compares every ``NewsItem`` field
*except* ``received_at``; two observations at the same key with an
identical fingerprint are the same story re-polled, and are rejected as a
``DuplicateNewsItemError`` without changing history state (including
``dropped_count``, since nothing is appended).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.models.news_item import NewsItem
from app.market_data.realtime.buffers import BoundedBuffer
from app.news.exceptions import DuplicateNewsItemError

DEFAULT_CAPACITY = 512

NewsItemKey = tuple[str, str]
"""``(provider, provider_item_id)`` - the news-item identity (see module
docstring), not a unique ingestion-record identity."""

_INGESTION_ONLY_FIELDS = frozenset({"received_at"})
"""The only ``NewsItem`` field excluded from semantic duplicate comparison -
it records when *we* fetched the record, never a provider fact. A field
added to ``NewsItem`` in the future participates automatically unless
explicitly added here."""


def _key(item: NewsItem) -> NewsItemKey:
    return (item.provider, item.provider_item_id)


def _fingerprint(item: NewsItem) -> dict[str, Any]:
    """All provider/domain facts on ``item``, excluding ingestion-only metadata.

    Used only for duplicate comparison - never for the identity key itself,
    which stays ``(provider, provider_item_id)``.
    """
    return item.model_dump(exclude=_INGESTION_ONLY_FIELDS)


@dataclass(slots=True)
class NewsItemHistory:
    """Bounded, version-preserving, provider-isolated news log."""

    capacity: int = DEFAULT_CAPACITY
    _buffer: BoundedBuffer[NewsItem] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._buffer = BoundedBuffer(maxlen=self.capacity)

    @property
    def dropped_count(self) -> int:
        """Number of records evicted so far because the buffer was full."""
        return self._buffer.dropped_count

    def __len__(self) -> int:
        return len(self._buffer)

    def append(self, item: NewsItem) -> None:
        """Append one new ingestion observation.

        For a given identity (``provider``, ``provider_item_id``):

        - an observation whose fingerprint (every field except
          ``received_at``, see ``_fingerprint``) exactly matches an
          already-recorded observation at the same identity is a re-poll of
          the same story, regardless of ``received_at`` - raises
          ``DuplicateNewsItemError`` without changing history state;
        - any other observation at the same identity - a corrected
          headline/body, a newly-populated ``updated_at``, added provider
          tags/symbols, and so on - is a legitimate new version and is
          always appended. There is no conflict rule: unlike
          ``EconomicEventHistory``/rates observation histories, news has no
          settled state that a later observation could illegitimately
          contradict.

        Neither the duplicate case appends anything nor otherwise mutates
        the history.
        """
        key = _key(item)
        fingerprint = _fingerprint(item)
        for existing in self._buffer:
            if _key(existing) == key and _fingerprint(existing) == fingerprint:
                raise DuplicateNewsItemError(
                    f"item already recorded for key {key} (differs only by received_at, if at all)"
                )
        self._buffer.append(item)

    def all_items(self) -> list[NewsItem]:
        """All retained observations (any provider/identity), deterministically ordered.

        Ordered by ``(published_at, provider, provider_item_id)``; ties are
        broken by insertion order (the buffer already iterates
        oldest-inserted-first and ``sorted`` is stable), never by
        ``received_at``.
        """
        return sorted(self._buffer.latest(), key=_sort_key)

    def by_provider(self, provider: str) -> list[NewsItem]:
        """All retained observations for one provider, deterministically ordered."""
        return sorted((i for i in self._buffer if i.provider == provider), key=_sort_key)

    def versions_for(self, provider: str, provider_item_id: str) -> list[NewsItem]:
        """All retained observations of one ``(provider, provider_item_id)``.

        Preserves append/insertion order exactly - **not** re-sorted by any
        timestamp. News carries no provider-guaranteed monotonic counter
        (unlike ``revision_number`` in ``app.macro.history``/
        ``app.rates.history``), and ``published_at``/``updated_at`` are
        unenforced provider facts that may not be consistently populated or
        monotonic across corrections - see ``app.core.models.news_item``.
        Insertion order is the one ordering this history can honestly claim
        is deterministic without fabricating a ranking key.
        """
        return [i for i in self._buffer if _key(i) == (provider, provider_item_id)]

    def latest_version(self, provider: str, provider_item_id: str) -> NewsItem | None:
        """Most recently appended observation of this identity.

        ``None`` when no observation of this identity is currently retained
        (never seen, or evicted) - never fabricated.
        """
        versions = self.versions_for(provider, provider_item_id)
        return versions[-1] if versions else None


def _sort_key(item: NewsItem) -> tuple[object, ...]:
    return (item.published_at, item.provider, item.provider_item_id)


__all__ = ["DEFAULT_CAPACITY", "NewsItemHistory", "NewsItemKey"]

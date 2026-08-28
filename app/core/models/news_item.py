"""Stage 4C provider-neutral news-item fact.

One provider-reported news article/story, at one observed point in its
lifecycle. Facts only - no sentiment, no relevance/importance scoring, no
bullish/bearish interpretation, no entity resolution beyond whatever the
provider itself attached to the item.

Identity is ``(provider, provider_item_id)`` - see ``app.news.history`` for
append-only version handling. Unlike ``EconomicEvent``/``PolicyRateObservation``/
``GovernmentYieldObservation``, there is no ``revision_number``: no mainstream
news provider exposes an integer revision counter for an article, so this
model does not invent one. There is no canonical cross-provider item id
either: the same real-world story reported by two providers is two
independent records, mirroring ``EconomicEvent``'s stance.

``published_at`` and ``updated_at`` are both independent, unrelated provider
facts. This model does not enforce ``updated_at >= published_at`` or any
other cross-field chronological invariant between them: external providers
are not guaranteed to maintain one, and inventing such a rule here would be
an unreviewed assumption imposed on raw provider data. Both timestamps are
preserved exactly as reported - never normalized, repaired, or reinterpreted.
A later quality/anomaly stage may evaluate a suspicious relationship between
them; Stage 4C only preserves what the provider supplied.
"""

from __future__ import annotations

from pydantic import Field

from app.core.models.base import DomainModel, Timestamp


class NewsItem(DomainModel):
    """One provider-reported news item, at one observed version."""

    provider: str = Field(min_length=1)
    provider_item_id: str = Field(min_length=1)
    headline: str = Field(min_length=1)
    body: str | None = Field(default=None, min_length=1)
    source: str | None = Field(default=None, min_length=1)
    source_url: str | None = Field(default=None, min_length=1)
    language: str | None = Field(default=None, min_length=1, max_length=8)
    published_at: Timestamp
    updated_at: Timestamp | None = None
    received_at: Timestamp
    provider_tags: list[str] = Field(default_factory=list)
    provider_symbols: list[str] = Field(default_factory=list)


__all__ = ["NewsItem"]

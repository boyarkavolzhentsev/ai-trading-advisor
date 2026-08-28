"""Origin record of one sentiment-feed fetch (Stage 4D).

Parallel to ``app.news.provenance.NewsProvenance`` but scoped to Stage 4D
sentiment facts - not reused directly because ``NewsDataSource`` is a closed
vocabulary of news-feed endpoint kinds that should not grow sentiment-feed
members onto it. A standalone, per-fetch audit record - not embedded inside
``NewsSentimentObservation``, mirroring how no sibling provenance model is
embedded inside its fact model.

No confidence/reliability/credibility/probability/provider-ranking
classification lives here, mirroring every prior stage's provenance model:
no such policy exists yet, and inventing one now would be an unreviewed
numeric/categorical judgment.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from app.core.models.base import DomainModel, Timestamp


class NewsIntelDataSource(StrEnum):
    """Kind of endpoint one sentiment record was fetched from.

    Deliberately a single member for now: no concrete provider integration
    exists yet to justify a second one - add it later, deliberately, once
    real provider evidence exists (mirrors ``app.news.provenance.NewsDataSource``).
    """

    SENTIMENT_FEED = "SENTIMENT_FEED"


class NewsIntelProvenance(DomainModel):
    """Where one sentiment-feed fetch came from, and when."""

    provider: str = Field(min_length=1)
    source: NewsIntelDataSource
    fetched_at: Timestamp
    provider_timestamp: Timestamp | None = None
    source_url: str | None = Field(default=None, min_length=1)

    @property
    def label(self) -> str:
        """Compact ``provider:source`` label, mirroring ``NewsProvenance.label``."""
        return f"{self.provider}:{self.source.value}"


__all__ = ["NewsIntelDataSource", "NewsIntelProvenance"]

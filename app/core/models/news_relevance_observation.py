"""Stage 4D deterministic news-relevance fact.

The result of one deterministic, on-demand computation: does a queried
``Symbol`` appear among the provider-supplied symbols on one retained
``NewsItem`` observation? No text parsing, no keyword/tag interpretation, no
fuzzy matching, no entity resolution, and no numeric relevance score - see
``app.news_intel.relevance.compute_relevance``, the sole producer of this
model.

Not a fetched/independently-sourced fact - unlike
``app.core.models.news_sentiment_observation.NewsSentimentObservation``,
there is no history, protocol or provenance for this model: it is a pure,
zero-cost-to-recompute transform of data ``app.news.NewsItemHistory``
already retains (see the Stage 4D design report, "Storage/history
decision").

``matched=False`` has two structurally distinct causes, and this model keeps
them distinct rather than collapsing both to "not relevant":

- ``quality=VALID, matched=False`` - the source item did carry
  provider-supplied symbols, none of which was the queried one: a genuine,
  checked negative.
- ``quality=UNAVAILABLE, matched=False`` - the source item carried no
  provider-supplied symbols at all, so no determination could be made:
  "unknown", never silently reported as "not relevant".
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from app.core.enums.news_intel import RelevanceMethod
from app.core.enums.quality import FeatureQuality
from app.core.models.base import DomainModel, Symbol, Timestamp


class NewsRelevanceObservation(DomainModel):
    """One deterministic relevance determination: one ``NewsItem`` observation vs. one ``Symbol``."""

    source_provider: str = Field(min_length=1)
    source_provider_item_id: str = Field(min_length=1)
    source_received_at: Timestamp
    symbol: Symbol
    matched: bool
    quality: FeatureQuality
    method: RelevanceMethod
    computed_at: Timestamp

    @model_validator(mode="after")
    def _validate_matched_implies_valid(self) -> Self:
        if self.matched and self.quality is not FeatureQuality.VALID:
            raise ValueError("a matched=True observation must carry quality=VALID")
        return self


__all__ = ["NewsRelevanceObservation"]

"""Stage 4D deterministic relevance computation.

One pure function, no history, no protocol, no provenance, no exceptions:
relevance is a zero-cost-to-recompute transform of data
``app.news.NewsItemHistory`` already retains, not an independently-sourced
fact - see the Stage 4D design report, "Storage/history decision". This
module deliberately defines no exception class and no ``Protocol``: every
``(item, symbol)`` pair has a well-defined deterministic answer already
covered by ordinary model validation, so there is no failure mode of its
own to name.

``compute_relevance`` never reads a wall clock, never touches randomness,
and never parses ``NewsItem.headline``/``body``/``provider_tags`` - only
exact ``str`` membership in ``NewsItem.provider_symbols`` against the
caller-supplied ``symbol``.
"""

from __future__ import annotations

from app.core.enums.news_intel import RelevanceMethod
from app.core.enums.quality import FeatureQuality
from app.core.models.base import Symbol, Timestamp
from app.core.models.news_item import NewsItem
from app.core.models.news_relevance_observation import NewsRelevanceObservation


def compute_relevance(item: NewsItem, symbol: Symbol, computed_at: Timestamp) -> NewsRelevanceObservation:
    """Deterministically compare ``symbol`` against ``item.provider_symbols``.

    ``item.provider_symbols`` non-empty: ``quality=VALID`` and ``matched``
    reflects an exact membership check - a real, checked determination
    either way. ``item.provider_symbols`` empty: ``quality=UNAVAILABLE`` and
    ``matched=False`` - nothing to check against, "unknown", never silently
    reported as "not relevant".
    """
    if item.provider_symbols:
        return NewsRelevanceObservation(
            source_provider=item.provider,
            source_provider_item_id=item.provider_item_id,
            source_received_at=item.received_at,
            symbol=symbol,
            matched=symbol in item.provider_symbols,
            quality=FeatureQuality.VALID,
            method=RelevanceMethod.PROVIDER_SYMBOL_EXACT_MATCH,
            computed_at=computed_at,
        )
    return NewsRelevanceObservation(
        source_provider=item.provider,
        source_provider_item_id=item.provider_item_id,
        source_received_at=item.received_at,
        symbol=symbol,
        matched=False,
        quality=FeatureQuality.UNAVAILABLE,
        method=RelevanceMethod.PROVIDER_SYMBOL_EXACT_MATCH,
        computed_at=computed_at,
    )


__all__ = ["compute_relevance"]

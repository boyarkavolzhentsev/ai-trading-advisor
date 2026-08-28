"""Stage 4D sentiment/relevance enums - deterministic vocabulary only.

No member here encodes an importance/priority/market-impact judgment, a
reliability/credibility classification, or a trading direction - see
``app.core.models.news_relevance_observation``/
``app.core.models.news_sentiment_observation`` for the facts-only contracts
this vocabulary backs.
"""

from __future__ import annotations

from enum import StrEnum


class RelevanceMethod(StrEnum):
    """Deterministic method used to compute one ``NewsRelevanceObservation``.

    Single member for now: Stage 4D implements exact provider-symbol
    membership only (see ``app.news_intel.relevance``). A second method
    would be a new member, never a silent change of what an existing
    member means.
    """

    PROVIDER_SYMBOL_EXACT_MATCH = "PROVIDER_SYMBOL_EXACT_MATCH"


__all__ = ["RelevanceMethod"]

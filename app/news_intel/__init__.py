"""Stage 4D: deterministic sentiment/relevance foundation over ``app.news``.

Two structurally distinct halves, not one uniform skeleton - see the Stage
4D design report, "Storage/history decision":

1. ``app.news_intel.relevance`` - one pure function
   (``compute_relevance``) with no history, no protocol, no provenance, no
   exceptions: relevance is a zero-cost-to-recompute transform of data
   ``app.news.NewsItemHistory`` already retains, not an independently-sourced
   fact.
2. Provider-native sentiment facts
   (``app.core.models.news_sentiment_observation.NewsSentimentObservation``)
   - a genuinely new, independently-sourced fact type, given the full
   Stage 4A-4C-style skeleton: a provider Protocol
   (``NewsSentimentProvider``), a bounded version-preserving history
   (``NewsSentimentObservationHistory``), and standalone provenance
   (``NewsIntelProvenance``).

No internally-derived sentiment of any kind exists in this package -
``NewsSentimentObservation`` is provider-native only, and carries no
``origin`` field: every record here *is* provider-native by definition. A
future internally-derived sentiment feature belongs to a separately
reviewed feature/analyst contract, never mixed into this schema.

Unlike ``app.macro``/``app.rates``, and mirroring ``app.news``, there is no
``revision_number`` and no revision-conflict rule on the sentiment side: a
sentiment feed revising its own reported score is a normal correction, not
a conflict.

Independent from ``app.flow*`` and ``app.technical*`` - see
``tests/test_news_intel_no_flow_coupling.py`` and
``tests/test_news_intel_no_technical_coupling.py``.
"""

from __future__ import annotations

from app.news_intel.exceptions import (
    DuplicateNewsSentimentError,
    InvalidProviderResponseError,
    NewsIntelDataError,
    ProviderUnavailableError,
    UnknownSentimentObservationError,
)
from app.news_intel.provenance import NewsIntelDataSource, NewsIntelProvenance
from app.news_intel.relevance import compute_relevance
from app.news_intel.sentiment_history import DEFAULT_CAPACITY, NewsSentimentObservationHistory
from app.news_intel.sentiment_protocol import DEFAULT_SENTIMENT_LIMIT, NewsSentimentProvider

__all__ = [
    "DEFAULT_CAPACITY",
    "DEFAULT_SENTIMENT_LIMIT",
    "DuplicateNewsSentimentError",
    "InvalidProviderResponseError",
    "NewsIntelDataError",
    "NewsIntelDataSource",
    "NewsIntelProvenance",
    "NewsSentimentObservationHistory",
    "NewsSentimentProvider",
    "ProviderUnavailableError",
    "UnknownSentimentObservationError",
    "compute_relevance",
]

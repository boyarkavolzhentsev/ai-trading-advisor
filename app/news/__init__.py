"""Stage 4C: provider-agnostic news facts.

Normalized facts only - no sentiment, no relevance/importance scoring, no
market-impact interpretation, no analyst, no supervisor, no real HTTP
provider integration. Layering mirrors ``app.macro``/``app.rates``:

1. a provider Protocol (``NewsProvider``) future concrete adapters satisfy;
2. a domain contract (``app.core.models.news_item.NewsItem``);
3. ``app.news.history`` - a bounded, append-only, version-preserving news
   log.

Unlike ``app.macro``/``app.rates``, there is no ``revision_number`` and no
revision-conflict rule: news carries no provider-native revision counter,
and a changed article at the same identity is a normal correction, not a
conflict - see ``app.news.history`` for the full rationale. There is also
no ``app.news.quality`` module: news has no scheduled/postponed/cancelled-
style lifecycle to infer, mirroring ``app.rates``'s absence of a quality
module.

Independent from ``app.flow*`` and ``app.technical*`` - see
``tests/test_news_no_flow_coupling.py`` and
``tests/test_news_no_technical_coupling.py``.
"""

from __future__ import annotations

from app.news.exceptions import (
    DuplicateNewsItemError,
    InvalidProviderResponseError,
    NewsDataError,
    ProviderUnavailableError,
    UnknownNewsItemError,
)
from app.news.history import DEFAULT_CAPACITY, NewsItemHistory
from app.news.protocols import DEFAULT_NEWS_LIMIT, NewsProvider
from app.news.provenance import NewsDataSource, NewsProvenance

__all__ = [
    "DEFAULT_CAPACITY",
    "DEFAULT_NEWS_LIMIT",
    "DuplicateNewsItemError",
    "InvalidProviderResponseError",
    "NewsDataError",
    "NewsDataSource",
    "NewsItemHistory",
    "NewsProvenance",
    "NewsProvider",
    "ProviderUnavailableError",
    "UnknownNewsItemError",
]

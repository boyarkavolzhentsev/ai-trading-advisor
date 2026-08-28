"""Provider-agnostic news contract (Stage 4C).

Mirrors ``app.macro.protocols``/``app.rates.protocols``'s style: a narrow,
single-capability, ``runtime_checkable`` ``Protocol`` with a plain
synchronous method returning typed domain models, raising ``NewsDataError``
subclasses on failure. News polling at this foundation layer is a discrete,
low-frequency fetch over a time range - there is no continuous-stream
requirement analogous to the Stage 1C real-time layer, so this Protocol
stays synchronous by design, mirroring both siblings.

``symbols`` filters on whatever the provider itself already tagged an item
with (``NewsItem.provider_symbols``) - it is a pass-through query parameter,
never our own entity resolution. No ``tags`` filter parameter exists here:
``NewsItem.provider_tags`` is unnormalized free text, and filtering on it is
deferred until a real consumer justifies it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.core.models.base import Timestamp
from app.core.models.news_item import NewsItem

DEFAULT_NEWS_LIMIT = 100
"""Number of items requested when the caller does not specify a limit."""


@runtime_checkable
class NewsProvider(Protocol):
    """Read-only source of news items for one range of time."""

    def get_news(
        self,
        start: Timestamp,
        end: Timestamp,
        *,
        symbols: Sequence[str] | None = None,
        limit: int = DEFAULT_NEWS_LIMIT,
    ) -> list[NewsItem]:
        """Return up to ``limit`` items with ``published_at`` in ``[start, end]``."""
        ...


__all__ = ["DEFAULT_NEWS_LIMIT", "NewsProvider"]

"""Provider-agnostic sentiment contract (Stage 4D).

Mirrors ``app.news.protocols``'s style: a narrow, single-capability,
``runtime_checkable`` ``Protocol`` with a plain synchronous method returning
typed domain models, raising ``NewsIntelDataError`` subclasses on failure.
Sentiment polling at this foundation layer is a discrete, low-frequency
fetch over a time range - there is no continuous-stream requirement
analogous to the Stage 1C real-time layer, so this Protocol stays
synchronous by design, mirroring every prior Foundation stage.

``symbols`` filters on the queried target entity - a pass-through query
parameter, never our own entity resolution.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.core.models.base import Timestamp
from app.core.models.news_sentiment_observation import NewsSentimentObservation

DEFAULT_SENTIMENT_LIMIT = 100
"""Number of observations requested when the caller does not specify a limit."""


@runtime_checkable
class NewsSentimentProvider(Protocol):
    """Read-only source of provider-native sentiment observations for one range of time."""

    def get_sentiment(
        self,
        start: Timestamp,
        end: Timestamp,
        *,
        symbols: Sequence[str] | None = None,
        limit: int = DEFAULT_SENTIMENT_LIMIT,
    ) -> list[NewsSentimentObservation]:
        """Return up to ``limit`` observations with ``published_at`` in ``[start, end]``."""
        ...


__all__ = ["DEFAULT_SENTIMENT_LIMIT", "NewsSentimentProvider"]

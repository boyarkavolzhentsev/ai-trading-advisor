"""Stage 4D ``NewsSentimentProvider`` structural protocol conformance."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from app.core.models.news_sentiment_observation import NewsSentimentObservation
from app.news_intel.sentiment_protocol import DEFAULT_SENTIMENT_LIMIT, NewsSentimentProvider


class _ConformingProvider:
    def get_sentiment(
        self,
        start: datetime,
        end: datetime,
        *,
        symbols: Sequence[str] | None = None,
        limit: int = DEFAULT_SENTIMENT_LIMIT,
    ) -> list[NewsSentimentObservation]:
        return []


class _NonConformingProvider:
    def some_other_method(self) -> None:
        pass


def test_conforming_provider_satisfies_protocol() -> None:
    assert isinstance(_ConformingProvider(), NewsSentimentProvider)


def test_non_conforming_provider_does_not_satisfy_protocol() -> None:
    assert not isinstance(_NonConformingProvider(), NewsSentimentProvider)


def test_default_sentiment_limit_is_positive() -> None:
    assert DEFAULT_SENTIMENT_LIMIT > 0

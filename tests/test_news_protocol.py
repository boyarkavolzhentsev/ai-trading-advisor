"""Stage 4C ``NewsProvider`` structural protocol conformance."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from app.core.models.news_item import NewsItem
from app.news.protocols import DEFAULT_NEWS_LIMIT, NewsProvider


class _ConformingProvider:
    def get_news(
        self,
        start: datetime,
        end: datetime,
        *,
        symbols: Sequence[str] | None = None,
        limit: int = DEFAULT_NEWS_LIMIT,
    ) -> list[NewsItem]:
        return []


class _NonConformingProvider:
    def some_other_method(self) -> None:
        pass


def test_conforming_provider_satisfies_protocol() -> None:
    assert isinstance(_ConformingProvider(), NewsProvider)


def test_non_conforming_provider_does_not_satisfy_protocol() -> None:
    assert not isinstance(_NonConformingProvider(), NewsProvider)


def test_default_news_limit_is_positive() -> None:
    assert DEFAULT_NEWS_LIMIT > 0

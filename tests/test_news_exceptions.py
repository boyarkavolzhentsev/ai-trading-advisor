"""Stage 4C error hierarchy shape."""

from __future__ import annotations

from app.news.exceptions import (
    DuplicateNewsItemError,
    InvalidProviderResponseError,
    NewsDataError,
    ProviderUnavailableError,
    UnknownNewsItemError,
)


def test_all_news_errors_derive_from_news_data_error() -> None:
    for exc_cls in (
        ProviderUnavailableError,
        InvalidProviderResponseError,
        UnknownNewsItemError,
        DuplicateNewsItemError,
    ):
        assert issubclass(exc_cls, NewsDataError)


def test_news_data_error_derives_from_exception() -> None:
    assert issubclass(NewsDataError, Exception)


def test_no_revision_conflict_error_exists() -> None:
    """Required design decision: news has no revision-conflict rule (see
    ``app.news.history`` module docstring) - so no such error class exists."""
    import app.news.exceptions as exceptions_module

    assert not hasattr(exceptions_module, "RevisionConflictError")


def test_exceptions_are_distinct_classes() -> None:
    classes = {
        ProviderUnavailableError,
        InvalidProviderResponseError,
        UnknownNewsItemError,
        DuplicateNewsItemError,
    }
    assert len(classes) == 4

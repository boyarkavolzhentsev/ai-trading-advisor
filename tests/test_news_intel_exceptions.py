"""Stage 4D error hierarchy shape."""

from __future__ import annotations

from app.news_intel.exceptions import (
    DuplicateNewsSentimentError,
    InvalidProviderResponseError,
    NewsIntelDataError,
    ProviderUnavailableError,
    UnknownSentimentObservationError,
)


def test_all_news_intel_errors_derive_from_news_intel_data_error() -> None:
    for exc_cls in (
        ProviderUnavailableError,
        InvalidProviderResponseError,
        UnknownSentimentObservationError,
        DuplicateNewsSentimentError,
    ):
        assert issubclass(exc_cls, NewsIntelDataError)


def test_news_intel_data_error_derives_from_exception() -> None:
    assert issubclass(NewsIntelDataError, Exception)


def test_no_revision_conflict_error_exists() -> None:
    """Required design decision: sentiment has no revision-conflict rule -
    so no such error class exists."""
    import app.news_intel.exceptions as exceptions_module

    assert not hasattr(exceptions_module, "RevisionConflictError")


def test_exceptions_are_distinct_classes() -> None:
    classes = {
        ProviderUnavailableError,
        InvalidProviderResponseError,
        UnknownSentimentObservationError,
        DuplicateNewsSentimentError,
    }
    assert len(classes) == 4


def test_no_relevance_specific_error_exists() -> None:
    """Relevance is a pure computation with no failure mode of its own -
    no dedicated exception exists for it anywhere in this package."""
    import app.news_intel.exceptions as exceptions_module

    forbidden_names = {"RelevanceError", "InvalidRelevanceTargetError", "RelevanceComputationError"}
    defined = set(vars(exceptions_module))
    assert forbidden_names.isdisjoint(defined)

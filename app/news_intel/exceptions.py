"""Stage 4D sentiment errors.

Every failure that crosses the ``NewsSentimentProvider`` boundary, or that
``app.news_intel.sentiment_history`` detects, is one of these. Mirrors
``app.news.exceptions``'s taxonomy - a transient provider failure is kept
distinct from a contract violation, which is kept distinct from a
domain-specific duplicate. None of these may ever be silently absorbed into
a legitimate ``NewsSentimentObservation`` value.

Scoped to sentiment only: relevance is a pure computation
(``app.news_intel.relevance``) with no failure mode of its own beyond what
``NewsRelevanceObservation``'s own model validation already covers, so no
relevance-specific exception exists here or anywhere in this package.

Deliberately has no ``RevisionConflictError`` analog, mirroring
``app.news.exceptions``: sentiment carries no provider-native revision
counter, and a changed sentiment fact at the same identity is a normal,
expected update (a sentiment feed revising its own score as more signal
arrives), not a conflict - see
``app.news_intel.sentiment_history.NewsSentimentObservationHistory.append``.
"""

from __future__ import annotations


class NewsIntelDataError(Exception):
    """Base class for every Stage 4D sentiment failure."""


class ProviderUnavailableError(NewsIntelDataError):
    """Provider could not be reached or failed transiently.

    Network errors, timeouts, rate limiting and 5xx responses.
    """


class InvalidProviderResponseError(NewsIntelDataError):
    """Provider answered, but the payload does not satisfy the contract.

    Missing required fields, non-numeric values where a number is required,
    or a structurally malformed record.
    """


class UnknownSentimentObservationError(NewsIntelDataError):
    """Requested sentiment observation is not known to the provider or history store."""


class DuplicateNewsSentimentError(NewsIntelDataError):
    """Identical sentiment identity observation appended twice, unchanged.

    Raised when an appended observation's semantic fingerprint (every field
    except the Stage 4D sentiment ``received_at``) exactly matches an
    already-recorded observation at the same identity - a re-poll of the
    same fact, not a new version.
    """


__all__ = [
    "DuplicateNewsSentimentError",
    "InvalidProviderResponseError",
    "NewsIntelDataError",
    "ProviderUnavailableError",
    "UnknownSentimentObservationError",
]

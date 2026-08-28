"""Stage 4C news errors.

Every failure that crosses the ``NewsProvider`` boundary, or that
``app.news.history`` detects, is one of these. Mirrors
``app.macro.exceptions``/``app.rates.exceptions``'s taxonomy: a transient
provider failure is kept distinct from a contract violation, which is kept
distinct from a domain-specific conflict. None of these may ever be silently
absorbed into a legitimate ``NewsItem`` value.

Deliberately has no ``RevisionConflictError`` analog, unlike
``app.macro.exceptions``/``app.rates.exceptions``: news carries no
provider-native revision counter and a changed article at the same identity
is a normal, expected correction, not a conflict - see
``app.news.history.NewsItemHistory.append``.
"""

from __future__ import annotations


class NewsDataError(Exception):
    """Base class for every Stage 4C news failure."""


class ProviderUnavailableError(NewsDataError):
    """Provider could not be reached or failed transiently.

    Network errors, timeouts, rate limiting and 5xx responses.
    """


class InvalidProviderResponseError(NewsDataError):
    """Provider answered, but the payload does not satisfy the contract.

    Missing required fields, non-string values where a string is required,
    or a structurally malformed record.
    """


class UnknownNewsItemError(NewsDataError):
    """Requested news item is not known to the provider or history store."""


class DuplicateNewsItemError(NewsDataError):
    """Identical ``(provider, provider_item_id)`` observation appended twice, unchanged.

    Raised when an appended item's semantic fingerprint (every field except
    ``received_at``) exactly matches an already-recorded observation at the
    same identity - a re-poll of the same fact, not a new version.
    """


__all__ = [
    "DuplicateNewsItemError",
    "InvalidProviderResponseError",
    "NewsDataError",
    "ProviderUnavailableError",
    "UnknownNewsItemError",
]

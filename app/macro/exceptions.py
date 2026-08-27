"""Stage 4A economic-calendar errors.

Every failure that crosses the ``EconomicCalendarProvider`` boundary, or that
``app.macro.history.EconomicEventHistory`` detects, is one of these. Mirrors
``app.market_data.exceptions``'s taxonomy: a transient provider failure is
kept distinct from a contract violation, which is kept distinct from a
domain-specific conflict. None of these may ever be silently absorbed into a
legitimate ``EconomicEvent``/``EconomicEventStatus`` value.
"""

from __future__ import annotations


class EconomicDataError(Exception):
    """Base class for every Stage 4A economic-calendar failure."""


class ProviderUnavailableError(EconomicDataError):
    """Provider could not be reached or failed transiently.

    Network errors, timeouts, rate limiting and 5xx responses.
    """


class InvalidProviderResponseError(EconomicDataError):
    """Provider answered, but the payload does not satisfy the contract.

    Missing required fields, non-numeric values where a number is required,
    or a structurally malformed record.
    """


class UnknownEventError(EconomicDataError):
    """Requested event is not known to the provider or history store."""


class RevisionConflictError(EconomicDataError):
    """Same ``(provider, provider_event_id, revision_number)`` reported with
    conflicting content.

    Raised instead of silently overwriting the earlier record - see
    ``EconomicEventHistory.append``.
    """


class DuplicateEventError(EconomicDataError):
    """Identical ``(provider, provider_event_id, revision_number)`` appended twice, unchanged.

    Kept distinct from ``RevisionConflictError``: an exact repeat of an
    already-stored record is a duplicate append attempt, not a conflicting
    one.
    """


__all__ = [
    "DuplicateEventError",
    "EconomicDataError",
    "InvalidProviderResponseError",
    "ProviderUnavailableError",
    "RevisionConflictError",
    "UnknownEventError",
]

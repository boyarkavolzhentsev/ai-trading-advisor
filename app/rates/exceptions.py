"""Stage 4B rates/yields errors.

Every failure that crosses ``PolicyRateProvider``/``GovernmentYieldProvider``,
or that ``app.rates.history`` detects, is one of these. Mirrors
``app.macro.exceptions``'s taxonomy: a transient provider failure is kept
distinct from a contract violation, which is kept distinct from a
domain-specific conflict. None of these may ever be silently absorbed into a
legitimate ``PolicyRateObservation``/``GovernmentYieldObservation`` value.
"""

from __future__ import annotations


class RatesDataError(Exception):
    """Base class for every Stage 4B rates/yields failure."""


class ProviderUnavailableError(RatesDataError):
    """Provider could not be reached or failed transiently.

    Network errors, timeouts, rate limiting and 5xx responses.
    """


class InvalidProviderResponseError(RatesDataError):
    """Provider answered, but the payload does not satisfy the contract.

    Missing required fields, non-numeric values where a number is required,
    or a structurally malformed record.
    """


class UnknownSeriesError(RatesDataError):
    """Requested series is not known to the provider or history store."""


class RevisionConflictError(RatesDataError):
    """Same observation-revision identity reported with conflicting content.

    Identity is ``(provider, provider_series_id, observation_time,
    revision_number)``. Raised instead of silently overwriting the earlier
    observation - see ``PolicyRateObservationHistory``/
    ``GovernmentYieldObservationHistory``.
    """


class DuplicateObservationError(RatesDataError):
    """Identical observation revision identity appended twice, unchanged.

    Kept distinct from ``RevisionConflictError``: an exact repeat of an
    already-stored observation is a duplicate append attempt, not a
    conflicting one.
    """


__all__ = [
    "DuplicateObservationError",
    "InvalidProviderResponseError",
    "ProviderUnavailableError",
    "RatesDataError",
    "RevisionConflictError",
    "UnknownSeriesError",
]

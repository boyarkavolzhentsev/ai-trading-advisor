"""Stage 4E on-chain errors.

Every failure that crosses the ``OnChainProvider`` boundary, or that
``app.onchain.history`` detects, is one of these. Mirrors
``app.news.exceptions``'s taxonomy: a transient provider failure is kept
distinct from a contract violation, which is kept distinct from a
domain-specific duplicate. None of these may ever be silently absorbed into
a legitimate observation value.

One shared hierarchy across all four metric families, not one per family:
there is no genuine semantic difference between "duplicate network-activity
observation" and "duplicate exchange-flow observation" - both are the
identical structural situation (fingerprint match at identity) - so a
single ``DuplicateOnChainObservationError``/``UnknownOnChainObservationError``
pair suffices.

Deliberately has no ``RevisionConflictError`` analog, mirroring
``app.news.exceptions``: on-chain observations carry no provider-native
revision counter, and a changed observation at the same identity is a
normal, expected correction (e.g. a reorg-driven recount), not a conflict -
see ``app.onchain.history``.
"""

from __future__ import annotations


class OnChainDataError(Exception):
    """Base class for every Stage 4E on-chain failure."""


class ProviderUnavailableError(OnChainDataError):
    """Provider could not be reached or failed transiently.

    Network errors, timeouts, rate limiting and 5xx responses.
    """


class InvalidProviderResponseError(OnChainDataError):
    """Provider answered, but the payload does not satisfy the contract.

    Missing required fields, non-numeric values where a number is required,
    or a structurally malformed record.
    """


class UnknownOnChainObservationError(OnChainDataError):
    """Requested observation is not known to the provider or history store."""


class DuplicateOnChainObservationError(OnChainDataError):
    """Identical observation identity appended twice, unchanged.

    Raised when an appended observation's semantic fingerprint (every field
    except ``received_at``) exactly matches an already-recorded observation
    at the same identity - a re-poll of the same fact, not a new version.
    """


__all__ = [
    "DuplicateOnChainObservationError",
    "InvalidProviderResponseError",
    "OnChainDataError",
    "ProviderUnavailableError",
    "UnknownOnChainObservationError",
]

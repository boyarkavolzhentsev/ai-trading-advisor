"""Stage 3C input-validation errors.

Every error here signals a programming/orchestration mistake in how
``TechnicalAnalysisResult`` objects were assembled and handed to
``TechnicalSupervisor.aggregate`` - never a legitimate market condition.
Stage 3C must fail loudly on these rather than disguise them as evidence
unavailability (that legitimate case is
``app.core.enums.technical_supervisor.TechnicalSupervisorOutcome.INSUFFICIENT_EVIDENCE``,
which only ever arises from analyst/timeframe cells that actually ran and
abstained, or are absent - never from malformed input). Mirrors
``app.flow_supervisor.errors`` one contour over.
"""

from __future__ import annotations


class TechnicalSupervisorInputError(ValueError):
    """Base class for all Stage 3C input-contract violations."""


class EmptyResultsError(TechnicalSupervisorInputError):
    """Raised when ``aggregate`` is called with zero results.

    Stage 3C cannot construct a result without at least one
    ``TechnicalAnalysisResult`` to anchor its evaluation identity (symbol,
    contract_type, observation_time) - even an ABSTAINED result carries that
    identity, so an empty sequence is never a legitimate "insufficient
    evidence" case, only a caller error.
    """


class DuplicateAnalystTimeframeResultError(TechnicalSupervisorInputError):
    """Raised when more than one supplied result shares the same
    ``(analyst_type, timeframe)`` key."""


class UnexpectedAnalystResultError(TechnicalSupervisorInputError):
    """Raised when a supplied result's ``analyst_type`` is not in ``expected_analysts``."""


class UnexpectedTimeframeResultError(TechnicalSupervisorInputError):
    """Raised when a supplied result's ``timeframe`` is not in ``expected_timeframes``."""


class InconsistentSnapshotError(TechnicalSupervisorInputError):
    """Raised when supplied results do not share one evaluation identity.

    Covers symbol/contract_type/observation_time mismatches and
    provenance-key collisions with differing values across results.
    Deliberately does NOT cover ``last_closed_candle_time``, which is
    expected to legitimately differ across timeframes.
    """


__all__ = [
    "DuplicateAnalystTimeframeResultError",
    "EmptyResultsError",
    "InconsistentSnapshotError",
    "TechnicalSupervisorInputError",
    "UnexpectedAnalystResultError",
    "UnexpectedTimeframeResultError",
]

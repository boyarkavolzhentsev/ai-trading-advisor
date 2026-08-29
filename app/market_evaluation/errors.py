"""Stage 5A input-validation errors.

Every error here signals a programming/orchestration mistake in how
Flow/Technical/External-Intelligence supervisor results and a
``MarketEvaluationContext`` were assembled and handed to
``MarketEvaluator.evaluate`` - never a legitimate market condition. Stage 5A
must fail loudly on these rather than disguise them as evidence
unavailability (that legitimate case is
``app.core.enums.market_evaluation.MarketEvaluationOutcome.INSUFFICIENT_EVIDENCE``,
which arises only from contours that are missing or ran and found
insufficient evidence - never from malformed/mismatched input). Mirrors
``app.flow_supervisor.errors``/``app.technical_supervisor.errors``/
``app.external_intelligence_supervisor.errors`` one contour over.
"""

from __future__ import annotations


class MarketEvaluationInputError(ValueError):
    """Base class for all Stage 5A input-contract violations."""


class ScopeMismatchError(MarketEvaluationInputError):
    """Raised when a supplied Flow or Technical result's ``(symbol,
    contract_type)`` does not match the evaluation's
    ``MarketEvaluationContext``.

    A mismatched instrument is evidence about the *wrong* thing, not
    legitimate evidence absence - it is never silently downgraded to a
    ``MISSING`` contour.
    """


class FutureContourTimeError(MarketEvaluationInputError):
    """Raised when a supplied contour's own semantic timestamp is strictly
    after the evaluation's ``evaluation_time``.

    Each upstream supervisor owns its own semantic staleness; this check is
    strictly sequencing - a result timestamped after the stated evaluation
    instant can only reflect a caller error.
    """


__all__ = [
    "FutureContourTimeError",
    "MarketEvaluationInputError",
    "ScopeMismatchError",
]

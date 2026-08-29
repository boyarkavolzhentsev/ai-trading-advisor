"""Stage 4G input-validation errors.

Every error here signals a programming/orchestration mistake in how
``ExternalIntelligenceAnalysisResult`` objects were assembled and handed to
``ExternalIntelligenceSupervisor.aggregate`` - never a legitimate market
condition. Stage 4G must fail loudly on these rather than disguise them as
evidence unavailability (that legitimate case is
``app.core.enums.external_intelligence_supervisor.ExternalIntelligenceSupervisorOutcome.INSUFFICIENT_EVIDENCE``,
which arises from analyst types that abstained, are missing, or from an
empty input sequence - never from malformed input). Mirrors
``app.flow_supervisor.errors``/``app.technical_supervisor.errors`` one
contour over.
"""

from __future__ import annotations


class ExternalIntelligenceSupervisorInputError(ValueError):
    """Base class for all Stage 4G input-contract violations."""


class DuplicateAnalystScopeResultError(ExternalIntelligenceSupervisorInputError):
    """Raised when more than one supplied result shares the same
    ``(analyst_type, native_scope)`` identity - regardless of whether their
    content is identical or divergent. No last-write-wins, no quality or
    timestamp preference: the caller must resolve the duplication upstream.
    """


class FutureResultTimeError(ExternalIntelligenceSupervisorInputError):
    """Raised when a supplied result's ``analysis_time`` is strictly after
    the supervisor's own ``analysis_time``.

    Stage 4F owns semantic staleness (age *within* a result); this check is
    strictly sequencing - a result timestamped after the supervisor's own
    stated instant can only reflect a caller error, never a legitimate
    evidence-availability state.
    """


__all__ = [
    "DuplicateAnalystScopeResultError",
    "ExternalIntelligenceSupervisorInputError",
    "FutureResultTimeError",
]

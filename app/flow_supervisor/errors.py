"""Stage 2C input-validation errors.

Every error here signals a programming/orchestration mistake in how
``FlowAnalysisResult`` objects were assembled and handed to
``FlowSupervisor.aggregate`` - never a legitimate market condition. Stage 2C
must fail loudly on these rather than disguise them as evidence
unavailability (that legitimate case is
``app.core.enums.flow_supervisor.FlowSupervisorOutcome.INSUFFICIENT_EVIDENCE``,
which only ever arises from analysts that actually ran and abstained, or are
absent - never from malformed input).
"""

from __future__ import annotations


class FlowSupervisorInputError(ValueError):
    """Base class for all Stage 2C input-contract violations."""


class EmptyResultsError(FlowSupervisorInputError):
    """Raised when ``aggregate`` is called with zero results.

    Stage 2C cannot construct a result without at least one
    ``FlowAnalysisResult`` to anchor its snapshot identity (symbol,
    contract_type, observation_time, windows) - even an ABSTAINED result
    carries that identity, so an empty sequence is never a legitimate
    "insufficient evidence" case, only a caller error.
    """


class DuplicateAnalystResultError(FlowSupervisorInputError):
    """Raised when more than one supplied result shares the same ``AnalystType``."""


class UnexpectedAnalystResultError(FlowSupervisorInputError):
    """Raised when a supplied result's ``AnalystType`` is not in ``expected_analysts``."""


class InconsistentSnapshotError(FlowSupervisorInputError):
    """Raised when supplied results do not share one snapshot identity.

    Covers symbol/contract_type/observation_time/windows mismatches and
    provenance-key collisions with differing values across results.
    """


__all__ = [
    "DuplicateAnalystResultError",
    "EmptyResultsError",
    "FlowSupervisorInputError",
    "InconsistentSnapshotError",
    "UnexpectedAnalystResultError",
]

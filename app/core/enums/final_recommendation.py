"""Final Recommendation vocabulary (Final Runtime Integration, Part D).

Describes only the coarse construction outcome of converting one already-
completed ``DecisionRiskPipelineResult`` into broker-normalized, advisory-only
recommendations - never a trade approval, never an execution decision, never
a ranking/preference across families. No member here means BUY/SELL/ENTER/
EXIT/HOLD or a qualitative market judgment; that content stays entirely
within the embedded ``CandidateTradeSetup``/``SessionFamilyResult`` this
stage never reinterprets.
"""

from __future__ import annotations

from enum import StrEnum


class FinalRecommendationOutcome(StrEnum):
    """Coarse, participation-derived verdict across every family Stage 9
    produced a result for - or the pipeline-level fail-closed state when
    Stage 9 never ran at all.

    ``PIPELINE_BLOCKED_BEFORE_RISK`` mirrors
    ``DecisionRiskPipelineOutcome.BLOCKED_BEFORE_RISK`` exactly: Runtime Fact
    Assembly was not ``READY`` this cycle, so Stage 7/8/9 - and therefore
    Stage 10C broker sizing - never ran.
    """

    SOME_ACTIONABLE = "SOME_ACTIONABLE"
    NO_ACTIONABLE_FAMILY = "NO_ACTIONABLE_FAMILY"
    PIPELINE_BLOCKED_BEFORE_RISK = "PIPELINE_BLOCKED_BEFORE_RISK"


class FinalRecommendationVerdict(StrEnum):
    """Per-family Final Recommendation verdict.

    ``ACTIONABLE`` means only that a concrete, broker-normalized advisory
    recommendation was constructed - never that a trade, position, or
    execution of any kind has occurred or been approved.
    """

    ACTIONABLE = "ACTIONABLE"
    BLOCKED = "BLOCKED"


class FinalRecommendationBlockReason(StrEnum):
    """Exact structural reason one family did not become ``ACTIONABLE``.

    Every check this stage performs is sequential/short-circuiting for a
    given family - never more than one reason applies at once, mirroring
    ``PortfolioBlockReason``/``SessionBlockReason``'s own "at most one
    reason" discipline rather than ``RiskBlockReason``'s multi-reason one.
    ``SESSION_NOT_ELIGIBLE`` is checked first (a family already
    ``BLOCKED_BY_SESSION`` never reaches broker sizing at all);
    ``SYMBOL_FACTS_MISMATCH`` and ``SETUP_EXPIRED`` are this stage's own
    caller-input preconditions, checked before Stage 10C is ever invoked;
    ``SIZING_NOT_ACTIONABLE`` reflects Stage 10C's own verdict unchanged,
    never re-derived.
    """

    SESSION_NOT_ELIGIBLE = "SESSION_NOT_ELIGIBLE"
    SYMBOL_FACTS_MISMATCH = "SYMBOL_FACTS_MISMATCH"
    SETUP_EXPIRED = "SETUP_EXPIRED"
    SIZING_NOT_ACTIONABLE = "SIZING_NOT_ACTIONABLE"


__all__ = [
    "FinalRecommendationBlockReason",
    "FinalRecommendationOutcome",
    "FinalRecommendationVerdict",
]

"""Stage 9 session-gate enums - deterministic session-policy vocabulary only.

No member here means BUY/SELL/LONG/SHORT/ENTER/EXIT/HOLD, a qualitative
market judgment, a capital-sizing decision, a historical-performance ranking,
or final trade authorization. Every value describes either a per-family
session verdict, the coarse participation-derived outcome across every
family Portfolio produced a result for, or an exact structural/global reason
one family was blocked - never a re-interpretation of Judge/Policy/Risk/
Portfolio's own direction/evidence/allocation content, which stays entirely
out of Stage 9's reach.

``ELIGIBLE_FOR_RUNTIME_REVIEW`` deliberately names the *next* architectural
boundary (Stage 10 MT5/runtime integration), not final approval or
execution: Stage 9 is not the last advisory checkpoint, and V1 remains
advisory-only end to end.
"""

from __future__ import annotations

from enum import StrEnum


class SessionFamilyVerdict(StrEnum):
    """Per-family Stage 9 verdict.

    Never a trade approval: ``ELIGIBLE_FOR_RUNTIME_REVIEW`` means only that
    this family's portfolio allocation is unaffected by any session-level
    block and may proceed to Stage 10 runtime review, never that a trade,
    position, or execution of any kind has been approved.
    """

    ELIGIBLE_FOR_RUNTIME_REVIEW = "ELIGIBLE_FOR_RUNTIME_REVIEW"
    BLOCKED_BY_SESSION = "BLOCKED_BY_SESSION"


class SessionGateOutcome(StrEnum):
    """Coarse, participation-derived verdict across every family Portfolio
    produced a result for.

    Fully derived from per-family ``SessionFamilyVerdict`` values - never a
    selected family, a preferred family, an aggregate direction, or a
    ranking/vote of any kind.
    """

    SOME_ELIGIBLE_FOR_RUNTIME_REVIEW = "SOME_ELIGIBLE_FOR_RUNTIME_REVIEW"
    NO_SESSION_ELIGIBLE_FAMILY = "NO_SESSION_ELIGIBLE_FAMILY"


class SessionBlockReason(StrEnum):
    """Exact structural or global reason one family was blocked.

    Each member maps to exactly one independently-checked fact - never a
    free-text explanation. ``PORTFOLIO_NOT_ELIGIBLE`` is a per-family,
    structural fact (the family was already ``BLOCKED_BY_PORTFOLIO``);
    ``SESSION_LOCKED``, ``LOSS_LIMIT_REACHED`` and ``TARGET_REACHED`` are
    global session-state facts applied identically to every otherwise-
    eligible family and are mutually exclusive by the Stage 9 V1 status
    precedence (``app.statistics.session``).
    """

    PORTFOLIO_NOT_ELIGIBLE = "PORTFOLIO_NOT_ELIGIBLE"
    SESSION_LOCKED = "SESSION_LOCKED"
    LOSS_LIMIT_REACHED = "LOSS_LIMIT_REACHED"
    TARGET_REACHED = "TARGET_REACHED"


__all__ = [
    "SessionBlockReason",
    "SessionFamilyVerdict",
    "SessionGateOutcome",
]

"""Stage 7 risk-gate enums - deterministic account-risk-policy vocabulary only.

No member here means BUY/SELL/LONG/SHORT/ENTER/EXIT/HOLD, a qualitative
market judgment, or final trade authorization. Every value describes either a
per-family risk verdict, the coarse participation-derived outcome across
every family Policy produced a result for, or an exact structural reason one
family was blocked - never a semantic interpretation of Judge/Policy's own
direction/evidence content, which stays entirely out of Stage 7's reach.
"""

from __future__ import annotations

from enum import StrEnum


class RiskFamilyVerdict(StrEnum):
    """Per-family Stage 7 verdict.

    Never a trade approval: ``ELIGIBLE_FOR_PORTFOLIO_REVIEW`` means only that
    this family's account-risk ceiling permits it to proceed to Stage 8
    Portfolio/Diversification review, never that a trade, position, or
    execution of any kind has been approved.
    """

    ELIGIBLE_FOR_PORTFOLIO_REVIEW = "ELIGIBLE_FOR_PORTFOLIO_REVIEW"
    BLOCKED_BY_RISK = "BLOCKED_BY_RISK"


class RiskGateOutcome(StrEnum):
    """Coarse, participation-derived verdict across every family Policy
    produced a result for.

    Fully derived from per-family ``RiskFamilyVerdict`` values - never a
    selected family, a preferred family, an aggregate direction, or a
    ranking/vote of any kind.
    """

    SOME_ELIGIBLE_FOR_PORTFOLIO_REVIEW = "SOME_ELIGIBLE_FOR_PORTFOLIO_REVIEW"
    NO_RISK_ELIGIBLE_FAMILY = "NO_RISK_ELIGIBLE_FAMILY"


class RiskBlockReason(StrEnum):
    """Exact structural reason one family was blocked.

    Each member maps to exactly one independently-checked structural fact -
    never a free-text explanation. ``ZERO_OR_NEGATIVE_RISK_PER_UNIT`` is a
    candidate-input-shape fact independent of account state and may coexist
    with an account-state reason; ``DAILY_LOSS_LIMIT_REACHED`` and
    ``INSUFFICIENT_REMAINING_RISK_BUDGET`` are mutually exclusive by
    evaluation precedence (see ``app.risk.engine``).
    """

    POLICY_NOT_ELIGIBLE = "POLICY_NOT_ELIGIBLE"
    ZERO_OR_NEGATIVE_RISK_PER_UNIT = "ZERO_OR_NEGATIVE_RISK_PER_UNIT"
    DAILY_LOSS_LIMIT_REACHED = "DAILY_LOSS_LIMIT_REACHED"
    INSUFFICIENT_REMAINING_RISK_BUDGET = "INSUFFICIENT_REMAINING_RISK_BUDGET"


__all__ = [
    "RiskBlockReason",
    "RiskFamilyVerdict",
    "RiskGateOutcome",
]

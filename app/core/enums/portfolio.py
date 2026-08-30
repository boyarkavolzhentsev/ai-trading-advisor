"""Stage 8 portfolio-gate enums - deterministic account-portfolio-policy
vocabulary only.

No member here means BUY/SELL/LONG/SHORT/ENTER/EXIT/HOLD, a qualitative
market judgment, or final trade authorization. Every value describes either
a per-family portfolio verdict, the coarse participation-derived outcome
across every family Risk produced a result for, or an exact structural
reason one family was blocked - never a semantic interpretation of Judge/
Policy/Risk's own direction/evidence content, which stays entirely out of
Stage 8's reach.

``ELIGIBLE_FOR_SESSION_REVIEW`` deliberately names the *next* architectural
boundary (Stage 9 Session/Statistics Management, then Stage 10 MT5/broker
integration), not final approval: Stage 8 is not the last stage before
execution.
"""

from __future__ import annotations

from enum import StrEnum


class PortfolioFamilyVerdict(StrEnum):
    """Per-family Stage 8 verdict.

    Never a trade approval: ``ELIGIBLE_FOR_SESSION_REVIEW`` means only that
    this family's risk-to-stop allocation fits within the account's
    portfolio-risk budget and may proceed to Stage 9 session review, never
    that a trade, position, or execution of any kind has been approved.
    """

    ELIGIBLE_FOR_SESSION_REVIEW = "ELIGIBLE_FOR_SESSION_REVIEW"
    BLOCKED_BY_PORTFOLIO = "BLOCKED_BY_PORTFOLIO"


class PortfolioGateOutcome(StrEnum):
    """Coarse, participation-derived verdict across every family Risk
    produced a result for.

    Fully derived from per-family ``PortfolioFamilyVerdict`` values - never a
    selected family, a preferred family, an aggregate direction, or a
    ranking/vote of any kind.
    """

    SOME_ELIGIBLE_FOR_SESSION_REVIEW = "SOME_ELIGIBLE_FOR_SESSION_REVIEW"
    NO_PORTFOLIO_ELIGIBLE_FAMILY = "NO_PORTFOLIO_ELIGIBLE_FAMILY"


class PortfolioBlockReason(StrEnum):
    """Exact structural reason one family was blocked.

    Each member maps to exactly one independently-checked structural fact -
    never a free-text explanation.
    """

    RISK_NOT_ELIGIBLE = "RISK_NOT_ELIGIBLE"
    GLOBAL_PORTFOLIO_CAP_REACHED = "GLOBAL_PORTFOLIO_CAP_REACHED"


__all__ = [
    "PortfolioBlockReason",
    "PortfolioFamilyVerdict",
    "PortfolioGateOutcome",
]

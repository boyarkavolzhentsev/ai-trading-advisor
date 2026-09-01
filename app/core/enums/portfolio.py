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

Stage 8 jointly enforces two independent shared capacities against the sum
of every simultaneously Risk-eligible family's ``max_individual_risk``: the
Stage 7 daily-loss-derived ``available_new_trade_risk`` (re-derived locally,
never imported - see ``app.diversification.supervisor``) and Stage 8's own
``portfolio_risk_limit_percent``-derived capacity. ``RISK_NOT_ELIGIBLE``,
``DAILY_RISK_CAPACITY_EXHAUSTED`` and ``GLOBAL_PORTFOLIO_CAP_REACHED`` are
structurally mutually exclusive: the first applies only to a family Risk
already blocked; of the remaining two, whichever shared capacity is
non-positive names the reason, with ``DAILY_RISK_CAPACITY_EXHAUSTED`` taking
precedence whenever both are simultaneously non-positive - the tighter,
upstream daily-risk safety boundary already prevents any new allocation
regardless of the portfolio capacity's own state, mirroring Stage 9's own
"daily-loss exhaustion is the most conservative fact" precedence.
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
    DAILY_RISK_CAPACITY_EXHAUSTED = "DAILY_RISK_CAPACITY_EXHAUSTED"
    GLOBAL_PORTFOLIO_CAP_REACHED = "GLOBAL_PORTFOLIO_CAP_REACHED"


__all__ = [
    "PortfolioBlockReason",
    "PortfolioFamilyVerdict",
    "PortfolioGateOutcome",
]

"""Stage 6C policy-gate enums - system-policy vocabulary only.

No member here means BUY/SELL/LONG/SHORT/ENTER/EXIT/HOLD, a qualitative
market judgment, a capital-sizing decision, or final trade authorization.
Every value describes either a per-family policy verdict, the coarse
participation-derived outcome across every family Judge produced a result
for, or an exact structural reason one family was blocked - never a semantic
interpretation of Judge's own direction/evidence content, which is Stage 6C's
one hard boundary never to cross.
"""

from __future__ import annotations

from enum import StrEnum


class PolicyFamilyVerdict(StrEnum):
    """Per-family Stage 6C verdict.

    Never a trade approval: ``ELIGIBLE_FOR_RISK_REVIEW`` means only that this
    family's Judge thesis may proceed to Risk/Money-Management review, never
    that a trade, position, or execution of any kind has been approved.
    """

    ELIGIBLE_FOR_RISK_REVIEW = "ELIGIBLE_FOR_RISK_REVIEW"
    BLOCKED = "BLOCKED"


class PolicyGateOutcome(StrEnum):
    """Coarse, participation-derived verdict across every family Judge
    produced a result for.

    Fully derived from per-family ``PolicyFamilyVerdict`` values - never a
    ranking, a preferred family, a winner, or a cross-family semantic
    reconciliation of any kind.
    """

    SOME_ELIGIBLE_FOR_RISK_REVIEW = "SOME_ELIGIBLE_FOR_RISK_REVIEW"
    NO_ELIGIBLE_FAMILY = "NO_ELIGIBLE_FAMILY"


class PolicyBlockReason(StrEnum):
    """Exact structural reason one family was blocked.

    Each member maps to exactly one independently-checked structural fact -
    never a free-text explanation.
    """

    JUDGE_OUTCOME_MIXED = "JUDGE_OUTCOME_MIXED"
    JUDGE_OUTCOME_INSUFFICIENT_EVIDENCE = "JUDGE_OUTCOME_INSUFFICIENT_EVIDENCE"
    DISALLOWED_EVIDENCE_QUALITY = "DISALLOWED_EVIDENCE_QUALITY"


__all__ = [
    "PolicyBlockReason",
    "PolicyFamilyVerdict",
    "PolicyGateOutcome",
]

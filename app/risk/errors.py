"""Stage 7 input-validation errors.

Every error here signals a programming/orchestration mistake in how
``candidate_inputs`` was assembled against an already-produced
``StrategyPolicyResult`` and handed to ``RiskGate.evaluate`` - never a
legitimate account-risk condition. Stage 7 must fail loudly on these rather
than disguise them as an account-risk block (that legitimate case is
``app.core.enums.risk_gate.RiskFamilyVerdict.BLOCKED_BY_RISK``, which arises
only from a Policy-blocked family or a genuine account-risk-budget shortfall
- never from malformed/mismatched candidate input). Mirrors
``app.market_evaluation.errors`` one Decision-layer stage further.
"""

from __future__ import annotations


class RiskInputError(ValueError):
    """Base class for all Stage 7 input-contract violations."""


class UnknownCandidateFamilyError(RiskInputError):
    """Raised when a ``CandidateRiskInput`` references a family that does
    not appear at all in the supplied ``StrategyPolicyResult``."""


class CandidateForBlockedFamilyError(RiskInputError):
    """Raised when a ``CandidateRiskInput`` references a family whose Policy
    verdict is ``BLOCKED`` - sizing facts for a thesis Policy already
    rejected are never legitimate input, not silently ignored."""


class DuplicateCandidateFamilyError(RiskInputError):
    """Raised when ``candidate_inputs`` carries more than one entry for the
    same ``StrategyFamily``."""


class MissingCandidateForEligibleFamilyError(RiskInputError):
    """Raised when a Policy-``ELIGIBLE_FOR_RISK_REVIEW`` family has no
    matching ``CandidateRiskInput`` - every eligible family must receive an
    explicit sizing fact from the caller, never silently skipped."""


__all__ = [
    "CandidateForBlockedFamilyError",
    "DuplicateCandidateFamilyError",
    "MissingCandidateForEligibleFamilyError",
    "RiskInputError",
    "UnknownCandidateFamilyError",
]

"""Stage 6A deterministic strategy-router output contract.

Aggregates one already-produced ``MarketEvaluationResult`` into a per-
``StrategyFamily`` structural eligibility verdict: whether each family has
enough structurally-present, non-``UNAVAILABLE`` evidence for Stage 6B Judge
to be allowed to interpret it. Deliberately narrower than
``MarketEvaluationResult``: this model never reads dimension/value content,
never re-grades or re-derives contour participation/quality, and can
structurally never carry a ranking, a score, a weight, a confidence, a
preferred strategy, or a winner.

The embedded ``MarketEvaluationResult`` is carried unchanged: no evidence,
observation, or provenance is ever copied out of it - the only new fact this
model contributes is the per-family eligibility verdict itself. Carries no
router-owned timestamp: the authoritative time is
``market_evaluation.evaluation_time``, since this stage performs no new
temporal observation of its own.
"""

from __future__ import annotations

from typing import Self

from pydantic import model_validator

from app.core.enums.strategy_router import StrategyFamily, StrategyIneligibilityReason, StrategyRouterOutcome
from app.core.models.base import DomainModel
from app.core.models.market_evaluation_result import MarketEvaluationResult

_REASON_ORDER: tuple[StrategyIneligibilityReason, ...] = tuple(StrategyIneligibilityReason)
_FAMILY_ORDER: tuple[StrategyFamily, ...] = tuple(StrategyFamily)


class StrategyEligibilityEntry(DomainModel):
    """One family's structural eligibility verdict.

    ``ineligibility_reasons`` is empty if and only if ``eligible`` is
    ``True``; when non-empty it is canonically ordered (``StrategyIneligibilityReason``
    declaration order) and duplicate-free. Carries no dimension/value
    content, no evidence, no score, no confidence.
    """

    family: StrategyFamily
    eligible: bool
    ineligibility_reasons: tuple[StrategyIneligibilityReason, ...] = ()

    @model_validator(mode="after")
    def _validate_eligible_matches_reasons(self) -> Self:
        if self.eligible != (len(self.ineligibility_reasons) == 0):
            raise ValueError("eligible must equal (ineligibility_reasons is empty)")
        return self

    @model_validator(mode="after")
    def _validate_reasons_canonical_and_unique(self) -> Self:
        indexes = [_REASON_ORDER.index(reason) for reason in self.ineligibility_reasons]
        if indexes != sorted(indexes):
            raise ValueError("ineligibility_reasons must be in canonical StrategyIneligibilityReason order")
        if len(set(indexes)) != len(indexes):
            raise ValueError("ineligibility_reasons must not contain duplicates")
        return self


class StrategyRouterResult(DomainModel):
    """Deterministic Stage 6A aggregation: one structural eligibility entry
    per ``StrategyFamily``, plus the participation-derived routing outcome."""

    market_evaluation: MarketEvaluationResult
    outcome: StrategyRouterOutcome
    eligibility: tuple[StrategyEligibilityEntry, ...]
    eligible_families: tuple[StrategyFamily, ...]

    @model_validator(mode="after")
    def _validate_eligibility_covers_every_family_in_order(self) -> Self:
        families = tuple(entry.family for entry in self.eligibility)
        if families != _FAMILY_ORDER:
            raise ValueError("eligibility must contain exactly one entry per StrategyFamily, in canonical order")
        return self

    @model_validator(mode="after")
    def _validate_eligible_families(self) -> Self:
        expected = tuple(entry.family for entry in self.eligibility if entry.eligible)
        if self.eligible_families != expected:
            raise ValueError("eligible_families must equal the eligible entries, in canonical order")
        return self

    @model_validator(mode="after")
    def _validate_outcome(self) -> Self:
        expected = StrategyRouterOutcome.ROUTED if self.eligible_families else StrategyRouterOutcome.NO_ELIGIBLE_STRATEGY
        if self.outcome is not expected:
            raise ValueError(f"outcome {self.outcome} does not match eligible_families-derived outcome {expected}")
        return self


__all__ = ["StrategyEligibilityEntry", "StrategyRouterResult"]

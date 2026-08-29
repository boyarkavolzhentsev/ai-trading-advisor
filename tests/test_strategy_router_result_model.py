"""Stage 6A result-model self-validation: ``StrategyEligibilityEntry`` and
``StrategyRouterResult`` invariants, frozen/extra-forbid behavior."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.enums.strategy_router import StrategyFamily, StrategyIneligibilityReason, StrategyRouterOutcome
from app.core.models.strategy_router_result import StrategyEligibilityEntry, StrategyRouterResult
from tests.market_evaluation_support import full_technical_result, make_context
from tests.strategy_router_support import evaluation

_ALL_FAMILIES = tuple(StrategyFamily)


def _ineligible_entry(family: StrategyFamily) -> StrategyEligibilityEntry:
    return StrategyEligibilityEntry(
        family=family, eligible=False, ineligibility_reasons=(StrategyIneligibilityReason.CONTOUR_MISSING,)
    )


def _eligible_entry(family: StrategyFamily) -> StrategyEligibilityEntry:
    return StrategyEligibilityEntry(family=family, eligible=True)


def _full_eligibility(eligible_family: StrategyFamily | None = None) -> tuple[StrategyEligibilityEntry, ...]:
    return tuple(
        _eligible_entry(family) if family is eligible_family else _ineligible_entry(family)
        for family in _ALL_FAMILIES
    )


# --- StrategyEligibilityEntry invariants ---


def test_eligible_true_requires_empty_reasons() -> None:
    with pytest.raises(ValidationError):
        StrategyEligibilityEntry(
            family=StrategyFamily.TREND_FOLLOWING,
            eligible=True,
            ineligibility_reasons=(StrategyIneligibilityReason.CONTOUR_MISSING,),
        )


def test_eligible_false_requires_nonempty_reasons() -> None:
    with pytest.raises(ValidationError):
        StrategyEligibilityEntry(family=StrategyFamily.TREND_FOLLOWING, eligible=False, ineligibility_reasons=())


def test_reasons_must_be_canonically_ordered() -> None:
    with pytest.raises(ValidationError):
        StrategyEligibilityEntry(
            family=StrategyFamily.TREND_FOLLOWING,
            eligible=False,
            ineligibility_reasons=(
                StrategyIneligibilityReason.QUALITY_UNAVAILABLE,
                StrategyIneligibilityReason.CONTOUR_MISSING,
            ),
        )


def test_duplicate_reasons_rejected() -> None:
    with pytest.raises(ValidationError):
        StrategyEligibilityEntry(
            family=StrategyFamily.TREND_FOLLOWING,
            eligible=False,
            ineligibility_reasons=(
                StrategyIneligibilityReason.CONTOUR_MISSING,
                StrategyIneligibilityReason.CONTOUR_MISSING,
            ),
        )


def test_eligibility_entry_frozen() -> None:
    entry = _eligible_entry(StrategyFamily.TREND_FOLLOWING)
    with pytest.raises(ValidationError):
        entry.eligible = False


def test_eligibility_entry_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        StrategyEligibilityEntry(family=StrategyFamily.TREND_FOLLOWING, eligible=True, confidence=0.9)


# --- StrategyRouterResult invariants ---


def test_result_via_router_is_valid() -> None:
    # A round trip through the real router is itself a strong self-validation check.
    from app.strategies.router import StrategyRouter

    result = StrategyRouter().route(market_evaluation=evaluation(technical=full_technical_result()))
    assert isinstance(result, StrategyRouterResult)


def test_eligibility_must_cover_every_family_exactly_once() -> None:
    with pytest.raises(ValidationError):
        StrategyRouterResult(
            market_evaluation=evaluation(),
            outcome=StrategyRouterOutcome.NO_ELIGIBLE_STRATEGY,
            eligibility=_full_eligibility()[:-1],  # omits EVENT_DRIVEN
            eligible_families=(),
        )


def test_duplicate_family_in_eligibility_rejected() -> None:
    eligibility = _full_eligibility()[:-1] + (_ineligible_entry(StrategyFamily.TREND_FOLLOWING),)
    with pytest.raises(ValidationError):
        StrategyRouterResult(
            market_evaluation=evaluation(),
            outcome=StrategyRouterOutcome.NO_ELIGIBLE_STRATEGY,
            eligibility=eligibility,
            eligible_families=(),
        )


def test_eligibility_order_must_be_canonical() -> None:
    eligibility = tuple(reversed(_full_eligibility()))
    with pytest.raises(ValidationError):
        StrategyRouterResult(
            market_evaluation=evaluation(),
            outcome=StrategyRouterOutcome.NO_ELIGIBLE_STRATEGY,
            eligibility=eligibility,
            eligible_families=(),
        )


def test_eligible_families_must_match_eligible_entries() -> None:
    eligibility = _full_eligibility(eligible_family=StrategyFamily.TREND_FOLLOWING)
    with pytest.raises(ValidationError):
        StrategyRouterResult(
            market_evaluation=evaluation(),
            outcome=StrategyRouterOutcome.ROUTED,
            eligibility=eligibility,
            eligible_families=(),  # should be (TREND_FOLLOWING,)
        )


def test_outcome_must_match_eligible_families() -> None:
    eligibility = _full_eligibility(eligible_family=StrategyFamily.TREND_FOLLOWING)
    with pytest.raises(ValidationError):
        StrategyRouterResult(
            market_evaluation=evaluation(),
            outcome=StrategyRouterOutcome.NO_ELIGIBLE_STRATEGY,  # should be ROUTED
            eligibility=eligibility,
            eligible_families=(StrategyFamily.TREND_FOLLOWING,),
        )


def test_result_frozen() -> None:
    from app.strategies.router import StrategyRouter

    result = StrategyRouter().route(market_evaluation=evaluation())
    with pytest.raises(ValidationError):
        result.outcome = StrategyRouterOutcome.ROUTED


def test_result_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        StrategyRouterResult(
            market_evaluation=evaluation(),
            outcome=StrategyRouterOutcome.NO_ELIGIBLE_STRATEGY,
            eligibility=_full_eligibility(),
            eligible_families=(),
            score=1.0,
        )

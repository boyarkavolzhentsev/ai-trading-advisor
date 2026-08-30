"""Stage 8 result-model self-validation: ``PortfolioFamilyResult`` and
``StrategyPortfolioResult`` invariants, frozen/extra-forbid behavior.
Malformed externally-constructed objects must be rejected - not only objects
``PortfolioSupervisor`` itself would build."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums.portfolio import PortfolioBlockReason, PortfolioFamilyVerdict, PortfolioGateOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.portfolio_result import PortfolioFamilyResult, StrategyPortfolioResult
from tests.market_evaluation_support import full_technical_result
from tests.risk_gate_support import route_judge_gate_and_risk

# --- PortfolioFamilyResult: verdict/reasons coupling ---


def test_eligible_forbids_reasons() -> None:
    with pytest.raises(ValidationError):
        PortfolioFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW,
            reasons=(PortfolioBlockReason.GLOBAL_PORTFOLIO_CAP_REACHED,),
            portfolio_allocated_risk=Decimal("100"),
        )


def test_blocked_requires_at_least_one_reason() -> None:
    with pytest.raises(ValidationError):
        PortfolioFamilyResult(family=StrategyFamily.TREND_FOLLOWING, verdict=PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO, reasons=())


def test_eligible_requires_positive_allocation() -> None:
    with pytest.raises(ValidationError):
        PortfolioFamilyResult(family=StrategyFamily.TREND_FOLLOWING, verdict=PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW)


def test_eligible_rejects_zero_allocation() -> None:
    with pytest.raises(ValidationError):
        PortfolioFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW,
            portfolio_allocated_risk=Decimal("0"),
        )


def test_blocked_forbids_allocation_field() -> None:
    with pytest.raises(ValidationError):
        PortfolioFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO,
            reasons=(PortfolioBlockReason.GLOBAL_PORTFOLIO_CAP_REACHED,),
            portfolio_allocated_risk=Decimal("100"),
        )


def test_eligible_with_valid_allocation_accepted() -> None:
    result = PortfolioFamilyResult(
        family=StrategyFamily.TREND_FOLLOWING, verdict=PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW, portfolio_allocated_risk=Decimal("500")
    )
    assert result.portfolio_allocated_risk == Decimal("500")


def test_multiple_reasons_rejected() -> None:
    with pytest.raises(ValidationError):
        PortfolioFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO,
            reasons=(PortfolioBlockReason.RISK_NOT_ELIGIBLE, PortfolioBlockReason.GLOBAL_PORTFOLIO_CAP_REACHED),
        )


# --- frozen / extra-forbid ---


def test_family_result_frozen() -> None:
    result = PortfolioFamilyResult(
        family=StrategyFamily.TREND_FOLLOWING, verdict=PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO, reasons=(PortfolioBlockReason.RISK_NOT_ELIGIBLE,)
    )
    with pytest.raises(ValidationError):
        result.verdict = PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW


def test_family_result_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        PortfolioFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO,
            reasons=(PortfolioBlockReason.RISK_NOT_ELIGIBLE,),
            confidence=0.9,
        )


# --- StrategyPortfolioResult: family coverage / outcome ---


def _base_risk_result():
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result())
    return risk_result


def test_family_results_must_match_risk_family_results() -> None:
    risk_result = _base_risk_result()
    with pytest.raises(ValidationError):
        StrategyPortfolioResult(strategy_risk_result=risk_result, outcome=PortfolioGateOutcome.NO_PORTFOLIO_ELIGIBLE_FAMILY, family_results=())


def test_inconsistent_top_level_outcome_rejected() -> None:
    from app.diversification.supervisor import PortfolioSupervisor

    risk_result = _base_risk_result()
    correct = PortfolioSupervisor().evaluate(strategy_risk_result=risk_result)
    wrong_outcome = (
        PortfolioGateOutcome.NO_PORTFOLIO_ELIGIBLE_FAMILY
        if correct.outcome is PortfolioGateOutcome.SOME_ELIGIBLE_FOR_SESSION_REVIEW
        else PortfolioGateOutcome.SOME_ELIGIBLE_FOR_SESSION_REVIEW
    )
    with pytest.raises(ValidationError):
        StrategyPortfolioResult(strategy_risk_result=correct.strategy_risk_result, outcome=wrong_outcome, family_results=correct.family_results)


def test_correct_result_accepted() -> None:
    from app.diversification.supervisor import PortfolioSupervisor

    risk_result = _base_risk_result()
    correct = PortfolioSupervisor().evaluate(strategy_risk_result=risk_result)
    rebuilt = StrategyPortfolioResult(
        strategy_risk_result=correct.strategy_risk_result, outcome=correct.outcome, family_results=correct.family_results
    )
    assert rebuilt == correct


def test_frozen() -> None:
    from app.diversification.supervisor import PortfolioSupervisor

    risk_result = _base_risk_result()
    result = PortfolioSupervisor().evaluate(strategy_risk_result=risk_result)
    with pytest.raises(ValidationError):
        result.outcome = PortfolioGateOutcome.NO_PORTFOLIO_ELIGIBLE_FAMILY


def test_extra_fields_forbidden() -> None:
    risk_result = _base_risk_result()
    with pytest.raises(ValidationError):
        StrategyPortfolioResult(
            strategy_risk_result=risk_result,
            outcome=PortfolioGateOutcome.NO_PORTFOLIO_ELIGIBLE_FAMILY,
            family_results=(),
            confidence=0.9,
        )

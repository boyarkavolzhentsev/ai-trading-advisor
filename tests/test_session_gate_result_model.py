"""Stage 9 result-model self-validation: ``SessionFamilyResult`` and
``StrategySessionResult`` invariants, frozen/extra-forbid behavior, family
coverage/order, and unreachability of CAPITAL_PRESERVATION/REDUCED_RISK.
Malformed externally-constructed objects must be rejected - not only objects
``SessionGate`` itself would build."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums.session import TradingSessionStatus
from app.core.enums.session_gate import SessionBlockReason, SessionFamilyVerdict, SessionGateOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.session_result import SessionFamilyResult, StrategySessionResult
from app.statistics.session import SessionGate
from tests.session_support import route_to_portfolio_and_session

# --- SessionFamilyResult: verdict/reasons coupling ---


def test_eligible_forbids_reasons() -> None:
    with pytest.raises(ValidationError):
        SessionFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=SessionFamilyVerdict.ELIGIBLE_FOR_RUNTIME_REVIEW,
            reasons=(SessionBlockReason.TARGET_REACHED,),
            session_allocated_risk=Decimal("100"),
        )


def test_blocked_requires_at_least_one_reason() -> None:
    with pytest.raises(ValidationError):
        SessionFamilyResult(family=StrategyFamily.TREND_FOLLOWING, verdict=SessionFamilyVerdict.BLOCKED_BY_SESSION, reasons=())


def test_eligible_requires_positive_allocation() -> None:
    with pytest.raises(ValidationError):
        SessionFamilyResult(family=StrategyFamily.TREND_FOLLOWING, verdict=SessionFamilyVerdict.ELIGIBLE_FOR_RUNTIME_REVIEW)


def test_eligible_rejects_zero_allocation() -> None:
    with pytest.raises(ValidationError):
        SessionFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=SessionFamilyVerdict.ELIGIBLE_FOR_RUNTIME_REVIEW,
            session_allocated_risk=Decimal("0"),
        )


def test_blocked_forbids_allocation_field() -> None:
    with pytest.raises(ValidationError):
        SessionFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=SessionFamilyVerdict.BLOCKED_BY_SESSION,
            reasons=(SessionBlockReason.TARGET_REACHED,),
            session_allocated_risk=Decimal("100"),
        )


def test_multiple_reasons_rejected() -> None:
    with pytest.raises(ValidationError):
        SessionFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=SessionFamilyVerdict.BLOCKED_BY_SESSION,
            reasons=(SessionBlockReason.SESSION_LOCKED, SessionBlockReason.TARGET_REACHED),
        )


def test_family_result_frozen() -> None:
    result = SessionFamilyResult(
        family=StrategyFamily.TREND_FOLLOWING, verdict=SessionFamilyVerdict.BLOCKED_BY_SESSION, reasons=(SessionBlockReason.SESSION_LOCKED,)
    )
    with pytest.raises(ValidationError):
        result.verdict = SessionFamilyVerdict.ELIGIBLE_FOR_RUNTIME_REVIEW


def test_family_result_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        SessionFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=SessionFamilyVerdict.BLOCKED_BY_SESSION,
            reasons=(SessionBlockReason.SESSION_LOCKED,),
            confidence=0.9,
        )


# --- StrategySessionResult: family coverage / outcome / status re-derivation ---


def _base_portfolio_result():
    portfolio_result, _ = route_to_portfolio_and_session()
    return portfolio_result


def test_family_results_must_match_portfolio_family_results() -> None:
    portfolio_result = _base_portfolio_result()
    with pytest.raises(ValidationError):
        StrategySessionResult(
            strategy_portfolio_result=portfolio_result,
            session_status=TradingSessionStatus.ACTIVE,
            outcome=SessionGateOutcome.NO_SESSION_ELIGIBLE_FAMILY,
            family_results=(),
        )


def test_inconsistent_top_level_outcome_rejected() -> None:
    portfolio_result = _base_portfolio_result()
    correct = SessionGate().evaluate(strategy_portfolio_result=portfolio_result)
    wrong_outcome = (
        SessionGateOutcome.NO_SESSION_ELIGIBLE_FAMILY
        if correct.outcome is SessionGateOutcome.SOME_ELIGIBLE_FOR_RUNTIME_REVIEW
        else SessionGateOutcome.SOME_ELIGIBLE_FOR_RUNTIME_REVIEW
    )
    with pytest.raises(ValidationError):
        StrategySessionResult(
            strategy_portfolio_result=correct.strategy_portfolio_result,
            locked_override=correct.locked_override,
            session_status=correct.session_status,
            outcome=wrong_outcome,
            family_results=correct.family_results,
        )


def test_session_status_must_match_expected_derivation() -> None:
    portfolio_result = _base_portfolio_result()
    correct = SessionGate().evaluate(strategy_portfolio_result=portfolio_result)
    assert correct.session_status is TradingSessionStatus.ACTIVE
    with pytest.raises(ValidationError):
        StrategySessionResult(
            strategy_portfolio_result=correct.strategy_portfolio_result,
            locked_override=False,
            session_status=TradingSessionStatus.TARGET_REACHED,
            outcome=correct.outcome,
            family_results=correct.family_results,
        )


def test_locked_override_mismatch_rejected() -> None:
    """session_status must be re-derivable from locked_override - a result
    claiming ACTIVE while locked_override is True is rejected."""
    portfolio_result = _base_portfolio_result()
    correct = SessionGate().evaluate(strategy_portfolio_result=portfolio_result)
    with pytest.raises(ValidationError):
        StrategySessionResult(
            strategy_portfolio_result=correct.strategy_portfolio_result,
            locked_override=True,
            session_status=TradingSessionStatus.ACTIVE,
            outcome=correct.outcome,
            family_results=correct.family_results,
        )


@pytest.mark.parametrize("status", [TradingSessionStatus.CAPITAL_PRESERVATION, TradingSessionStatus.REDUCED_RISK])
def test_capital_preservation_and_reduced_risk_rejected_as_declared_status(status: TradingSessionStatus) -> None:
    portfolio_result = _base_portfolio_result()
    correct = SessionGate().evaluate(strategy_portfolio_result=portfolio_result)
    with pytest.raises(ValidationError):
        StrategySessionResult(
            strategy_portfolio_result=correct.strategy_portfolio_result,
            locked_override=correct.locked_override,
            session_status=status,
            outcome=correct.outcome,
            family_results=correct.family_results,
        )


def test_correct_result_accepted() -> None:
    portfolio_result = _base_portfolio_result()
    correct = SessionGate().evaluate(strategy_portfolio_result=portfolio_result)
    rebuilt = StrategySessionResult(
        strategy_portfolio_result=correct.strategy_portfolio_result,
        locked_override=correct.locked_override,
        session_status=correct.session_status,
        outcome=correct.outcome,
        family_results=correct.family_results,
    )
    assert rebuilt == correct


def test_frozen() -> None:
    portfolio_result = _base_portfolio_result()
    result = SessionGate().evaluate(strategy_portfolio_result=portfolio_result)
    with pytest.raises(ValidationError):
        result.outcome = SessionGateOutcome.NO_SESSION_ELIGIBLE_FAMILY


def test_extra_fields_forbidden() -> None:
    portfolio_result = _base_portfolio_result()
    with pytest.raises(ValidationError):
        StrategySessionResult(
            strategy_portfolio_result=portfolio_result,
            session_status=TradingSessionStatus.ACTIVE,
            outcome=SessionGateOutcome.NO_SESSION_ELIGIBLE_FAMILY,
            family_results=(),
            confidence=0.9,
        )


def test_family_order_matches_portfolio_result_order() -> None:
    portfolio_result = _base_portfolio_result()
    result = SessionGate().evaluate(strategy_portfolio_result=portfolio_result)
    assert tuple(r.family for r in result.family_results) == tuple(r.family for r in portfolio_result.family_results)


def test_outcome_matches_participation() -> None:
    _, locked_result = route_to_portfolio_and_session(locked_override=True)
    assert locked_result.outcome is SessionGateOutcome.NO_SESSION_ELIGIBLE_FAMILY

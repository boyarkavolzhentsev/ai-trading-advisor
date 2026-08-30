"""Stage 7 open-risk-to-stop semantics: non-negative, floored
``available_new_trade_risk``, and no floating-PnL/open-risk double counting."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums.strategy_router import StrategyFamily
from app.core.models.risk_gate_result import AccountRiskSnapshot
from tests.market_evaluation_support import full_technical_result
from tests.risk_gate_support import NOW, default_account_snapshot, route_judge_gate_and_risk


def _trend(risk_result):
    return next(r for r in risk_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)


def test_zero_open_risk_to_stop() -> None:
    snapshot = default_account_snapshot(current_open_risk_to_stop=Decimal("0"))
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), account_snapshot=snapshot)
    assert _trend(risk_result).verdict.value == "ELIGIBLE_FOR_PORTFOLIO_REVIEW"


def test_positive_open_risk_consumes_capacity() -> None:
    """remaining_daily_loss_capacity=1500, open_risk=1100 -> available=400,
    below the 500 per-trade budget -> per-trade no longer binds, available does."""
    snapshot = default_account_snapshot(current_open_risk_to_stop=Decimal("1100"))
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), account_snapshot=snapshot)
    assert _trend(risk_result).max_individual_risk == Decimal("400")


def test_negative_open_risk_to_stop_rejected_at_construction() -> None:
    with pytest.raises(ValidationError):
        AccountRiskSnapshot(
            as_of=NOW,
            rollover_equity=Decimal("100000"),
            current_equity=Decimal("100000"),
            realized_daily_pnl=Decimal("0"),
            floating_pnl=Decimal("0"),
            current_open_risk_to_stop=Decimal("-1"),
        )


def test_no_double_counting_of_floating_pnl_and_open_risk() -> None:
    """A -300 floating loss plus a 200 open-risk-to-stop must combine as two
    disjoint deductions (900+200=... ) not double-subtracted: remaining
    daily capacity after the floating loss is 1500-300=1200, then minus
    open-risk 200 gives available=1000 - never treating the 300 as if it
    were part of the same 200 figure or vice versa."""
    snapshot = default_account_snapshot(floating_pnl=Decimal("-300"), current_open_risk_to_stop=Decimal("200"))
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), account_snapshot=snapshot)
    # remaining = max(0, 1500-300) = 1200; available = max(0, 1200-200) = 1000; per-trade 500 binds.
    assert _trend(risk_result).max_individual_risk == Decimal("500.000")


def test_available_new_trade_risk_floored_at_zero() -> None:
    """Open risk-to-stop alone (2000) exceeds daily capacity (1500) even
    with zero PnL - available floors at 0, never negative, and blocks with
    INSUFFICIENT_REMAINING_RISK_BUDGET rather than DAILY_LOSS_LIMIT_REACHED
    (the raw daily PnL never actually reached the limit)."""
    snapshot = default_account_snapshot(current_open_risk_to_stop=Decimal("2000"))
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), account_snapshot=snapshot)
    trend = _trend(risk_result)
    assert trend.verdict.value == "BLOCKED_BY_RISK"
    assert trend.reasons[0].value == "INSUFFICIENT_REMAINING_RISK_BUDGET"
    assert trend.max_individual_risk is None

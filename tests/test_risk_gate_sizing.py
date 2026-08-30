"""Stage 7 position-sizing formula: per-trade-budget-binding,
account-remaining-budget-binding, the equal-boundary case, exact Decimal
arithmetic, and the absence of any broker-style rounding."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.strategy_router import StrategyFamily
from tests.market_evaluation_support import full_technical_result
from tests.risk_gate_support import default_account_snapshot, route_judge_gate_and_risk


def _trend(risk_result):
    return next(r for r in risk_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)


def test_per_trade_budget_binds() -> None:
    """available_new_trade_risk (1500) exceeds per_trade_risk_budget (500)."""
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result())
    trend = _trend(risk_result)
    assert trend.max_individual_risk == Decimal("500.000")


def test_account_remaining_budget_binds() -> None:
    """available_new_trade_risk (200, via open-risk consumption) is below
    per_trade_risk_budget (500)."""
    snapshot = default_account_snapshot(current_open_risk_to_stop=Decimal("1300"))
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), account_snapshot=snapshot)
    trend = _trend(risk_result)
    assert trend.max_individual_risk == Decimal("200")


def test_equal_boundary_min_case() -> None:
    """available_new_trade_risk exactly equals per_trade_risk_budget (500);
    min() of two equal Decimals is well-defined and eligible."""
    snapshot = default_account_snapshot(current_open_risk_to_stop=Decimal("1000"))
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), account_snapshot=snapshot)
    trend = _trend(risk_result)
    assert trend.verdict.value == "ELIGIBLE_FOR_PORTFOLIO_REVIEW"
    assert trend.max_individual_risk == Decimal("500")


def test_exact_recommended_units_decimal_arithmetic() -> None:
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), risk_per_unit=Decimal("7"))
    trend = _trend(risk_result)
    # max_individual_risk = 500.000, risk_per_unit = 7 -> 500/7 exact Decimal division.
    assert trend.recommended_units == Decimal("500.000") / Decimal("7")


def test_no_broker_rounding_fractional_units_preserved() -> None:
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), risk_per_unit=Decimal("3"))
    trend = _trend(risk_result)
    # 500/3 is a genuinely fractional, non-round number - never rounded to a whole lot.
    assert trend.recommended_units != trend.recommended_units.to_integral_value()

"""Stage 7 ``risk_per_unit`` handling: normal path, zero, and negative."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.strategy_router import StrategyFamily
from tests.market_evaluation_support import full_technical_result
from tests.risk_gate_support import route_judge_gate_and_risk


def _trend(risk_result):
    return next(r for r in risk_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)


def test_positive_risk_per_unit_normal_path() -> None:
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), risk_per_unit=Decimal("10"))
    trend = _trend(risk_result)
    assert trend.verdict.value == "ELIGIBLE_FOR_PORTFOLIO_REVIEW"
    assert trend.recommended_units == Decimal("50")


def test_zero_risk_per_unit_blocked() -> None:
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), risk_per_unit=Decimal("0"))
    trend = _trend(risk_result)
    assert trend.verdict.value == "BLOCKED_BY_RISK"
    assert trend.reasons[0].value == "ZERO_OR_NEGATIVE_RISK_PER_UNIT"
    assert trend.max_individual_risk is None
    assert trend.recommended_units is None


def test_negative_risk_per_unit_blocked() -> None:
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), risk_per_unit=Decimal("-5"))
    trend = _trend(risk_result)
    assert trend.verdict.value == "BLOCKED_BY_RISK"
    assert trend.reasons[0].value == "ZERO_OR_NEGATIVE_RISK_PER_UNIT"
    assert trend.max_individual_risk is None
    assert trend.recommended_units is None

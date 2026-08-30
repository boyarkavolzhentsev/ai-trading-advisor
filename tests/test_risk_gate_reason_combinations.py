"""Stage 7 reason-combination behavior: ``ZERO_OR_NEGATIVE_RISK_PER_UNIT``
may coexist with either account-state reason; ``DAILY_LOSS_LIMIT_REACHED``
and ``INSUFFICIENT_REMAINING_RISK_BUDGET`` remain mutually exclusive, and the
independent risk_per_unit check is never short-circuited by an
account-state block."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.strategy_router import StrategyFamily
from tests.market_evaluation_support import full_technical_result
from tests.risk_gate_support import default_account_snapshot, route_judge_gate_and_risk


def _trend(risk_result):
    return next(r for r in risk_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)


def test_zero_risk_per_unit_plus_daily_limit_reached() -> None:
    snapshot = default_account_snapshot(realized_daily_pnl=Decimal("-1500"))
    _, risk_result = route_judge_gate_and_risk(
        technical=full_technical_result(), account_snapshot=snapshot, risk_per_unit=Decimal("0")
    )
    trend = _trend(risk_result)
    reason_values = {r.value for r in trend.reasons}
    assert reason_values == {"ZERO_OR_NEGATIVE_RISK_PER_UNIT", "DAILY_LOSS_LIMIT_REACHED"}
    assert [r.value for r in trend.reasons] == ["ZERO_OR_NEGATIVE_RISK_PER_UNIT", "DAILY_LOSS_LIMIT_REACHED"]


def test_zero_risk_per_unit_plus_insufficient_remaining_budget() -> None:
    snapshot = default_account_snapshot(current_open_risk_to_stop=Decimal("2000"))
    _, risk_result = route_judge_gate_and_risk(
        technical=full_technical_result(), account_snapshot=snapshot, risk_per_unit=Decimal("-1")
    )
    trend = _trend(risk_result)
    reason_values = {r.value for r in trend.reasons}
    assert reason_values == {"ZERO_OR_NEGATIVE_RISK_PER_UNIT", "INSUFFICIENT_REMAINING_RISK_BUDGET"}
    assert [r.value for r in trend.reasons] == ["ZERO_OR_NEGATIVE_RISK_PER_UNIT", "INSUFFICIENT_REMAINING_RISK_BUDGET"]


def test_daily_and_insufficient_never_co_occur() -> None:
    """When the daily limit itself is reached, INSUFFICIENT_REMAINING_RISK_BUDGET
    is never additionally reported (precedence, not independent evaluation)."""
    snapshot = default_account_snapshot(realized_daily_pnl=Decimal("-1500"), current_open_risk_to_stop=Decimal("100"))
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), account_snapshot=snapshot)
    trend = _trend(risk_result)
    assert [r.value for r in trend.reasons] == ["DAILY_LOSS_LIMIT_REACHED"]

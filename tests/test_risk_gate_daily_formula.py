"""Stage 7 daily-risk arithmetic: exact Decimal daily/per-trade budgets,
sign conventions, and the not-reached/exactly-reached/exceeded cases."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.strategy_router import StrategyFamily
from tests.market_evaluation_support import full_technical_result
from tests.risk_gate_support import default_account_snapshot, default_config, route_judge_gate_and_risk


def _trend(risk_result):
    return next(r for r in risk_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)


def test_exact_daily_budget_decimal() -> None:
    snapshot = default_account_snapshot(rollover_equity=Decimal("100000"))
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), account_snapshot=snapshot)
    # daily_loss_limit = 100000 * 1.5/100 = 1500; no PnL/open-risk -> available = 1500
    # per_trade_risk_budget = 100000 * 0.5/100 = 500 -> binds (500 < 1500)
    assert _trend(risk_result).max_individual_risk == Decimal("500.000")


def test_exact_per_trade_budget_decimal() -> None:
    snapshot = default_account_snapshot(rollover_equity=Decimal("200000"))
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), account_snapshot=snapshot)
    # per_trade_risk_budget = 200000 * 0.5/100 = 1000
    assert _trend(risk_result).max_individual_risk == Decimal("1000.000")


def test_positive_daily_pnl_does_not_increase_daily_limit() -> None:
    snapshot = default_account_snapshot(realized_daily_pnl=Decimal("400"), floating_pnl=Decimal("100"))
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), account_snapshot=snapshot)
    # remaining_daily_loss_capacity stays 1500 regardless of +500 profit; per-trade budget (500) still binds.
    assert _trend(risk_result).max_individual_risk == Decimal("500.000")


def test_negative_realized_pnl_only() -> None:
    snapshot = default_account_snapshot(realized_daily_pnl=Decimal("-600"))
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), account_snapshot=snapshot)
    # remaining = max(0, 1500 - 600) = 900; per-trade budget 500 still binds.
    assert _trend(risk_result).max_individual_risk == Decimal("500.000")


def test_negative_floating_pnl_only() -> None:
    snapshot = default_account_snapshot(floating_pnl=Decimal("-600"))
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), account_snapshot=snapshot)
    assert _trend(risk_result).max_individual_risk == Decimal("500.000")


def test_combined_realized_and_floating_loss() -> None:
    snapshot = default_account_snapshot(realized_daily_pnl=Decimal("-600"), floating_pnl=Decimal("-300"))
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), account_snapshot=snapshot)
    # remaining = max(0, 1500 - 900) = 600; per-trade budget 500 still binds (500 < 600).
    assert _trend(risk_result).max_individual_risk == Decimal("500.000")


def test_realized_loss_offset_by_floating_profit() -> None:
    snapshot = default_account_snapshot(realized_daily_pnl=Decimal("-900"), floating_pnl=Decimal("400"))
    # current_daily_pnl = -500 -> loss_consumed=500 -> remaining = 1000; per-trade 500 still binds.
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), account_snapshot=snapshot)
    assert _trend(risk_result).max_individual_risk == Decimal("500.000")


def test_daily_limit_not_reached() -> None:
    snapshot = default_account_snapshot(realized_daily_pnl=Decimal("-100"))
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), account_snapshot=snapshot)
    assert _trend(risk_result).verdict.value == "ELIGIBLE_FOR_PORTFOLIO_REVIEW"


def test_daily_limit_exactly_reached() -> None:
    """realized -1000, floating -500 -> current_daily_pnl=-1500 -> loss_consumed=1500
    -> remaining = max(0, 1500-1500) = 0 -> DAILY_LOSS_LIMIT_REACHED."""
    snapshot = default_account_snapshot(realized_daily_pnl=Decimal("-1000"), floating_pnl=Decimal("-500"))
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), account_snapshot=snapshot)
    trend = _trend(risk_result)
    assert trend.verdict.value == "BLOCKED_BY_RISK"
    assert trend.reasons[0].value == "DAILY_LOSS_LIMIT_REACHED"


def test_daily_limit_exceeded() -> None:
    snapshot = default_account_snapshot(realized_daily_pnl=Decimal("-1200"), floating_pnl=Decimal("-600"))
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), account_snapshot=snapshot)
    trend = _trend(risk_result)
    assert trend.verdict.value == "BLOCKED_BY_RISK"
    assert trend.reasons[0].value == "DAILY_LOSS_LIMIT_REACHED"
    assert trend.max_individual_risk is None

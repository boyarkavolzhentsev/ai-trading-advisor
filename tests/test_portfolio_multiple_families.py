"""Stage 8: multiple Risk-eligible families - aggregate requested risk below,
exactly at, and above the shared portfolio capacity."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.portfolio import PortfolioFamilyVerdict
from tests.market_evaluation_support import full_flow_result, make_context
from tests.portfolio_support import route_judge_gate_risk_and_portfolio, technical_with_trend_and_confirmed_break
from tests.risk_gate_support import default_account_snapshot
from tests.strategy_judge_support import external_with_news_sentiment

_ROLLOVER_EQUITY = Decimal("1000000")  # ample Stage 7 daily/per-trade headroom regardless of current_equity below
_TECHNICAL = technical_with_trend_and_confirmed_break()


def _three_family_portfolio_result(current_equity: Decimal):
    snapshot = default_account_snapshot(
        rollover_equity=_ROLLOVER_EQUITY, current_equity=current_equity, current_open_risk_to_stop=Decimal("0")
    )
    _, portfolio_result = route_judge_gate_risk_and_portfolio(
        technical=_TECHNICAL,
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
        context=make_context(),
        account_snapshot=snapshot,
        risk_per_unit=Decimal("10"),
    )
    return portfolio_result


def _eligible(portfolio_result):
    return [r for r in portfolio_result.family_results if r.verdict is PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW]


def test_aggregate_below_cap_unscaled() -> None:
    # per_trade_budget = 1,000,000 * 0.5% = 5000 each; 3 eligible x 5000 = 15000 requested.
    # cap = 300,000 * 6% = 18000 >= 15000 -> unscaled.
    portfolio_result = _three_family_portfolio_result(Decimal("300000"))
    eligible = _eligible(portfolio_result)
    assert len(eligible) == 3
    for result in eligible:
        assert result.portfolio_allocated_risk == Decimal("5000.000")


def test_aggregate_exactly_at_cap_unscaled() -> None:
    # cap = 250,000 * 6% = 15000 == total requested (15000) -> boundary, still unscaled.
    portfolio_result = _three_family_portfolio_result(Decimal("250000"))
    eligible = _eligible(portfolio_result)
    assert len(eligible) == 3
    for result in eligible:
        assert result.portfolio_allocated_risk == Decimal("5000.000")


def test_aggregate_above_cap_scaled() -> None:
    # cap = 100,000 * 6% = 6000 < 15000 requested -> scaling_factor = 6000/15000 = 0.4.
    portfolio_result = _three_family_portfolio_result(Decimal("100000"))
    eligible = _eligible(portfolio_result)
    assert len(eligible) == 3
    for result in eligible:
        assert result.portfolio_allocated_risk == Decimal("2000.0")
    total = sum((r.portfolio_allocated_risk for r in eligible), Decimal("0"))
    assert total == Decimal("6000.0")

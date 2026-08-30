"""Stage 8 proportional-scaling exactness: identical scaling factor applied
to every simultaneously Risk-eligible family, for 2-family and 3+-family
cases."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.portfolio import PortfolioFamilyVerdict
from app.core.enums.strategy_router import StrategyFamily
from tests.market_evaluation_support import full_flow_result, full_technical_result, make_context
from tests.portfolio_support import route_judge_gate_risk_and_portfolio, technical_with_trend_and_confirmed_break
from tests.risk_gate_support import default_account_snapshot
from tests.strategy_judge_support import external_with_news_sentiment


def test_two_family_scaling_exact() -> None:
    """TREND_FOLLOWING + BREAKOUT both eligible (via technical_with_trend_and_confirmed_break,
    no external -> EVENT_DRIVEN stays ineligible), scaled by an identical factor."""
    snapshot = default_account_snapshot(
        rollover_equity=Decimal("1000000"), current_equity=Decimal("100000"), current_open_risk_to_stop=Decimal("0")
    )
    _, portfolio_result = route_judge_gate_risk_and_portfolio(
        technical=technical_with_trend_and_confirmed_break(),
        flow=full_flow_result(),
        account_snapshot=snapshot,
        risk_per_unit=Decimal("10"),
    )
    eligible = {r.family: r for r in portfolio_result.family_results if r.verdict is PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW}
    assert set(eligible) == {StrategyFamily.TREND_FOLLOWING, StrategyFamily.BREAKOUT}
    # per_trade_budget = 5000 each; total_requested = 10000; cap = 6000 -> scale = 0.6.
    for result in eligible.values():
        assert result.portfolio_allocated_risk == Decimal("3000.0")


def test_three_family_scaling_exact() -> None:
    snapshot = default_account_snapshot(
        rollover_equity=Decimal("1000000"), current_equity=Decimal("100000"), current_open_risk_to_stop=Decimal("0")
    )
    _, portfolio_result = route_judge_gate_risk_and_portfolio(
        technical=technical_with_trend_and_confirmed_break(),
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
        context=make_context(),
        account_snapshot=snapshot,
        risk_per_unit=Decimal("10"),
    )
    eligible = [r for r in portfolio_result.family_results if r.verdict is PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW]
    assert len(eligible) == 3
    # per_trade_budget = 5000 each; total_requested = 15000; cap = 6000 -> scale = 0.4.
    allocations = {r.portfolio_allocated_risk for r in eligible}
    assert allocations == {Decimal("2000.0")}
    total = sum((r.portfolio_allocated_risk for r in eligible), Decimal("0"))
    assert total == Decimal("6000.0")


def test_no_scaling_when_single_family_within_cap() -> None:
    _, portfolio_result = route_judge_gate_risk_and_portfolio(technical=full_technical_result())
    trend = next(r for r in portfolio_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert trend.portfolio_allocated_risk == Decimal("500.000")

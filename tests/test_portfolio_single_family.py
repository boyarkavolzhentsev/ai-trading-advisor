"""Stage 8: a single Risk-eligible family with ample capacity is allocated
its full ``max_individual_risk``, unscaled."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.portfolio import PortfolioFamilyVerdict
from app.core.enums.strategy_router import StrategyFamily
from tests.market_evaluation_support import full_technical_result
from tests.portfolio_support import route_judge_gate_risk_and_portfolio


def test_single_eligible_family_ample_capacity_unscaled() -> None:
    risk_result, portfolio_result = route_judge_gate_risk_and_portfolio(technical=full_technical_result())
    risk_trend = next(r for r in risk_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    portfolio_trend = next(r for r in portfolio_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)

    assert portfolio_trend.verdict is PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW
    assert portfolio_trend.reasons == ()
    assert portfolio_trend.portfolio_allocated_risk == risk_trend.max_individual_risk
    # rollover_equity=100000, per-trade budget 500 (0.5%), portfolio cap 6000 (6%) - ample room, no scaling.
    assert portfolio_trend.portfolio_allocated_risk == Decimal("500.000")

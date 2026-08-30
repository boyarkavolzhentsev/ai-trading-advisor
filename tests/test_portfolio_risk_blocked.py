"""Stage 8: a Risk-blocked family always maps to ``BLOCKED_BY_PORTFOLIO`` /
``RISK_NOT_ELIGIBLE`` and never becomes eligible downstream."""

from __future__ import annotations

from app.core.enums.portfolio import PortfolioBlockReason, PortfolioFamilyVerdict
from app.core.enums.risk_gate import RiskFamilyVerdict
from app.core.enums.strategy_router import StrategyFamily
from tests.market_evaluation_support import full_technical_result
from tests.portfolio_support import route_judge_gate_risk_and_portfolio


def test_risk_blocked_family_maps_to_risk_not_eligible() -> None:
    risk_result, portfolio_result = route_judge_gate_risk_and_portfolio(technical=full_technical_result())
    mean_reversion_risk = next(r for r in risk_result.family_results if r.family is StrategyFamily.MEAN_REVERSION)
    assert mean_reversion_risk.verdict is RiskFamilyVerdict.BLOCKED_BY_RISK

    mean_reversion_portfolio = next(r for r in portfolio_result.family_results if r.family is StrategyFamily.MEAN_REVERSION)
    assert mean_reversion_portfolio.verdict is PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO
    assert mean_reversion_portfolio.reasons == (PortfolioBlockReason.RISK_NOT_ELIGIBLE,)
    assert mean_reversion_portfolio.portfolio_allocated_risk is None

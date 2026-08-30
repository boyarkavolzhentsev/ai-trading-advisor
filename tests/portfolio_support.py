"""Shared builders for Stage 8 portfolio-gate tests.

Builds real ``StrategyRiskResult`` fixtures via the real
``StrategyRouter``/``Judge``/``PolicyGate``/``RiskGate`` chain (reusing
``tests/risk_gate_support.py`` and its own upstream support modules), then
runs them through the real ``PortfolioSupervisor`` - never a hand-rolled
``StrategyPortfolioResult`` for anything but malformed-model invariant
tests. Not a test module itself (no ``test_`` prefix): pytest will not
collect it.
"""

from __future__ import annotations

from app.core.enums.technical_analysis import TechnicalAnalysisDimension, TechnicalAnalystType
from app.core.models.portfolio_result import StrategyPortfolioResult
from app.core.models.risk_gate_result import StrategyRiskResult
from app.core.models.technical_supervisor_result import TechnicalSupervisorResult
from app.diversification.supervisor import PortfolioSupervisor
from app.technical_supervisor.supervisor import TechnicalSupervisor
from tests.risk_gate_support import route_judge_gate_and_risk
from tests.technical_supervisor_support import DEFAULT_TIMEFRAMES, analyzed_result, make_observation

__all__ = ["route_judge_gate_risk_and_portfolio", "technical_with_trend_and_confirmed_break"]


def route_judge_gate_risk_and_portfolio(**kwargs: object) -> tuple[StrategyRiskResult, StrategyPortfolioResult]:
    _, risk_result = route_judge_gate_and_risk(**kwargs)
    portfolio_result = PortfolioSupervisor().evaluate(strategy_risk_result=risk_result)
    return risk_result, portfolio_result


def technical_with_trend_and_confirmed_break() -> TechnicalSupervisorResult:
    """TREND analyst clean/directional UPWARD; MARKET_STRUCTURE analyst
    confirms an UPWARD_BREAK on the same timeframes - both TREND_FOLLOWING
    and BREAKOUT resolve DIRECTIONAL, non-conflicting, enabling a 3rd
    simultaneously Risk-eligible family (with EVENT_DRIVEN) for shared-cap
    allocation tests."""
    timeframes = DEFAULT_TIMEFRAMES[:2]
    trend_results = [
        analyzed_result(
            TechnicalAnalystType.TREND,
            timeframe,
            observations=(make_observation(dimension=TechnicalAnalysisDimension.RETURN_DIRECTION, value="UPWARD"),),
        )
        for timeframe in timeframes
    ]
    structure_results = [
        analyzed_result(
            TechnicalAnalystType.MARKET_STRUCTURE,
            timeframe,
            observations=(
                make_observation(dimension=TechnicalAnalysisDimension.STRUCTURAL_BREAK_PRESENCE, value="BREAK_CONFIRMED"),
                make_observation(dimension=TechnicalAnalysisDimension.LATEST_BREAK_DIRECTION, value="UPWARD_BREAK"),
            ),
        )
        for timeframe in timeframes
    ]
    return TechnicalSupervisor().aggregate(tuple(trend_results + structure_results))

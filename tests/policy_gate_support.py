"""Shared builders for Stage 6C policy-gate tests.

Builds real ``TechnicalSupervisorResult``/``ExternalIntelligenceSupervisorResult``
fixtures with precisely controlled observation-level ``FeatureQuality`` (via
``tests/technical_supervisor_support.py``'s own ``quality=`` parameter on
``make_observation``), then routes/judges/gates them through the real
``StrategyRouter``/``Judge``/``PolicyGate`` - never a hand-rolled
``StrategyPolicyResult`` for anything but malformed-model invariant tests.
Not a test module itself (no ``test_`` prefix): pytest will not collect it.
"""

from __future__ import annotations

from app.core.enums.market import Timeframe
from app.core.enums.quality import FeatureQuality
from app.core.enums.technical_analysis import TechnicalAnalysisDimension, TechnicalAnalystType
from app.core.models.policy_gate_result import StrategyPolicyResult
from app.core.models.strategy_judge_result import StrategyJudgeResult
from app.core.models.strategy_router_result import StrategyRouterResult
from app.core.models.technical_supervisor_result import TechnicalSupervisorResult
from app.decision.gate import PolicyGate
from app.judge.judge import Judge
from app.strategies.router import StrategyRouter
from app.technical_supervisor.supervisor import TechnicalSupervisor
from tests.strategy_router_support import evaluation
from tests.technical_supervisor_support import DEFAULT_TIMEFRAMES, analyzed_result, make_observation

__all__ = [
    "route_judge_and_gate",
    "technical_trend_with_quality",
]


def technical_trend_with_quality(
    *,
    timeframes: tuple[Timeframe, ...] = DEFAULT_TIMEFRAMES[:2],
    return_direction: str = "UPWARD",
    slope_direction: str = "UPWARD",
    quality: FeatureQuality = FeatureQuality.VALID,
    result_quality: FeatureQuality | None = None,
) -> TechnicalSupervisorResult:
    """A TREND-analyst-only Technical contour with exact RETURN_DIRECTION/
    SLOPE_DIRECTION values on every given timeframe, every observation
    carrying the given ``quality`` (``result_quality`` defaults to the same
    value for the enclosing ``TechnicalAnalysisResult.quality`` field)."""
    if result_quality is None:
        result_quality = quality
    results = []
    for timeframe in timeframes:
        observations = (
            make_observation(dimension=TechnicalAnalysisDimension.RETURN_DIRECTION, value=return_direction, quality=quality),
            make_observation(dimension=TechnicalAnalysisDimension.SLOPE_DIRECTION, value=slope_direction, quality=quality),
        )
        results.append(
            analyzed_result(TechnicalAnalystType.TREND, timeframe, observations=observations, quality=result_quality)
        )
    return TechnicalSupervisor().aggregate(tuple(results))


def route_judge_and_gate(**evaluate_kwargs: object) -> tuple[StrategyRouterResult, StrategyJudgeResult, StrategyPolicyResult]:
    market_evaluation = evaluation(**evaluate_kwargs)
    router_result = StrategyRouter().route(market_evaluation=market_evaluation)
    judge_result = Judge().judge(strategy_router_result=router_result)
    policy_result = PolicyGate().apply(strategy_judge_result=judge_result)
    return router_result, judge_result, policy_result

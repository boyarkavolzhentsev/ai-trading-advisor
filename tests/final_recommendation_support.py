"""Shared builders for Final Recommendation tests.

Builds a real, actionable ``DecisionRiskPipelineResult`` (via the real
``evaluate_decision_risk_pipeline``) with a deliberately tight stop distance
so Stage 10C's own ``compute_broker_sizing`` produces ``ACTIONABLE`` by
default - never a hand-rolled ``DecisionRiskPipelineResult`` or
``MT5BrokerSizingResult``. Not a test module itself (no ``test_`` prefix):
pytest will not collect it.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.technical import BreakDirection, SwingKind
from app.core.enums.technical_analysis import TechnicalAnalysisDimension, TechnicalAnalystType
from app.core.models.decision_risk_pipeline import DecisionRiskPipelineResult
from app.core.models.market_structure_features import MarketStructureFeatures
from app.core.models.technical_supervisor_result import TechnicalSupervisorResult
from app.orchestration.decision_risk_pipeline import evaluate_decision_risk_pipeline
from app.technical_supervisor.supervisor import TechnicalSupervisor
from tests.decision_risk_pipeline_support import NOW, blocked_assembly, context, ready_assembly, symbol_facts
from tests.risk_gate_support import default_config
from tests.setup_construction_support import structural_break, swing, usable_market_structure
from tests.strategy_judge_support import technical_with_trend_observations
from tests.technical_supervisor_support import DEFAULT_TIMEFRAMES, analyzed_result, make_observation

__all__ = [
    "NOW",
    "actionable_trend_market_structure",
    "blocked_assembly",
    "context",
    "opposite_direction_market_structure",
    "opposite_direction_technical",
    "ready_assembly",
    "run_pipeline",
    "symbol_facts",
    "trend_following_technical",
]


def trend_following_technical() -> TechnicalSupervisorResult:
    return technical_with_trend_observations(return_direction="UPWARD", slope_direction="UPWARD")


def actionable_trend_market_structure(*, stop_price: Decimal = Decimal("100")) -> MarketStructureFeatures:
    """A LOW swing close enough to entry that Stage 10C's own broker-volume
    floor never rejects the resulting size - unlike
    ``tests.decision_risk_pipeline_support.trend_following_market_structure``
    (deliberately far, for Part C's own risk-arithmetic tests, which never
    reach Stage 10C sizing at all)."""
    return usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=stop_price),))


def opposite_direction_technical() -> TechnicalSupervisorResult:
    """TREND_FOLLOWING LONG (``SLOPE_DIRECTION`` only - deliberately omitting
    ``RETURN_DIRECTION`` so BREAKOUT's own ``RETURN_DIRECTION`` corroborating
    check in ``app.judge.judge._judge_breakout`` has nothing to veto against)
    and BREAKOUT SHORT, on one shared technical contour."""
    trend_results = tuple(
        analyzed_result(
            TechnicalAnalystType.TREND,
            timeframe,
            observations=(make_observation(dimension=TechnicalAnalysisDimension.SLOPE_DIRECTION, value="UPWARD"),),
        )
        for timeframe in DEFAULT_TIMEFRAMES[:2]
    )
    structure_results = tuple(
        analyzed_result(
            TechnicalAnalystType.MARKET_STRUCTURE,
            timeframe,
            observations=(
                make_observation(dimension=TechnicalAnalysisDimension.STRUCTURAL_BREAK_PRESENCE, value="BREAK_CONFIRMED"),
                make_observation(dimension=TechnicalAnalysisDimension.LATEST_BREAK_DIRECTION, value="DOWNWARD_BREAK"),
            ),
        )
        for timeframe in DEFAULT_TIMEFRAMES[:2]
    )
    return TechnicalSupervisor().aggregate(trend_results + structure_results)


def opposite_direction_market_structure() -> MarketStructureFeatures:
    low_swing = swing(kind=SwingKind.LOW, price=Decimal("100"))
    high_swing = swing(kind=SwingKind.HIGH, price=Decimal("100.10"))
    break_ = structural_break(
        broken_swing=high_swing, break_close=Decimal("100.05"), direction=BreakDirection.DOWNWARD_BREAK
    )
    return usable_market_structure(swings=(low_swing,), breaks=(break_,))


def run_pipeline(
    *,
    technical=None,
    flow=None,
    external=None,
    m15_market_structure=None,
    account_risk_snapshot_assembly=None,
    trading_cycle_config=None,
    evaluation_time=NOW,
) -> DecisionRiskPipelineResult:
    return evaluate_decision_risk_pipeline(
        flow=flow,
        technical=technical,
        external=external,
        context=context(),
        evaluation_time=evaluation_time,
        symbol_facts=symbol_facts(),
        m15_market_structure=m15_market_structure,
        account_risk_snapshot_assembly=(
            account_risk_snapshot_assembly if account_risk_snapshot_assembly is not None else ready_assembly()
        ),
        trading_cycle_config=trading_cycle_config if trading_cycle_config is not None else default_config(),
    )

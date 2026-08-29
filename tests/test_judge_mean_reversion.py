"""Stage 6B MEAN_REVERSION: no approved V1 semantic mapping exists - always
INSUFFICIENT_EVIDENCE, regardless of how extreme the underlying Technical
facts are. Pins the approved design decision explicitly."""

from __future__ import annotations

from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.strategy_judge import JudgeOutcome
from app.core.enums.technical_analysis import TechnicalAnalysisDimension, TechnicalAnalystType
from app.technical_supervisor.supervisor import TechnicalSupervisor
from tests.market_evaluation_support import full_technical_result
from tests.strategy_judge_support import route_and_judge
from tests.technical_supervisor_support import DEFAULT_TIMEFRAMES, analyzed_result, make_observation


def _mean_reversion_result(judge_result):
    (result,) = [r for r in judge_result.family_results if r.family is StrategyFamily.MEAN_REVERSION]
    return result


def test_full_technical_result_is_still_insufficient() -> None:
    _, judge_result = route_and_judge(technical=full_technical_result())
    result = _mean_reversion_result(judge_result)
    assert result.outcome is JudgeOutcome.INSUFFICIENT_EVIDENCE
    assert result.direction is None
    assert result.evidence_refs == ()


def test_extreme_rsi_midpoint_cannot_activate_mean_reversion() -> None:
    technical = TechnicalSupervisor().aggregate(
        tuple(
            analyzed_result(
                TechnicalAnalystType.MOMENTUM,
                timeframe,
                observations=(make_observation(dimension=TechnicalAnalysisDimension.RSI_MIDPOINT_RELATION, value="ABOVE_MIDPOINT"),),
            )
            for timeframe in DEFAULT_TIMEFRAMES[:2]
        )
    )
    _, judge_result = route_and_judge(technical=technical)
    result = _mean_reversion_result(judge_result)
    assert result.outcome is JudgeOutcome.INSUFFICIENT_EVIDENCE
    assert result.direction is None


def test_extreme_price_vs_sma_cannot_activate_mean_reversion() -> None:
    technical = TechnicalSupervisor().aggregate(
        tuple(
            analyzed_result(
                TechnicalAnalystType.MOVING_AVERAGE,
                timeframe,
                observations=(
                    make_observation(dimension=TechnicalAnalysisDimension.PRICE_VS_SMA_POSITION, value="ABOVE_SMA", subject="20"),
                ),
            )
            for timeframe in DEFAULT_TIMEFRAMES[:2]
        )
    )
    _, judge_result = route_and_judge(technical=technical)
    result = _mean_reversion_result(judge_result)
    assert result.outcome is JudgeOutcome.INSUFFICIENT_EVIDENCE
    assert result.direction is None


def test_range_state_boundary_cannot_activate_mean_reversion() -> None:
    technical = TechnicalSupervisor().aggregate(
        tuple(
            analyzed_result(
                TechnicalAnalystType.RANGE_STATE,
                timeframe,
                observations=(
                    make_observation(dimension=TechnicalAnalysisDimension.DIRECTIONAL_EFFICIENCY_BOUNDARY, value="AT_MINIMUM"),
                ),
            )
            for timeframe in DEFAULT_TIMEFRAMES[:2]
        )
    )
    _, judge_result = route_and_judge(technical=technical)
    result = _mean_reversion_result(judge_result)
    assert result.outcome is JudgeOutcome.INSUFFICIENT_EVIDENCE
    assert result.direction is None


def test_candle_geometry_cannot_activate_mean_reversion() -> None:
    technical = TechnicalSupervisor().aggregate(
        tuple(
            analyzed_result(
                TechnicalAnalystType.CANDLE_STRUCTURE,
                timeframe,
                observations=(
                    make_observation(dimension=TechnicalAnalysisDimension.CLOSE_LOCATION_RELATION, value="ABOVE_MIDPOINT"),
                    make_observation(dimension=TechnicalAnalysisDimension.WICK_SIDE_COMPARISON, value="LOWER_WICK_LARGER"),
                ),
            )
            for timeframe in DEFAULT_TIMEFRAMES[:2]
        )
    )
    _, judge_result = route_and_judge(technical=technical)
    result = _mean_reversion_result(judge_result)
    assert result.outcome is JudgeOutcome.INSUFFICIENT_EVIDENCE
    assert result.direction is None

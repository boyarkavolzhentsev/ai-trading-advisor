"""Stage 6B TREND_FOLLOWING semantic rules: RETURN_DIRECTION/SLOPE_DIRECTION
coherence as PRIMARY, five named dimensions as veto-only CORROBORATING
evidence, no majority voting."""

from __future__ import annotations

from app.core.enums.strategy_judge import DirectionalCandidate, JudgeOutcome
from app.core.enums.strategy_router import StrategyFamily
from tests.strategy_judge_support import route_and_judge, technical_with_moving_average_corroborator, technical_with_trend_observations


def _trend_result(judge_result):
    (result,) = [r for r in judge_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING]
    return result


def test_return_and_slope_agree_upward_is_directional_long() -> None:
    technical = technical_with_trend_observations(return_direction="UPWARD", slope_direction="UPWARD")
    _, judge_result = route_and_judge(technical=technical)
    result = _trend_result(judge_result)
    assert result.outcome is JudgeOutcome.DIRECTIONAL
    assert result.direction is DirectionalCandidate.LONG_CANDIDATE


def test_return_and_slope_agree_downward_is_directional_short() -> None:
    technical = technical_with_trend_observations(return_direction="DOWNWARD", slope_direction="DOWNWARD")
    _, judge_result = route_and_judge(technical=technical)
    result = _trend_result(judge_result)
    assert result.outcome is JudgeOutcome.DIRECTIONAL
    assert result.direction is DirectionalCandidate.SHORT_CANDIDATE


def test_return_and_slope_disagree_is_mixed() -> None:
    technical = technical_with_trend_observations(return_direction="UPWARD", slope_direction="DOWNWARD")
    _, judge_result = route_and_judge(technical=technical)
    result = _trend_result(judge_result)
    assert result.outcome is JudgeOutcome.MIXED
    assert result.direction is None
    assert len(result.evidence_refs) >= 2


def test_only_return_direction_present_is_still_directional() -> None:
    technical = technical_with_trend_observations(return_direction="UPWARD", slope_direction=None)
    _, judge_result = route_and_judge(technical=technical)
    result = _trend_result(judge_result)
    assert result.outcome is JudgeOutcome.DIRECTIONAL
    assert result.direction is DirectionalCandidate.LONG_CANDIDATE


def test_flat_return_direction_across_all_timeframes_is_insufficient() -> None:
    """ALL_AGREE with a non-directional value (FLAT) must not be treated as
    directional evidence."""
    technical = technical_with_trend_observations(return_direction="FLAT", slope_direction="FLAT")
    _, judge_result = route_and_judge(technical=technical)
    result = _trend_result(judge_result)
    assert result.outcome is JudgeOutcome.INSUFFICIENT_EVIDENCE
    assert result.direction is None
    assert result.evidence_refs == ()


def test_no_trend_evidence_at_all_is_insufficient() -> None:
    technical = technical_with_trend_observations(return_direction=None, slope_direction=None)
    _, judge_result = route_and_judge(technical=technical)
    result = _trend_result(judge_result)
    assert result.outcome is JudgeOutcome.INSUFFICIENT_EVIDENCE
    assert result.direction is None
    assert result.evidence_refs == ()


def test_missing_technical_contour_yields_no_family_results() -> None:
    _, judge_result = route_and_judge()
    assert judge_result.family_results == ()


def test_corroborating_agreement_does_not_change_directional_result() -> None:
    trend = technical_with_trend_observations(return_direction="UPWARD", slope_direction="UPWARD")
    combined = technical_with_moving_average_corroborator(trend.analyst_results, price_vs_sma="ABOVE_SMA")
    _, judge_result = route_and_judge(technical=combined)
    result = _trend_result(judge_result)
    assert result.outcome is JudgeOutcome.DIRECTIONAL
    assert result.direction is DirectionalCandidate.LONG_CANDIDATE


def test_corroborating_veto_forces_mixed() -> None:
    trend = technical_with_trend_observations(return_direction="UPWARD", slope_direction="UPWARD")
    combined = technical_with_moving_average_corroborator(trend.analyst_results, price_vs_sma="BELOW_SMA")
    _, judge_result = route_and_judge(technical=combined)
    result = _trend_result(judge_result)
    assert result.outcome is JudgeOutcome.MIXED
    assert result.direction is None


def test_corroborating_evidence_alone_cannot_create_directional_result() -> None:
    """No PRIMARY evidence at all - a corroborating-only signal must never
    manufacture a direction by itself."""
    from app.core.enums.technical_analysis import TechnicalAnalysisDimension, TechnicalAnalystType
    from app.technical_supervisor.supervisor import TechnicalSupervisor
    from tests.technical_supervisor_support import DEFAULT_TIMEFRAMES, analyzed_result, make_observation

    ma_only = TechnicalSupervisor().aggregate(
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
    _, judge_result = route_and_judge(technical=ma_only)
    result = _trend_result(judge_result)
    assert result.outcome is JudgeOutcome.INSUFFICIENT_EVIDENCE
    assert result.direction is None
